# extract_pdf.py — AI Reference & Architecture Guide

## 1. Overview & Purpose
`extract_pdf.py` is a specialized OCR extraction script engineered specifically for **mathematics textbooks, problem sets, and calculus/algebra exams**.

Unlike general-purpose OCR tools that convert math into arbitrary text, conversational explanations, or solved derivations, `extract_pdf.py` enforces a strict, machine-parseable contract:
- Extracts numbered equations and questions verbatim.
- Emits raw LaTeX equation strings without Markdown math wrappers (`$` or `$$`).
- Strictly prohibits solving, simplifying, or explaining the equations.
- Preserves precise question numbers (`Q20`, `Q21`, etc.).

---

## 2. Input Types & Requirements

### Inputs
- **PDF Documents (`.pdf`)**: Math textbooks, problem sets, exercise sheets, scanned exams.
- **PowerPoint Files (`.pptx`)**: Automatically converted to PDF via LibreOffice.
- **Page Ranges**: Subsets of pages (e.g., `45-50` for a specific problem set).

### Prerequisites
- System tools: `poppler-utils` (`pdftoppm`), `libreoffice` (if converting PPTX).
- Python dependencies: `groq`, `pdf2image`, `PyPDF2`, `python-dotenv`.
- Environment: `GROQ_API_KEY` set in `.env`.

---

## 3. Extraction Protocol & Output Format

### System Prompt Specification
```
You are a highly precise Math OCR data-extraction model. Your sole purpose is to transcribe numbered mathematical questions from images into a strict, parseable format. 

CRITICAL RULES:
1. DO NOT solve the equations.
2. DO NOT include markdown math wrappers like '$' or '$$'.
3. DO NOT output any conversational text, chain-of-thought, introductory, or concluding remarks. 
4. You MUST preserve the question number.

OUTPUT FORMAT:
For every question in the image, output exactly two lines separated by a blank line, using this exact structure:

Q[Number]
[LaTeX Equation]
---
```

### Example Output
```latex
Q20
\frac{dN}{dt} + N = Nte^{t+2}
---

Q21
\frac{dy}{dx} = \frac{xy+3x-y-3}{xy-2x+4y-8}
---
```

---

## 4. Key Functions & Class Structure

### `class LectureProcessor`
- **`__init__(groq_api_key, batch_size=3, dpi=300)`**:
  - Sets up Groq client using `meta-llama/llama-4-scout-17b-16e-instruct`.
- **`parse_page_range(page_range_str, total_pages)`**:
  - Parses 1-based page range string (e.g. `"1-5,10"`) into 0-based index list.
- **`convert_pages_to_files(file_path, page_range)`**:
  - Renders requested pages to high-resolution PNGs on disk.
- **`extract_text_from_images(image_paths)`**:
  - Sends batched images to Groq vision model with the Math OCR system prompt.
- **`process(file_path, page_range, output_dir)`**:
  - Orchestrates rendering, batch extraction, and file output.

---

## 5. CLI Usage & Flags

```bash
# Extract all math questions from a PDF
python extract_pdf.py calculus_exercises.pdf

# Extract math questions from a specific page range (e.g. exercises section)
python extract_pdf.py textbook.pdf 120-135

# Extract from multiple selected pages
python extract_pdf.py assignment.pdf "1-3,7,9-12"
```

---

## 6. Output Files
Generated under `--output-dir` (default: `outputs/`):
- `[basename]_pages_[range]_extracted.txt`: Clean, parseable math problem bank formatted as `Q[N]\n[LaTeX]\n---`.

---

## 7. AI Agent Guidelines
- **Downstream RAG & Solver Pipelines**: The output of this script is ideally structured for automated equation solvers (SymPy, Wolfram Alpha) or downstream quiz-generation RAG systems that parse `Q[Number]` and LaTeX formulas.
- **No Summary / No QA**: Unlike `Book_processor.py` or `robust_lecture_notes.py`, `extract_pdf.py` explicitly leaves summary and Q&A stages commented out to focus solely on fast, deterministic math OCR extraction.
