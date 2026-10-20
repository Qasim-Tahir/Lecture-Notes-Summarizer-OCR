# test_classroom_ingest.py — AI Reference & Test Guide

## 1. Overview & Purpose
`test_classroom_ingest.py` provides automated unit test coverage for the core URL filtering and filesystem sanitization logic used in [classroom_ingest.py](file:///media/giga-niga/b5bedfd4-42da-dc01-b0ba-ddd442dadc01/projects/Upwork/RAG/OCR/classroom_ingest.py).

It ensures that external URLs scraped from Google Classroom pages are strictly vetted against legitimate Google Drive/Docs endpoints, and that file names suggested by browser downloads cannot cause path traversal or filesystem errors.

---

## 2. Test Cases Covered

### 1. `test_google_attachment_hosts()`
Tests host boundary enforcement:
- **Valid Google Drive links**: `https://drive.google.com/file/d/abc/view` ➔ `True`
- **Valid Google Docs/Presentations**: `https://docs.google.com/presentation/d/abc/edit` ➔ `True`
- **Classroom course navigation links**: `https://classroom.google.com/c/abc` ➔ `False` (prevents recursive classroom looping)
- **Spoofed / Phishing domains**: `https://evil.example/drive.google.com/file` ➔ `False` (ensures exact hostname matching)

### 2. `test_safe_name()`
Tests filename sanitization:
- **Special character removal**: `'lecture:/week?.pdf'` ➔ `'lecture__week_.pdf'` (replaces colons, question marks, slashes with underscores)
- **Empty / Whitespace fallback**: `'  '` ➔ `'attachment'` (ensures no unnamed or dot-only files are created)

---

## 3. Execution Commands

The test file contains plain assertion functions and does not require pytest. Run it with:
```bash
python -c "import test_classroom_ingest as t; t.test_google_attachment_hosts(); t.test_safe_name(); print('ingestion tests passed')"
```

Or execute directly via Python test runner:
```bash
python -c "import test_classroom_ingest; test_classroom_ingest.test_google_attachment_hosts(); test_classroom_ingest.test_safe_name(); print('All tests passed!')"
```

---

## 4. Maintenance Notes
If Google introduces new document attachment hosts (such as `workspace.google.com` or `jamboard.google.com`), update `DRIVE_HOSTS` in `classroom_ingest.py` and add corresponding test assertions here.
