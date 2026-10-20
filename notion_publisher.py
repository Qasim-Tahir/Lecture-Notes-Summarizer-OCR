"""Publish the batch runner's queue through the Notion public API.

Set NOTION_TOKEN and NOTION_PARENT_PAGE_ID in .env. The runner keeps files in
the queue when either value is missing, so a scheduled job never loses work.
"""
from __future__ import annotations

import json
import mimetypes
import os
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional for minimal environments
    load_dotenv = None


API = "https://api.notion.com/v1"
VERSION = "2026-03-11"


def rich(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": text[:2000]}}] if text else []


def markdown_blocks(markdown: str) -> list[dict]:
    blocks: list[dict] = []
    code = False
    code_lines: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("```"):
            if code:
                blocks.append({"object": "block", "type": "code", "code": {"rich_text": rich("\n".join(code_lines)), "language": "plain text"}})
                code_lines, code = [], False
            else:
                code = True
            continue
        if code:
            code_lines.append(line)
            continue
        stripped = line.strip()
        if not stripped:
            continue
        match = None
        for level in (1, 2, 3):
            if stripped.startswith("#" * level + " "):
                match = level
                break
        if match:
            blocks.append({"object": "block", "type": f"heading_{match}", f"heading_{match}": {"rich_text": rich(stripped[match + 1:])}})
        elif stripped.startswith("- "):
            blocks.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich(stripped[2:])}})
        elif stripped[:2].isdigit() and stripped[2:4] == ". ":
            blocks.append({"object": "block", "type": "numbered_list_item", "numbered_list_item": {"rich_text": rich(stripped[4:])}})
        else:
            blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich(stripped)}})
    return blocks


class Notion:
    def __init__(self, token: str, parent: str):
        self.token, self.parent = token, parent

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = Request(API + path, data=data, method=method, headers={"Authorization": f"Bearer {self.token}", "Notion-Version": VERSION, "Content-Type": "application/json"})
        with urlopen(req, timeout=60) as response:
            return json.load(response)

    def create_page(self, title: str, blocks: list[dict]) -> str:
        page = self.request("POST", "/pages", {"parent": {"page_id": self.parent}, "properties": {"title": {"title": [{"type": "text", "text": {"content": title[:2000]}}]}}})
        page_id = page["id"]
        for start in range(0, len(blocks), 100):
            self.request("PATCH", f"/blocks/{page_id}/children", {"children": blocks[start:start + 100]})
        return page.get("url", page_id)

    def upload_file(self, path: Path) -> str:
        filename = path.name
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        upload = self.request("POST", "/file_uploads", {"mode": "single_part", "filename": filename, "content_type": content_type})
        boundary = "----lecture-notes-" + uuid.uuid4().hex
        body = b"--" + boundary.encode() + b"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"" + filename.encode() + b"\"\r\nContent-Type: " + content_type.encode() + b"\r\n\r\n" + path.read_bytes() + b"\r\n--" + boundary.encode() + b"--\r\n"
        req = Request(f"{API}/file_uploads/{upload['id']}/send", data=body, method="POST", headers={"Authorization": f"Bearer {self.token}", "Notion-Version": VERSION, "Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urlopen(req, timeout=120):
            pass
        return upload["id"]


def publish_state(state_path: Path) -> int:
    if load_dotenv:
        load_dotenv()
    token, parent = os.getenv("NOTION_TOKEN"), os.getenv("NOTION_PARENT_PAGE_ID")
    if not token or not parent:
        print("Notion publishing skipped: set NOTION_TOKEN and NOTION_PARENT_PAGE_ID")
        return 0
    state = json.loads(state_path.read_text(encoding="utf-8"))
    client = Notion(token, parent)
    published = 0
    for key, item in state.get("processed", {}).items():
        if item.get("status") == "published":
            continue
        title, path = item.get("title", key), Path(item.get("path", ""))
        try:
            if item.get("kind") == "solution":
                upload_id = client.upload_file(Path(item["local_path"]))
                blocks = [{"object": "block", "type": "file", "file": {"type": "file_upload", "file_upload": {"id": upload_id}}}]
            else:
                content = ""
                for name in ("notion_notes.md", "exam_qa.md"):
                    file = path / name
                    if file.exists():
                        content += file.read_text(encoding="utf-8") + "\n"
                blocks = markdown_blocks(content)
            item["notion_url"] = client.create_page(title, blocks)
            item["status"] = "published"
            published += 1
        except Exception as exc:
            item["publish_error"] = str(exc)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Published {published} Notion page(s)")
    return published
