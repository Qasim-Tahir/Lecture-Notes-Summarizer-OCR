"""Download permitted Classroom attachments through an authenticated browser.

This intentionally does not bypass Google Workspace or file-owner controls.  It
uses the same permissions as the logged-in browser and records files for which
Google does not expose a download action.

Example:
    python classroom_ingest.py \
        --url 'https://classroom.google.com/c/COURSE_ID' \
        --cdp http://127.0.0.1:9222 \
        --output-dir downloads

Start Chrome yourself with a dedicated automation profile, sign in manually,
and complete any 2FA before running this command.  Do not point Chrome at your
normal profile; Playwright documents that doing so can make Chrome exit or
pages fail to load.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse


DRIVE_HOSTS = {"drive.google.com", "docs.google.com"}
DOWNLOAD_LABELS = re.compile(r"download", re.IGNORECASE)


@dataclass
class AttachmentResult:
    source_url: str
    status: str
    path: str | None = None
    reason: str | None = None


def is_google_attachment(url: str) -> bool:
    """Return true for Google Drive/Docs links, excluding navigation links."""
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in DRIVE_HOSTS


def safe_name(name: str) -> str:
    """Make a browser-provided filename safe and portable."""
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", name).strip(" .")
    return name[:180] or "attachment"


async def visible_download(page, output_dir: Path) -> AttachmentResult:
    """Download only through a visible viewer action, if one is available."""
    url = page.url
    buttons = page.get_by_role("button", name=DOWNLOAD_LABELS)
    links = page.get_by_role("link", name=DOWNLOAD_LABELS)
    action = None
    try:
        await buttons.first.wait_for(timeout=15_000)
        action = buttons.first
    except Exception:
        try:
            await links.first.wait_for(timeout=2_000)
            action = links.first
        except Exception:
            pass
    if not action:
        return AttachmentResult(url, "blocked", reason="No visible Download action")

    try:
        async with page.expect_download(timeout=10_000) as download_info:
            await action.click()
        download = await download_info.value
        filename = safe_name(download.suggested_filename)
        destination = output_dir / filename
        # Avoid overwriting an earlier run's artifact.
        if destination.exists():
            destination = output_dir / f"{destination.stem}-1{destination.suffix}"
        await download.save_as(str(destination))
        return AttachmentResult(url, "downloaded", str(destination))
    except Exception as exc:  # Playwright uses several error types by version.
        return AttachmentResult(url, "blocked", reason=f"Download action did not produce a file: {exc}")


async def collect_links(page) -> list[str]:
    hrefs = await page.locator("a[href]").evaluate_all(
        "els => els.map(e => e.href).filter(Boolean)"
    )
    # Preserve order while de-duplicating links from repeated Classroom cards.
    return list(dict.fromkeys(href for href in hrefs if is_google_attachment(href)))


async def run(urls: list[str], cdp: str, output_dir: Path) -> list[AttachmentResult]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise SystemExit("Install dependencies with `uv sync` or `pip install playwright` followed by `playwright install chromium`.") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[AttachmentResult] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(cdp)
        contexts = browser.contexts
        if not contexts:
            raise RuntimeError("The CDP browser has no browser context.")
        context = contexts[0]
        page = await context.new_page()
        try:
            for source in urls:
                if is_google_attachment(source):
                    links = [source]
                else:
                    await page.goto(source, wait_until="domcontentloaded")
                    # Classroom hydrates post cards after the initial document
                    # load. Wait for attachment links, not a fixed short delay.
                    try:
                        await page.locator(
                            'a[href*="drive.google.com"], a[href*="docs.google.com"]'
                        ).first.wait_for(timeout=15_000)
                    except Exception:
                        await page.wait_for_timeout(1500)
                    links = await collect_links(page)
                if not links:
                    results.append(AttachmentResult(source, "no_attachments", reason="No Drive/Docs links found on page"))
                    continue
                for link in links:
                    viewer = await context.new_page()
                    try:
                        await viewer.goto(link, wait_until="domcontentloaded")
                        await viewer.wait_for_timeout(3000)
                        results.append(await visible_download(viewer, output_dir))
                    finally:
                        await viewer.close()
        finally:
            await page.close()
            await browser.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Download permitted Google Classroom lecture attachments")
    parser.add_argument("--url", action="append", required=True, help="Classroom page URL; repeat for multiple pages")
    parser.add_argument("--cdp", default="http://127.0.0.1:9222", help="Chrome DevTools endpoint")
    parser.add_argument("--output-dir", type=Path, default=Path("downloads"))
    args = parser.parse_args()
    results = asyncio.run(run(args.url, args.cdp, args.output_dir))
    manifest = args.output_dir / "manifest.json"
    manifest.write_text(json.dumps([asdict(item) for item in results], indent=2), encoding="utf-8")
    for result in results:
        detail = result.path or result.reason or ""
        print(f"{result.status:12} {result.source_url} {detail}")
    print(f"Manifest: {manifest}")


if __name__ == "__main__":
    main()
