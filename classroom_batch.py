"""Five-day Classroom batch runner.

The runner scans the authenticated Classroom page, downloads only permitted
attachments, imports public GitHub material, processes unseen files, and
leaves a durable state/queue for Notion publishing. Use --once for a single
run or --daemon to wait between runs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from classroom_ingest import run as download_urls

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional for minimal environments
    load_dotenv = None


DRIVE_ID = re.compile(r"/(?:file/d|document/d|presentation/d|spreadsheets/d)/([^/?]+)")
DATE_TEXT = re.compile(r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2})\b")
ASSESSMENT = re.compile(r"\b(quiz|mid[- ]?term|mid[- ]?exam|final|exam)\b", re.I)


@dataclass
class Material:
    key: str
    title: str
    source_url: str
    kind: str
    posted_at: str | None = None
    local_path: str | None = None
    source: str = "classroom"
    sha: str | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        match = DATE_TEXT.search(value)
        if not match:
            return None
        return datetime.strptime(match.group(1).replace("/", "-"), "%Y-%m-%d").replace(tzinfo=timezone.utc)


def drive_key(url: str) -> str:
    match = DRIVE_ID.search(url)
    if match:
        return f"drive:{match.group(1)}"
    return f"url:{url.split('?')[0]}"


def classify(title: str) -> str:
    value = title.lower().replace("_", " ")
    if re.search(r"solution|answer key|answers", value):
        return "solution"
    if re.search(r"syllabus|course ?outline|outline", value):
        return "syllabus"
    if re.search(r"\bquiz\b", value):
        return "quiz"
    if re.search(r"\bmid\b|mid[- ]?term|mid[- ]?exam|\bfinal\b|\bexam\b|past paper", value):
        return "exam"
    return "lecture"


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"processed": {}, "events": [], "last_run_at": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"processed": {}, "events": [], "last_run_at": None}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


async def scan_classroom(url: str, cdp: str) -> tuple[list[Material], list[dict]]:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(cdp)
        if not browser.contexts:
            raise RuntimeError("CDP browser has no browser context")
        page = await browser.contexts[0].new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(6000)
            records = await page.locator("a[href]").evaluate_all(
                """els => els.map(a => {
                  let node = a, best = a.innerText || a.getAttribute('aria-label') || '';
                  for (let i=0; i<8 && node; i++, node=node.parentElement) {
                    const t = (node.innerText || '').trim();
                    if (t.length > best.length && t.length < 3000) best = t;
                  }
                  const root = a.closest('[role=listitem]') || a.parentElement;
                  const time = root && root.querySelector('time');
                  return {href:a.href, text:best, datetime:time && (time.dateTime || time.title || time.innerText)};
                }).filter(x => /drive\\.google\\.com|docs\\.google\\.com/.test(x.href))"""
            )
            materials: list[Material] = []
            for record in records:
                url_value = record["href"]
                title = (record.get("text") or "").splitlines()[0].strip() or url_value
                materials.append(Material(drive_key(url_value), title, url_value, classify(title), record.get("datetime")))
            body = await page.locator("body").inner_text()
            events: list[dict] = []
            for record in records:
                if ASSESSMENT.search(record.get("text") or ""):
                    events.append({"text": (record.get("text") or "")[:500], "date": record.get("datetime")})
            for line in body.splitlines():
                line = line.strip()
                if ASSESSMENT.search(line):
                    events.append({"text": line[:500], "date": (DATE_TEXT.search(line).group(1) if DATE_TEXT.search(line) else None)})
            unique = {m.key: m for m in materials}
            return list(unique.values()), events
        finally:
            await page.close()
            await browser.close()


def github_materials(root: Path, repo: str, folder: str, state: dict) -> list[Material]:
    api = f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1"
    request = Request(api, headers={"Accept": "application/vnd.github+json", "User-Agent": "lecture-notes-runner"})
    with urlopen(request, timeout=30) as response:
        tree = json.load(response)["tree"]
    found: list[Material] = []
    for item in tree:
        path = item.get("path", "")
        if not path.startswith(folder.rstrip("/") + "/") or not path.lower().endswith((".pdf", ".pptx")):
            continue
        raw = "https://raw.githubusercontent.com/{repo}/main/{path}".format(repo=repo, path=path.replace(" ", "%20"))
        title = Path(path).stem
        found.append(Material(f"github:{path}", title, raw, classify(title), source="github", sha=item.get("sha")))
    return found


def select_quiz_window(materials: list[Material], events: list[dict]) -> list[Material]:
    quizzes = sorted((parse_date(e.get("date")) for e in events if e.get("date") and re.search(r"\bquiz\b", e.get("text", ""), re.I)), key=lambda x: x or datetime.min.replace(tzinfo=timezone.utc))
    if not quizzes:
        return []
    latest = quizzes[-1]
    previous = max(
        (
            d
            for d in (
                parse_date(e.get("date"))
                for e in events
                if e.get("date") and ASSESSMENT.search(e.get("text", ""))
            )
            if d and d < latest
        ),
        default=None,
    )
    candidates = []
    for item in materials:
        posted = parse_date(item.posted_at)
        if item.kind == "lecture" and posted and (previous is None or posted > previous) and posted <= latest:
            candidates.append(item)
    return candidates


def run_process(material: Material, output_root: Path) -> Path:
    local = Path(material.local_path or "")
    source_root = output_root / "sources"
    notion_root = output_root / "notion"
    subprocess.run([sys.executable, "extract_lecture_sources.py", str(source_root), str(local)], check=True)
    source = source_root / local.stem / "source_slides.md"
    subprocess.run([sys.executable, "regenerate_notion_notes.py", str(source), "--output-dir", str(notion_root)], check=True)
    return notion_root / local.stem


def run_quiz_prep(materials: list[Material], output_root: Path, latest: datetime) -> Path | None:
    """Create one combined source and notes page for the current quiz window."""
    usable = [m for m in materials if m.local_path and m.kind == "lecture"]
    if not usable:
        return None
    source_root = output_root / "sources" / f"Quiz Prep {latest.date().isoformat()}"
    source_root.mkdir(parents=True, exist_ok=True)
    combined = [f"# Quiz Prep {latest.date().isoformat()}", ""]
    for material in usable:
        source = output_root / "sources" / Path(material.local_path).stem / "source_slides.md"
        if source.exists():
            combined += [f"## {material.title}", "", source.read_text(encoding="utf-8"), ""]
    source_path = source_root / "source_slides.md"
    source_path.write_text("\n".join(combined), encoding="utf-8")
    subprocess.run([sys.executable, "regenerate_notion_notes.py", str(source_path), "--output-dir", str(output_root / "notion")], check=True)
    return output_root / "notion" / source_root.name


def run_once(args: argparse.Namespace) -> None:
    state_path = Path(args.state)
    state = load_state(state_path)
    materials, events = asyncio.run(scan_classroom(args.classroom_url, args.cdp))
    materials.extend(github_materials(Path(args.output_dir), args.github_repo, args.github_folder, state))
    download_dir = Path(args.output_dir) / "downloads"
    for material in materials:
        if material.source == "github":
            target = download_dir / Path(material.source_url).name.replace("%20", " ")
            if not target.exists():
                request = Request(material.source_url, headers={"User-Agent": "lecture-notes-runner"})
                with urlopen(request, timeout=60) as response:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(response.read())
            material.local_path = str(target)
        elif material.key not in state["processed"]:
            results = asyncio.run(download_urls([material.source_url], args.cdp, download_dir))
            if results and results[0].status == "downloaded":
                material.local_path = results[0].path
        if not material.local_path:
            continue
        if material.key in state["processed"]:
            continue
        if material.kind in {"lecture", "syllabus", "exam"}:
            page_dir = run_process(material, Path(args.output_dir))
            state["processed"][material.key] = {"status": "notes_ready", "kind": material.kind, "title": material.title, "path": str(page_dir), "source_url": material.source_url, "processed_at": utcnow().isoformat()}
        elif material.kind == "solution":
            state["processed"][material.key] = {"status": "upload_as_is", "kind": material.kind, "title": material.title, "local_path": material.local_path, "source_url": material.source_url, "processed_at": utcnow().isoformat()}
    prep = select_quiz_window(materials, events)
    quiz_dates = [parse_date(e.get("date")) for e in events if e.get("date") and re.search(r"\bquiz\b", e.get("text", ""), re.I)]
    prep_path = run_quiz_prep(prep, Path(args.output_dir), max(quiz_dates)) if quiz_dates and prep else None
    state["events"] = events
    state["last_run_at"] = utcnow().isoformat()
    state["quiz_prep_candidates"] = [asdict(x) for x in prep]
    state["quiz_prep_path"] = str(prep_path) if prep_path else None
    if prep_path:
        prep_key = f"quiz-prep:{max(quiz_dates).date().isoformat()}"
        state["processed"].setdefault(prep_key, {"status": "notes_ready", "kind": "quiz_prep", "title": f"Quiz Prep {max(quiz_dates).date().isoformat()}", "path": str(prep_path), "processed_at": utcnow().isoformat()})
    state["notion_queue"] = [v for v in state["processed"].values() if v.get("status") in {"notes_ready", "upload_as_is"}]
    save_state(state_path, state)
    if os.getenv("NOTION_TOKEN") and os.getenv("NOTION_PARENT_PAGE_ID"):
        from notion_publisher import publish_state
        publish_state(state_path)
    print(json.dumps({"materials": len(materials), "processed": len(state["processed"]), "quiz_prep_candidates": len(prep), "state": str(state_path)}, indent=2))


def main() -> None:
    if load_dotenv:
        load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--classroom-url", required=True)
    parser.add_argument("--cdp", default="http://127.0.0.1:9222")
    parser.add_argument("--state", default="state/classroom_batch.json")
    parser.add_argument("--output-dir", default="outputs/classroom-batch")
    parser.add_argument("--github-repo", default="saleha-muzammil/Academic-Time-Machine")
    parser.add_argument("--github-folder", default="Generative AI")
    parser.add_argument("--interval-days", type=float, default=5)
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--once", action="store_true", help="Run one batch; this is the default")
    args = parser.parse_args()
    while True:
        try:
            run_once(args)
        except Exception as exc:
            print(f"batch failed: {exc}")
        if not args.daemon:
            return
        time.sleep(max(60, args.interval_days * 86400))


if __name__ == "__main__":
    main()
