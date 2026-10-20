# extract.py — AI Reference & Architecture Guide

## 1. Overview & Purpose
`extract.py` is a specialized OCR extraction script designed for **general exam papers, test question banks, multiple choice quizzes, and assignment sheets**.

While [extract_pdf.py](file:///media/giga-niga/b5bedfd4-42da-dc01-b0ba-ddd442dadc01/projects/Upwork/RAG/OCR/extract_pdf.claude.md) strictly forces raw math LaTeX output without text formatting, `extract.py` focuses on verbatim transcription of general examination questions, preserving question numbers, instructions, options, and structured layouts without conversational chain-of-thought or solver commentary.

---

## 2. Input Types & Requirements

### Inputs
- **PDF Documents (`.pdf`)**: Exam papers, quizzes, midterms, question banks.
- **PowerPoint Files (`.pptx`)**: Quiz slides or test presentations.
- **Selective Page Ranges**: e.g., `1-5` or `"2,4,6"`.

### Prerequisites
- System tools: `poppler-utils` (`pdftoppm`), `libreoffice` (if converting PPTX).
- Python dependencies: `groq`, `pdf2image`, `PyPDF2`, `python-dotenv`.
- Environment: `GROQ_API_KEY` set in `.env`.

---

## 3. Extraction Protocol

### System Prompt Specification
```
You are a highly precise OCR data-extraction model. Your sole purpose is to transcribe the questions from images as it is into a strict, presentable format. 

CRITICAL RULES:
1. DO NOT output any conversational text, chain-of-thought, introductory, or concluding remarks. 
2. You MUST preserve the question number.
```

The user prompt instructs:
```
Extract all questions from the provided images as it is:
```

---

## 4. Key Functions & Class Structure

### `class LectureProcessor`
- **`__init__(groq_api_key, batch_size=3, dpi=300)`**:
  - Sets up Groq client using `meta-llama/llama-4-scout-17b-16e-instruct`.
- **`parse_page_range(page_range_str, total_pages)`**:
  - Parses comma-separated ranges into 0-indexed page numbers.
- **`convert_pages_to_files(file_path, page_range)`**:
  - Converts selected pages to temporary PNGs on disk.
- **`extract_text_from_images(image_paths)`**:
  - Batches images and queries the Groq Vision model.
- **`process(file_path, page_range, output_dir)`**:
  - Manages the full pipeline, writing the raw extracted questions to disk.

---

## 5. CLI Usage & Flags

```bash
# Extract all questions from an exam PDF
python extract.py midterm_exam.pdf

# Extract questions from specific pages (e.g. pages 2 through 4)
python extract.py exam_paper.pdf 2-4

# Extract questions from selected pages
python extract.py quiz_bank.pdf "1,3,5-7"
```

---

## 6. Output Files
Outputs are written to `--output-dir` (default: `outputs/`):
- `[basename]_extracted.txt`: Clean, formatted exam question text with preserved question numbers and options.

---

## 7. Comparison with Sister Scripts
- **Use `extract.py`**: When you have an exam, test paper, or multiple-choice quiz and want the exact questions transcribed without answers.
- **Use `extract_pdf.py`**: When you specifically have a math problem set where formulas need to be extracted in strict `Q[N]\n[LaTeX]\n---` format.
- **Use `test.py` or `Book_processor.py`**: When you want full lecture notes, summaries, and AI-generated Q&A solutions.
