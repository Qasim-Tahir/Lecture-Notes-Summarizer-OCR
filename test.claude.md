# test.py — AI Reference & Architecture Guide

## 1. Overview & Purpose
`test.py` is a versatile and standalone document-to-notes processing engine designed to convert academic PDFs and PowerPoint slide decks into structured study notes and conceptual Q&A pairs.

It provides fine-grained control over document processing with features such as:
- Selective page range parsing (e.g. processing only chapters or sections of a 500-page book).
- High-resolution (300 DPI) temporary page image rendering on disk (minimizing RAM overhead).
- Vision OCR extraction using Groq's multimodal Scout models (`meta-llama/llama-4-scout-17b-16e-instruct`).
- Dual summarization modes: **Full comprehensive notes** or **Condensed notes** (~40% of source volume via `--condensed`).
- Post-generation hallucination verification checking entity grounding (dates, equations, metrics, proper nouns).

---

## 2. Input Types & Requirements

### Inputs
- **PDF Documents (`.pdf`)**: Academic textbooks, lecture slides, research articles.
- **PowerPoint Decks (`.pptx`)**: Automatically converted to temporary PDF via headless LibreOffice.
- **Pre-extracted Text Files (`--extracted`)**: Allows re-running summary or Q&A stages without repeating OCR.

### Prerequisites
- **System Tools**: `poppler-utils` (`pdftoppm`), `libreoffice` (headless).
- **Python Dependencies**: `groq`, `pdf2image`, `PyPDF2`, `Pillow`, `python-dotenv`.
- **Environment**: `GROQ_API_KEY` set in `.env` or system environment.

---

## 3. Architecture & Processing Stages

```
Input File (.pdf or .pptx)
   │
   ├──► 1. Page Range Filtering (parse_page_range)
   │       - Parses "1-10,15,20-25" or "all"
   │       - Validates against total document page count
   │
   ├──► 2. Disk-Based Rendering (convert_pages_to_files)
   │       - Converts selected pages to temp PNGs at 300 DPI
   │       - Keeps memory footprint flat regardless of book size
   │
   ├──► 3. Batch Vision OCR (extract_text_from_files)
   │       - Groups images into batches of 3
   │       - Base64-encodes images and calls Groq Vision LLM
   │       - Saves full transcription to outputs/<stem>_extracted.txt
   │
   ├──► 4. Summarization (summarize_text)
   │       - Chunks text into ~3,000 word segments (_chunk_text)
   │       - Mode A (Standard): In-depth academic Markdown notes
   │       - Mode B (--condensed): ~40% length condensed summary
   │       - Saves summary to outputs/<stem>_summary.txt
   │
   ├──► 5. Conceptual Q&A (generate_qa)
   │       - Prompts LLM as a professor creating 15 exam-grade questions
   │       - Saves to outputs/<stem>_qa.txt
   │
   └──► 6. Hallucination Verification (_verify_entities)
           - Extracts formulas, numbers, dates, and named entities
           - Verifies existence in source text; flags discrepancies
           - Saves verification log to outputs/<stem>_verified.txt
```

---

## 4. Key Methods & Class Structure

### `class LectureProcessor`
- **`__init__(groq_api_key, batch_size=3, dpi=300)`**:
  - Initializes Groq client.
  - Defaults to `meta-llama/llama-4-scout-17b-16e-instruct` for vision and summarization.
- **`parse_page_range(page_range_str, total_pages)`**:
  - Returns sorted 0-indexed list of page numbers. Handles single pages, ranges, and comma-separated lists.
- **`convert_pptx_to_pdf(pptx_path, output_dir)`**:
  - Calls `libreoffice --headless --convert-to pdf`.
- **`convert_pages_to_files(file_path, page_range)`**:
  - Uses `pdf2image.convert_from_path` with `first_page` and `last_page` slices, writing PNGs to a temporary directory.
- **`extract_text_from_images(image_paths)`**:
  - Sends batched images to the vision model with system instructions to preserve layout, math, and code.
- **`_summarize_chunk_condensed(chunk, chunk_index, total_chunks)`**:
  - Specialized condensed prompt generating high-signal, punchy summaries at ~40% of original length.
- **`_verify_entities(source_text, generated_text)`**:
  - Runs a cross-check prompt against the source text to detect fabricated equations, facts, or terms.
- **`process(...)`**:
  - Main driver handling orchestrations and step bypass flags.

---

## 5. CLI Usage & Flags

```bash
# Process all pages of a PDF
python test.py lecture.pdf

# Process specific page ranges of a textbook
python test.py textbook.pdf 1-50
python test.py textbook.pdf "10-25,30,45-50"

# Process a PowerPoint file
python test.py slides.pptx 1-15

# Generate condensed summary (~40% length)
python test.py lecture.pdf --condensed

# Skip extraction (use existing extracted text file)
python test.py lecture.pdf --skip-extraction --extracted outputs/lecture_extracted.txt

# Selective execution flags
python test.py lecture.pdf --skip-summary
python test.py lecture.pdf --skip-qa
python test.py lecture.pdf --skip-verify
python test.py lecture.pdf --output-dir outputs/custom_dir --title "Computer Networks Ch 3"
```

---

## 6. Output Files
Generated in `--output-dir` (default: `outputs/`):
- `[name]_extracted.txt`: Verbatim OCR extraction text.
- `[name]_summary.txt`: Markdown academic notes (standard or condensed).
- `[name]_qa.txt`: 15 conceptual exam questions and answers.
- `[name]_verified.txt`: Entity grounding and verification log.

---

## 7. AI Troubleshooting & Differences from `Book_processor.py`
- **`test.py` vs `Book_processor.py`**:
  - `Book_processor.py` adds video URL downloading (`yt-dlp`), audio extraction (`moviepy`), and Whisper transcription.
  - `test.py` adds the `--condensed` summary mode and focuses purely on document processing with `meta-llama/llama-4-scout-17b-16e-instruct`.
- **DPI Adjustment**: If processing very high-resolution scans or encountering memory issues with `pdf2image`, lower `dpi` in `LectureProcessor(dpi=150)`.
