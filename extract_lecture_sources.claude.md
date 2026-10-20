# extract_lecture_sources.py — AI Reference & Utility Guide

## 1. Overview & Purpose
`extract_lecture_sources.py` is a lightweight, zero-LLM utility script designed to extract raw slide text from PowerPoint (`.pptx`) or PDF (`.pdf`) files and structure it into clean, slide-delimited Markdown files (`source_slides.md`).

It serves as the fast offline preprocessing stage for the Notion notes generation pipeline. By decoupling text extraction from LLM processing, it allows users and agents to inspect and verify extracted slide content before spending LLM tokens on summarization or Q&A generation.

---

## 2. Input Types & Supported Formats
- **PowerPoint Presentations (`.pptx`)**: Parsed natively via OpenXML DrawingML (`extract_pptx_text` from `robust_lecture_notes`).
- **PDF Slide Decks (`.pdf`)**: Parsed via `PyPDF2.PdfReader`.

### Prerequisites
- Python libraries: `PyPDF2`, standard library (`zipfile`, `xml.etree.ElementTree`, `pathlib`).
- Reuses functions from [robust_lecture_notes.py](file:///media/giga-niga/b5bedfd4-42da-dc01-b0ba-ddd442dadc01/projects/Upwork/RAG/OCR/robust_lecture_notes.claude.md).

---

## 3. Workflow & Functionality

1. Takes an output directory and one or more input presentation files.
2. Checks file extension:
   - If `.pptx`: Calls `extract_pptx_text(path)` to extract slide text in document order directly from XML.
   - If `.pdf`: Iterates over PDF pages using `PyPDF2`, extracting visible text. Textless pages receive a placeholder: `[This slide contains no extractable text.]`.
3. Formats each slide using slide block markers:
   ```markdown
   --- Slide 1 ---
   [Slide text here]

   --- Slide 2 ---
   [Slide text here]
   ```
4. Writes the result to `<OUTPUT_DIR>/<stem>/source_slides.md`.

---

## 4. CLI Usage

```bash
# Extract slide text from a single PPTX
python extract_lecture_sources.py outputs/raw_sources lecture.pptx

# Extract slide text from multiple PPTX and PDF files
python extract_lecture_sources.py outputs/raw_sources lecture1.pptx lecture2.pdf lecture3.pptx
```

---

## 5. Downstream Integration
The generated `source_slides.md` file is the exact input format expected by:
- [regenerate_notion_notes.py](file:///media/giga-niga/b5bedfd4-42da-dc01-b0ba-ddd442dadc01/projects/Upwork/RAG/OCR/regenerate_notion_notes.claude.md):
  ```bash
  python regenerate_notion_notes.py outputs/raw_sources/lecture1/source_slides.md --output-dir outputs/notion_notes
  ```
