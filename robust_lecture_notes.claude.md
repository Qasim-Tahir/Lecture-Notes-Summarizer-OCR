# robust_lecture_notes.py — AI Reference & Architecture Guide

## 1. Overview & Purpose
`robust_lecture_notes.py` is a checkpointed lecture-note generator for PowerPoint presentations (`.pptx`) and PDF slide decks (`.pdf`).

Its core architectural design principles are:
1. **Direct Structured Text Extraction**: For `.pptx` files, it unzips the presentation and parses OpenXML DrawingML text nodes directly. This avoids image conversion for slides containing native text. It does not guarantee that text embedded in images, charts, or unusual PowerPoint objects will be extracted.
2. **Selective Vision OCR Fallback**: Vision OCR (`qwen/qwen3.8-27b`) is invoked **only** for slides that contain no extractable text (e.g. diagrams, handwritten equations, scanned figures), and only when `--vision-fallback` is explicitly enabled.
3. **Resilient Checkpointing**: Every expensive stage (individual slide OCR, summary chunks, Q&A) is persisted to `checkpoint.json`. If an API rate limit or network error occurs, the script can be restarted and will resume immediately from the exact point of interruption without repeating work.
4. **Smart Rate-Limit Backoff**: Parses Groq API rate limit error strings (e.g., `"try again in 2m 14.5s"`) to sleep for the exact duration required before retrying up to 5 times.

---

## 2. Input Types & Prerequisites

### Supported Inputs
- **PowerPoint Files (`.pptx`)**: Modern OpenXML PowerPoint files.
- **PDF Documents (`.pdf`)**: Lecture slide decks, course notes, paper handouts.

### Prerequisites
- **Python Libraries**: `groq`, `PyPDF2`, `python-dotenv`, `pdf2image` (if using vision fallback).
- **System Tools (only for vision fallback on .pptx)**: `libreoffice` (headless), `poppler-utils`.
- **Environment**: `GROQ_API_KEY` set in `.env` or system environment.

---

## 3. Architecture & Core Workflow

```
Input File (.pptx or .pdf)
   │
   ├──► 1. Slide Text Extraction
   │       ├─► PPTX: OpenXML zipfile extraction (ppt/slides/slide*.xml) via extract_pptx_text()
   │       └─► PDF:  PyPDF2 text extraction per page
   │
   ├──► 2. Vision OCR Fallback (Optional, for textless slides)
   │       ├─► If textless slides exist AND --vision-fallback enabled:
   │       │     └─► Convert slide to single-page PNG (render_slide)
   │       │     └─► Groq Vision OCR (qwen/qwen3.8-27b)
   │       │     └─► Save to checkpoint.json
   │       └─► Else: Mark as placeholder "[This slide contains no extractable text.]"
   │
   ├──► 3. Slide Aggregation & Grouping
   │       ├─► Format slide blocks: "--- Slide N ---\n<text>"
   │       ├─► Save verbatim source to outputs/<stem>/source_slides.md
   │       └─► Group slides into ~11,000 character segments (group_blocks)
   │
   ├──► 4. Structured Notion Notes Generation
   │       ├─► Groq LLM (openai/gpt-oss-120b) summarizes each group
   │       ├─► Enforces Notion Markdown hierarchy (#, ##, tables, bolding)
   │       ├─► Checkpoints each group to checkpoint.json
   │       └─► Merges into outputs/<stem>/notion_notes.md
   │
   └──► 5. Exam-Style Conceptual Q&A Generation
           ├─► Groq LLM attempts to generate 15 conceptual Q&A pairs
           ├─► Formatted with questions, answers, derivations, tables, code snippets
           └─► Saves to outputs/<stem>/exam_qa.md
```

---

## 4. Key Classes & Functions

- **`class Slide` (dataclass)**:
  - Holds `number: int` and `text: str`.
- **`extract_pptx_text(path: Path) -> list[Slide]`**:
  - Uses `zipfile.ZipFile` to read `ppt/slides/slide{number}.xml`.
  - Parses OpenXML DrawingML namespace (`http://schemas.openxmlformats.org/drawingml/2006/main`).
  - Extracts text from all `a:p` (paragraphs) and `a:t` (text runs) in natural slide order.
- **`group_blocks(blocks: list[str], limit: int = 11_000) -> list[str]`**:
  - Groups slide texts into logical chunks without breaking individual slides, staying safely within LLM context limits.
- **`class GroqNotesClient`**:
  - Encapsulates Groq client API calls.
  - Handles retries (up to 5 attempts) using `wait_for_retry` (parsing Groq's retry-after header / text).
  - Methods: `ocr_image()`, `summarize()`, and `qa()`.
- **`load_checkpoint(path)` & `save_checkpoint(path, data)`**:
  - Atomic JSON checkpointing using `.tmp` file replacement to prevent corruption.
- **`process_document(source_path, client, output_root, vision_fallback, dpi, make_qa)`**:
  - Coordinates full extraction, checkpointing, summarizing, and file writing.

---

## 5. CLI Usage & Flags

```bash
# Standard run (fast native text extraction, notes + 15 Q&A)
python robust_lecture_notes.py lecture.pptx

# Multiple files in batch
python robust_lecture_notes.py lec1.pptx lec2.pdf lec3.pptx

# Enable Vision OCR for slides that lack native text
python robust_lecture_notes.py lecture.pptx --vision-fallback

# Generate notes only (skip Q&A generation)
python robust_lecture_notes.py lecture.pptx --no-qa

# Customize models or output directory
python robust_lecture_notes.py lecture.pptx \
    --output-dir outputs/my_notes \
    --summary-model openai/gpt-oss-120b \
    --vision-model qwen/qwen3.8-27b \
    --dpi 200
```

---

## 6. Output Files
For an input `lecture.pptx`, outputs are organized into `outputs/lecture/`:
- `source_slides.md`: Verbatim extracted text indexed by slide number (`--- Slide 1 ---`, etc.).
- `notion_notes.md`: Model-generated notes in the script's Markdown format.
- `exam_qa.md`: Intended to contain 15 conceptual questions and answers. Validate numbering and the final answer before treating it as complete.
- `checkpoint.json`: Internal checkpoint state mapping completed steps and OCR caches.

---

## 7. AI Agent Troubleshooting & Tips
- **Crash Recovery**: If the script stops due to network outage or rate-limiting, simply re-run the exact same command. It reads `checkpoint.json` and skips all previously generated sections.
- **When to use `--vision-fallback`**: Use `--vision-fallback` only if slides contain critical architectural diagrams, equations rendered as images, or scanned graphics. If slides are text-heavy, omitting this flag saves significant time and API tokens.
- **Downstream Processing**: The generated `source_slides.md` files are the exact input expected by [regenerate_notion_notes.py](file:///media/giga-niga/b5bedfd4-42da-dc01-b0ba-ddd442dadc01/projects/Upwork/RAG/OCR/regenerate_notion_notes.claude.md) if further Notion-specific math formatting is needed.
