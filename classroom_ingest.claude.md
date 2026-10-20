# classroom_ingest.py — AI Reference & Architecture Guide

## 1. Overview & Purpose
`classroom_ingest.py` is an automated ingestion tool designed to collect permitted lecture materials (PDFs, presentations, handouts) directly from Google Classroom courses using an authenticated browser session over Chrome DevTools Protocol (CDP).

It does **not** bypass Google Workspace or file-owner access controls. Instead, it leverages the authenticated credentials and permissions of an existing user-launched Chrome browser instance. This allows downloading materials from restricted domains or institution-locked accounts where direct API or headless scraping without cookies/2FA would fail.

---

## 2. Input Types & Prerequisites

### Supported Inputs
- **Google Classroom Course URLs**: `https://classroom.google.com/c/<course_id>`
- **Direct Google Drive / Docs Links**: `https://drive.google.com/file/d/...`, `https://docs.google.com/presentation/d/...`

### Prerequisites
1. **Playwright**: Installed via `pip install playwright` and `playwright install chromium`.
2. **Pre-launched Authenticated Chrome**:
   - Must be started manually with remote debugging enabled and a separate user profile:
   ```bash
   google-chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome_automation_profile"
   ```
   - Log into Google Classroom and complete any two-factor authentication (2FA) inside this browser window before running the script.

---

## 3. Architecture & Core Workflow

```
User-Launched Chrome (Port 9222, Logged-in Profile)
       ▲
       │ CDP Connection (playwright.chromium.connect_over_cdp)
       ▼
[classroom_ingest.py]
       │
       ├──► 1. Navigate to Google Classroom Course Page
       │       - Waits for hydration of stream / classwork cards
       │       - Locates Drive / Docs anchor links (`is_google_attachment`)
       │
       ├──► 2. Filter & Deduplicate Attachment Links
       │       - Resolves unique Google Drive & Docs URLs
       │
       ├──► 3. Open Viewer Page for Each Attachment
       │       - Waits for viewer to render action bar
       │       - Locates visible "Download" action button/link (`DOWNLOAD_LABELS`)
       │
       ├──► 4. Download & Sanitize
       │       - Triggers download action inside Playwright `expect_download`
       │       - Sanitizes file name via `safe_name` (removes invalid characters, adds suffixes if duplicate)
       │       - Saves file into `downloads/` directory
       │
       └──► 5. Generate Manifest
               - Records status (`downloaded`, `blocked`, `no_attachments`) in `downloads/manifest.json`
```

---

## 4. Key Functions & Data Structures

- **`AttachmentResult` (dataclass)**:
  - `source_url: str`: URL of the attachment or course page.
  - `status: str`: `"downloaded"`, `"blocked"`, or `"no_attachments"`.
  - `path: str | None`: Local destination path if successfully saved.
  - `reason: str | None`: Detailed diagnostic message if blocked or failed.
- **`is_google_attachment(url: str) -> bool`**:
  - Validates if a hostname belongs to `drive.google.com` or `docs.google.com`. Prevents accidental navigation to arbitrary third-party or navigation links.
- **`safe_name(name: str) -> str`**:
  - Strips filesystem-illegal characters (`\/:*?"<>|`), strips trailing spaces and dots, and truncates to 180 characters.
- **`visible_download(page, output_dir: Path) -> AttachmentResult`**:
  - Finds role `button` or `link` matching regex `download`.
  - Executes browser download and writes file to disk without overwriting existing files.
- **`collect_links(page) -> list[str]`**:
  - Evaluates DOM `a[href]` tags and collects unique Google Drive/Docs links.
- **`run(urls, cdp, output_dir) -> list[AttachmentResult]`**:
  - Async orchestrator managing Playwright browser connection, tab management, navigation timeouts, and error handling.

---

## 5. CLI Usage & Flags

```bash
# Ingest materials from a single Classroom course
python classroom_ingest.py \
    --url 'https://classroom.google.com/c/MzEyODk0NTk4ODAy' \
    --cdp http://127.0.0.1:9222 \
    --output-dir downloads

# Ingest materials from multiple courses in one run
python classroom_ingest.py \
    --url 'https://classroom.google.com/c/COURSE_1' \
    --url 'https://classroom.google.com/c/COURSE_2' \
    --output-dir downloads

# Ingest directly from specific Google Drive attachment URLs
python classroom_ingest.py \
    --url 'https://drive.google.com/file/d/1YkKeqdjgRAkJuTGAxKvnWPUlpNrhFYyg/view' \
    --output-dir downloads
```

---

## 6. Output Files
- **Downloaded Lecture Files**: Saved to `downloads/<filename>.pdf`, `.pptx`, `.docx`, etc.
- **`downloads/manifest.json`**:
  ```json
  [
    {
      "source_url": "https://drive.google.com/file/d/.../view",
      "status": "downloaded",
      "path": "downloads/Lecture 2 AE and VAE v2.pdf",
      "reason": null
    }
  ]
  ```

---

## 7. Troubleshooting & AI Agent Notes
- **"The CDP browser has no browser context"**: Ensure Chrome was started with `--remote-debugging-port=9222` and is actively running.
- **Classroom Post Card Hydration**: Google Classroom dynamically loads cards with JavaScript after `domcontentloaded`. The script waits up to 15 seconds for `a[href*="drive.google.com"]` locators to appear.
- **View-Only Files Without Download Option**: If the teacher disabled downloads ("Viewers cannot download, print, or copy"), the download button will not appear in the viewer. The script correctly marks these files as `"blocked"` with reason `"No visible Download action"`.
