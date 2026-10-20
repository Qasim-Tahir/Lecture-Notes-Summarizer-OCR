# PDF & PPTX Lecture Notes Generator

A collection of tools for extracting academic PDFs and PPTX slides, generating structured notes with Groq, and preparing Markdown for Notion.

## 🚀 Features

- **Multi-Format Support**: Handles both `.pdf` and `.pptx` (via LibreOffice conversion).
- **Selectivity**: Process specific page ranges (e.g., `1-10, 15, 20-25`) or entire documents.
- **Vision-Powered OCR**: Uses Groq's high-speed vision models to extract text, preserving equations and layouts.
- **Notion-oriented Output**: `regenerate_notion_notes.py` applies the project's Notion math conventions, but generated content must still be checked for truncation and source accuracy.
- **Study Aids**: Automatically creates conceptual Q&A pairs to help with exam preparation.
- **Memory Efficient**: Processes documents in batches and uses disk-based temporary storage.

## 🛠️ Setup

### 1. System Dependencies

The project relies on external tools for PDF processing and PPTX conversion:

- **Poppler**: Required for `pdf2image`.
  - Ubuntu/Debian: `sudo apt-get install poppler-utils`
- **LibreOffice**: Required for PPTX to PDF conversion.
  - Ubuntu/Debian: `sudo apt-get install libreoffice`

### 2. Python Environment

It is recommended to use a virtual environment.

```bash
# Install dependencies
pip install pdf2image groq Pillow python-dotenv PyPDF2
```

### 3. Configuration

Create a `.env` file in the root directory and add your Groq API key:

```env
GROQ_API_KEY=your_groq_api_key_here
```

## 📖 Usage

### Primary document tools

Use `extract_lecture_sources.py` for offline native PDF/PPTX extraction, then `regenerate_notion_notes.py` for Groq-generated notes and Q&A. Use `robust_lecture_notes.py` when you need checkpointing or OCR fallback. `Book_processor.py` remains the broader processor for long documents and video inputs.

The most robust script for processing large documents with CLI arguments.

```bash
# Extract native slide text without an LLM
python extract_lecture_sources.py outputs lecture.pdf slides.pptx

# Generate notes and Q&A from extracted slide text
python regenerate_notion_notes.py outputs/lecture/source_slides.md

# Process specific page range
python Book_processor.py textbook.pdf 45-67

# Process PPTX slides
python Book_processor.py seminar.pptx 1-10
```

### Batch Image OCR: `pic_ocr.py`

Use this if you have a folder of images (e.g., screenshots of slides) you want to extract text from.

1. Update `IMAGE_FOLDER` in `pic_ocr.py`.
2. Run the script:
   ```bash
   python pic_ocr.py
   ```

`Lecture_notes.py` is no longer part of this repository. Use `test.py` for selective page processing or `Book_processor.py` for the broader legacy workflow.

## 📂 Output

All results are saved in the `outputs/` directory (created automatically):

- `*_extracted.txt`: Raw text extracted via OCR.
- `source_slides.md`: Native slide text with slide markers.
- `notion_notes.md`: Model-generated notes after Notion formatting.
- `exam_qa.md`: Model-generated Q&A. Check that numbering and endings are complete before publication.

## 🤝 Acknowledgments

- [Groq](https://groq.com/) for providing lightning-fast LLM inference.
- [pdf2image](https://github.com/Belval/pdf2image) for PDF manipulation.
