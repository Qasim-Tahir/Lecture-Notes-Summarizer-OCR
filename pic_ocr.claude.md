# pic_ocr.py — AI Reference & Architecture Guide

## 1. Overview & Purpose
`pic_ocr.py` is a lightweight, minimal-dependency batch OCR script designed to extract text directly from folders of images (such as slide screenshots, photographed book pages, or diagrams) using Groq Vision models.

It provides a simple, direct interface without the overhead of PDF rendering, table restructuring, or summarization pipelines, making it ideal for quick extractions, exploratory OCR runs, or feeding raw text into downstream tools.

---

## 2. Input Types & Requirements

### Inputs
- **Image Directory (`IMAGE_FOLDER`)**:
  - Contains `.png` images named with `"image"` prefix (e.g., `image.png`, `image1.png`, `image_02.png`).
  - Automatically ensures `image.png` is processed first.

### Prerequisites
- Python dependencies: `groq`, `python-dotenv`, standard library (`base64`, `os`).
- Environment: `GROQ_API_KEY` set in `.env` or system environment.

---

## 3. Architecture & Workflow

```
Folder of Images (IMAGE_FOLDER)
   │
   ├──► 1. Load & Sort Images
   │       - Filters files starting with "image" and ending with ".png"
   │       - Sorts with "image.png" prioritized first
   │
   ├──► 2. Batch Loop (BATCH_SIZE = 3)
   │       - Reads images into Base64 format
   │       - Dispatches request to Groq Vision API
   │
   ├──► 3. Groq Vision Model (meta-llama/llama-4-scout-17b-16e-instruct)
   │       - System instruction: "Extract all text exactly as seen, preserving layout, equations, and formatting. DO NOT add any extra symbols like '$'."
   │
   └──► 4. Save Aggregated Output
           - Appends batches delimited by "--- Images X to Y ---"
           - Writes plain text file to OUTPUT_FILE (pic_text.txt)
```

---

## 4. Configuration Variables

Parameters are configured directly at the top of the file:
```python
IMAGE_FOLDER = "/home/giga-niga/projects/Upwork/RAG/OCR/pics"  # Path to images
OUTPUT_FILE = "pic_text.txt"                                  # Output destination
BATCH_SIZE = 3                                                # Images per API call (3-5 is safe)
MODEL_NAME = "meta-llama/llama-4-scout-17b-16e-instruct"      # Groq vision model
```

---

## 5. Execution

```bash
# Run the OCR extraction
python pic_ocr.py
```

---

## 6. Output Files
- `pic_text.txt`: Text file containing transcribed content separated by batch headers:
  ```
  --- Images 1 to 3 ---
  [Extracted content from images 1-3]

  --- Images 4 to 6 ---
  [Extracted content from images 4-6]
  ```

---

## 7. Comparison with `viz.py`
- **Use `pic_ocr.py`**: For straightforward text transcription from image folders without complex tables, multi-level headers, or JSON requirements.
- **Use `viz.py`**: When the images contain complex comparison tables, checkmarks, sub-columns, or need JSON structured output.
