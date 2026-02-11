# PDF & PPTX Lecture Notes Generator

A powerful tool to convert academic PDFs and PPTX slides into structured, Notion-ready notes and exam-style Q&A pairs using OCR (Groq Vision) and LLMs (Llama-4).

## 🚀 Features

- **Multi-Format Support**: Handles both `.pdf` and `.pptx` (via LibreOffice conversion).
- **Selectivity**: Process specific page ranges (e.g., `1-10, 15, 20-25`) or entire documents.
- **Vision-Powered OCR**: Uses Groq's high-speed vision models to extract text, preserving equations and layouts.
- **Notion-Ready Output**: Generates beautifully formatted Markdown summaries optimized for Notion.
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

### Primary Tool: `Book_processor.py`

The most robust script for processing large documents with CLI arguments.

```bash
# Process all pages
python Book_processor.py lecture.pdf

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

### Quick Script: `Lecture_notes.py`

A standalone script for quick processing with hardcoded paths, ideal for simple modifications or one-off tasks.

## 📂 Output

All results are saved in the `outputs/` directory (created automatically):

- `*_extracted.txt`: Raw text extracted via OCR.
- `*_summary.txt`: Structured Markdown notes.
- `*_qa.txt`: Generated Q&A pairs.

## 🤝 Acknowledgments

- [Groq](https://groq.com/) for providing lightning-fast LLM inference.
- [pdf2image](https://github.com/Belval/pdf2image) for PDF manipulation.
