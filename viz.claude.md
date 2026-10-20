# viz.py — AI Reference & Architecture Guide

## 1. Overview & Purpose
`viz.py` is a specialized visual OCR extraction and data normalization engine designed for **complex academic tables, multi-level benchmark comparison matrices, and scientific charts**.

Standard OCR models fail on scientific comparison tables because of:
1. Hierarchical, nested multi-level column headers (e.g. a parent header "Speaker" spanning two sub-columns "Face" and "Voice").
2. Checkmarks (✓, ✔, ☑) and cross marks (×, ✗, ☒) representing boolean feature support.
3. Embedded section headers nested inside table rows.
4. Unspaced abbreviations and symbols (e.g., `Vid.`, `Doc.`, `Text&Image`).

`viz.py` solves these challenges by combining structured vision prompting with automatic post-processing, rule-based validation, and dual-output formatting (**Markdown** and **nested JSON**).

---

## 2. Input Types & Supported Formats

### Inputs
- **Image Directory (`IMAGE_FOLDER`)**:
  - Contains PNG, JPG, JPEG, GIF, or WEBP images (e.g. screenshots of paper comparison tables, benchmark graphs, architectural figures).
  - Automatically sorts images alphabetically while prioritizing `"pasted image.png"` at the start.

### Prerequisites
- Python dependencies: `groq`, `python-dotenv`, standard library (`base64`, `pathlib`, `json`, `re`).
- Environment: `GROQ_API_KEY` set in `.env`.

---

## 3. Architecture & Key Features

```
Input Images in IMAGE_FOLDER (e.g., pics/)
   │
   ├──► 1. Image Discovery & Sorting (load_image_files)
   │       - Finds all .png, .jpg, .jpeg, .webp
   │       - Prioritizes "pasted image.png" first
   │
   ├──► 2. Batch Processing (extract_text_from_images)
   │       - Batches images (default: 3 images per request)
   │       - Formats Base64 data URIs
   │
   ├──► 3. Dual-Format Prompting & Generation
   │       ├─► Mode A: Markdown Extraction (Flattened multi-level headers, | syntax)
   │       └─► Mode B: JSON Extraction (Hierarchical nested keys, response_format={"type": "json_object"})
   │
   ├──► 4. Rule-Based Post-Processing (post_process_extraction)
   │       - Symbol conversion: ✓, ✔, ☑ ➔ "Yes" | ×, ✗, ☒ ➔ "No"
   │       - Abbreviation expansion: Vid. ➔ Video, Doc. ➔ Document, Conf. ➔ Conference
   │       - Spacing normalization: Text&Image ➔ Text & Image
   │       - Pulls bold section header rows OUT of tables and converts them to `## Header`
   │
   ├──► 5. Automated Table Validation (validate_table_extraction)
   │       - Scans rows for leftover unconverted symbols
   │       - Detects unexpanded abbreviations
   │       - Flags missing spaces around '&'
   │
   └──► 6. Output Generation
           ├─► pic_text.md (Clean, valid Markdown tables)
           └─► extracted_data.json (Hierarchical benchmark dataset)
```

---

## 4. Multi-Level Header Transformation

When an image table features grouped multi-level column headers:
```
                 Speaker
             Face   |   Voice
```

`viz.py` handles this in two distinct ways:

### Markdown Output: Header Flattening
Flattens the parent and child headers into a single descriptive column:
```markdown
| Benchmarks | Inputs | Outputs | Speaker Face | Speaker Voice |
| --- | --- | --- | --- | --- |
| Talkinghead [30] | Audio & Image | Short Video | Yes | Yes |
```

### JSON Output: Nested Objects
Generates deeply structured schema objects:
```json
{
  "name": "Talkinghead [30]",
  "inputs": ["Audio & Image"],
  "outputs": ["Short Video"],
  "features": {
    "speaker": {
      "face": true,
      "voice": true
    }
  }
}
```

---

## 5. Key Functions

- **`post_process_extraction(raw_text: str) -> str`**:
  - Converts boolean symbols, expands abbreviations, adds spacing around ampersands, and separates section headers from table bodies.
- **`validate_table_extraction(text: str) -> list[str]`**:
  - Scans line-by-line for extraction artifacts and returns diagnostic warning messages.
- **`extract_text_from_images(image_paths, output_format)`**:
  - Dispatches Groq Vision completions (`meta-llama/llama-4-scout-17b-16e-instruct` or specified model) in either Markdown or JSON mode.
- **`load_image_files(image_folder: str) -> list[str]`**:
  - Filters and orders target image files.
- **`main()`**:
  - Executes batch loop, collects markdown and JSON trees, and writes output files.

---

## 6. Execution & Configuration

### Configuration Variables (in `viz.py`)
```python
IMAGE_FOLDER = "pics"               # Directory containing source images
OUTPUT_FILE = "pic_text.md"         # Destination for Markdown tables
OUTPUT_JSON_FILE = "extracted_data.json" # Destination for JSON data
BATCH_SIZE = 3                      # Number of images per API call
MODEL_NAME = "meta-llama/llama-4-scout-17b-16e-instruct"
```

### Execution
```bash
python viz.py
```

---

## 7. Outputs Generated
- **`pic_text.md`**: Delimited markdown sections per batch with cleaned tables and extracted figures.
- **`extracted_data.json`**: Structured dataset containing all batches, image ranges, and parsed JSON objects.

---

## 8. AI Agent Tips
- **When to Use**: Whenever processing paper comparison tables, feature matrices, or benchmark leaderboards where standard OCR produces jumbled columns or missing checkmarks.
- **Validation Issues**: If the console outputs `⚠️ Found N validation issues in this batch`, inspect `pic_text.md` to see if a novel abbreviation or symbol was introduced, and add it to `abbreviations` in `post_process_extraction()`.
