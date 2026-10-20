# Book_processor.py — AI Reference & Architecture Guide

## 1. Overview & Purpose
`Book_processor.py` is an end-to-end, multimodal document and media processing pipeline designed to convert long-form academic materials (textbooks, lecture slide decks, book chapters, and video lectures) into structured study notes, conceptual Q&A pairs, and hallucination-verified summaries.

It is engineered for memory efficiency, using disk-based temporary image rendering rather than loading entire multi-hundred-page documents into RAM. It supports multimodal inputs (both visual documents and audio/video streams) and employs hierarchical chunking to handle materials that exceed LLM context windows.

---

## 2. Input Types & Requirements
`Book_processor.py` is designed to ingest:

1. **PDF Documents (`.pdf`)**:
   - Academic textbooks, slide decks, research papers, exam solutions.
   - Text-searchable or scanned/image-based (processed via Vision OCR).
2. **PowerPoint Presentations (`.pptx`)**:
   - Converted automatically to `.pdf` via headless LibreOffice before image extraction.
3. **Video URLs (`--video`)**:
   - YouTube or Instagram video URLs (downloaded via `yt-dlp`, audio extracted via `moviepy`).
4. **Pre-extracted Text Files (`--extracted`)**:
   - Allows skipping the OCR phase and directly generating summaries and Q&As from existing `.txt` files.

### Prerequisites & Dependencies
- **System Tools**: `poppler-utils` (`pdftoppm`), `libreoffice` (headless), `ffmpeg` (for audio/video extraction).
- **Python Libraries**: `groq`, `pdf2image`, `PyPDF2`, `yt-dlp`, `moviepy`, `dotenv`, `Pillow`.
- **Environment**: `GROQ_API_KEY` in `.env` or system environment.

---

## 3. Architecture & Core Workflow

### A. Document Pipeline (`process`)
```
PDF/PPTX File
  │
  ├──► [PPTX to PDF] (LibreOffice conversion if .pptx)
  │
  ├──► [Page Selection] (parse_page_range: e.g. "1-10,15,20-25")
  │
  ├──► [Convert Pages to Temp PNGs] (pdf2image with batching, saves to disk)
  │
  ├──► [Vision OCR via Groq] (batches of 3 images sent to vision model)
  │
  ├──► [Hierarchical Summarization] (chunk text -> summarize chunks -> merge)
  │
  ├──► [Conceptual Q&A Generation] (15 university-level conceptual Q&A pairs)
  │
  └──► [Hallucination Verification] (_verify_entities checks names/numbers against source)
```

### B. Video Pipeline (`process_video`)
```
Video URL (YouTube/Instagram)
  │
  ├──► [Download Audio] (yt-dlp saves audio stream)
  │
  ├──► [Extract/Convert Audio] (moviepy converts to 16kHz mono MP3/WAV)
  │
  ├──► [Transcribe via Groq Whisper] (whisper-large-v3 API)
  │
  └──► [Summarization -> Q&A -> Entity Verification] (same as Document Pipeline)
```

---

## 4. Models & Inference Configuration
- **Vision OCR Model**: `qwen/qwen3.8-27b` (configured in `__init__`)
  - Batched in groups of 3 images per request to stay within token payload limits.
  - System prompt enforces verbatim extraction of text, tables, equations, and diagrams without commentary.
- **Text Reasoning / Summarization / Q&A Model**: `openai/gpt-oss-120b` (configured in `__init__`)
  - Chunk size: ~3,000–4,000 words per chunk.
  - Temperature: default deterministic completions.
- **Audio Transcription Model**: `whisper-large-v3` via Groq Audio API.

---

## 5. Main Class & Key Methods

### `class LectureProcessor`
- **`__init__(groq_api_key, batch_size=3, dpi=300)`**: Initializes Groq client, batch sizes, rendering DPI, and model identifiers.
- **`parse_page_range(page_range_str, total_pages)`**: Parses syntax like `"1-5,10,12-15"` into 0-indexed integer list with boundary validation.
- **`get_pdf_page_count(pdf_path)`**: Fast page count query via `PyPDF2` without rendering images.
- **`convert_pptx_to_pdf(pptx_path, output_dir)`**: Invokes `libreoffice --headless --convert-to pdf`.
- **`convert_pages_to_files(file_path, page_range)`**: Converts selected PDF pages into temporary `.png` files on disk.
- **`extract_text_from_images(image_paths)`**: Base64-encodes images and queries Groq Vision LLM.
- **`summarize_text(text, title)`**: Splits long source text into manageable chunks (`_chunk_text`), summarizes each chunk (`_summarize_chunk`), and merges them into a unified Markdown summary (`_merge_summaries`).
- **`generate_qa(text)`**: Creates 15 conceptual questions and detailed solutions.
- **`_verify_entities(source_text, generated_text)`**: Extracts key entities (dates, numbers, formulas, proper nouns) from the summary/Q&A and verifies they are grounded in the source text.
- **`process_video(video_url, ...)`**: Coordinates downloading audio, Whisper transcription, and downstream study note generation.
- **`process(file_path, ...)`**: End-to-end driver for document files.

---

## 6. CLI Usage & Flags

```bash
# Process an entire textbook or lecture PDF
python Book_processor.py lecture.pdf

# Process specific page ranges
python Book_processor.py textbook.pdf 45-67
python Book_processor.py textbook.pdf "1-10,15,20-30"

# Process a PowerPoint presentation
python Book_processor.py presentation.pptx 1-20

# Process a video lecture from URL
python Book_processor.py --video "https://www.youtube.com/watch?v=..." --title "Neural Networks Lecture 1"

# Skip OCR if already extracted; only generate summary and Q&A
python Book_processor.py lecture.pdf --skip-extraction --extracted outputs/lecture_extracted.txt

# Generation control flags
python Book_processor.py lecture.pdf --skip-summary
python Book_processor.py lecture.pdf --skip-qa
python Book_processor.py lecture.pdf --skip-verify
```

---

## 7. Outputs Generated
All files are saved under `--output-dir` (default: `outputs/`):
- `[basename]_extracted.txt`: Verbatim OCR text extracted across all processed pages.
- `[basename]_summary.txt`: Notion-style structured Markdown notes (Overview, Key Concepts, Tables, Takeaways).
- `[basename]_qa.txt`: 15 conceptual exam questions with detailed answers.
- `[basename]_verified.txt`: Entity verification log highlighting verified vs. ungrounded claims.

---

## 8. Tips & Troubleshooting for AI Agents
1. **LibreOffice Requirement**: If processing `.pptx`, ensure `libreoffice` is installed on the host. If missing, convert the `.pptx` to `.pdf` before passing to `Book_processor.py`.
2. **Groq Model Availability**: The script defaults to `openai/gpt-oss-120b` and `qwen/qwen3.8-27b`. If Groq deprecates or changes availability of these endpoints, update `self.model` and `self.vision_model` in `LectureProcessor.__init__` to currently supported Groq models (e.g. `meta-llama/llama-4-scout-17b-16e-instruct` or `llama-3.3-70b-versatile`).
3. **Rate Limits**: If processing hundreds of pages, add delays between image batches to stay within Groq TPM/RPM limits.
