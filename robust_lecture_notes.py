#!/usr/bin/env python3
"""Create reliable, Notion-ready notes from PDF or PowerPoint lectures.

PowerPoint files are read as structured documents first.  Vision OCR is used
only for slides that have no extractable text, which keeps requests fast,
accurate, and far below rate limits.  Each expensive stage is checkpointed so
an interrupted run can resume without discarding completed work.

Examples:
    python robust_lecture_notes.py lecture.pptx
    python robust_lecture_notes.py lecture1.pptx lecture2.pptx --vision-fallback
    python robust_lecture_notes.py lecture.pptx --no-qa --output-dir outputs
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from dotenv import load_dotenv
from groq import Groq


PPT_EXTENSIONS = {".pptx"}
PDF_EXTENSIONS = {".pdf"}
DRAWING_NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}


@dataclass
class Slide:
    number: int
    text: str


def natural_slide_key(name: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", name)
    return int(match.group(1)) if match else 0


def extract_pptx_text(path: Path) -> list[Slide]:
    """Extract visible text in visual order from a modern PowerPoint file."""
    with zipfile.ZipFile(path) as presentation:
        slide_names = sorted(
            (name for name in presentation.namelist()
             if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
            key=natural_slide_key,
        )
        if not slide_names:
            raise ValueError(f"{path.name} contains no readable slides.")

        slides: list[Slide] = []
        for number, name in enumerate(slide_names, start=1):
            root = ET.fromstring(presentation.read(name))
            paragraphs: list[str] = []
            for paragraph in root.findall(".//a:p", DRAWING_NS):
                runs = [node.text or "" for node in paragraph.findall(".//a:t", DRAWING_NS)]
                line = "".join(runs).strip()
                if line:
                    paragraphs.append(line)
            slides.append(Slide(number, "\n".join(paragraphs)))
    return slides


def convert_pptx_to_pdf(pptx_path: Path, work_dir: Path) -> Path:
    """Convert with LibreOffice and verify that a PDF was really produced."""
    command = [
        "libreoffice", "--headless", "--convert-to", "pdf",
        "--outdir", str(work_dir), str(pptx_path.resolve()),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    pdf_path = work_dir / f"{pptx_path.stem}.pdf"
    if result.returncode != 0 or not pdf_path.exists():
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"LibreOffice could not convert {pptx_path.name}: {details}")
    return pdf_path


def render_slide(pdf_path: Path, page_number: int, image_path: Path, dpi: int) -> None:
    """Render just one page, avoiding the old script's full-document RAM load."""
    try:
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise RuntimeError("Vision fallback needs pdf2image to be installed.") from exc
    pages = convert_from_path(str(pdf_path), dpi=dpi, first_page=page_number, last_page=page_number)
    if not pages:
        raise RuntimeError(f"Could not render page {page_number} from {pdf_path.name}.")
    pages[0].save(image_path, "PNG")


def load_checkpoint(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_checkpoint(path: Path, data: dict[str, str]) -> None:
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def wait_for_retry(error: Exception, attempt: int) -> float:
    """Use Groq's suggested delay when present, otherwise exponential backoff."""
    match = re.search(r"try again in\s+(?:(\d+)m)?\s*([\d.]+)s", str(error), re.I)
    if match:
        return (int(match.group(1) or 0) * 60) + float(match.group(2)) + 2
    return min(90, 3 * (2 ** attempt))


class GroqNotesClient:
    def __init__(self, api_key: str, summary_model: str, vision_model: str) -> None:
        self.client = Groq(api_key=api_key)
        self.summary_model = summary_model
        self.vision_model = vision_model

    def complete(self, *, model: str, messages: list[dict], max_tokens: int, label: str) -> str:
        for attempt in range(5):
            try:
                response = self.client.chat.completions.create(
                    model=model, messages=messages, max_tokens=max_tokens,
                )
                content = response.choices[0].message.content
                if not content or not content.strip():
                    raise RuntimeError(f"{label} returned an empty response")
                return content.strip()
            except Exception as error:
                if attempt == 4:
                    raise RuntimeError(f"{label} failed after 5 attempts: {error}") from error
                delay = wait_for_retry(error, attempt)
                print(f"  {label} failed ({error}); retrying in {delay:.0f}s...", flush=True)
                time.sleep(delay)
        raise AssertionError("unreachable")

    def ocr_image(self, image_path: Path) -> str:
        image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return self.complete(
            model=self.vision_model,
            max_tokens=1800,
            label=f"OCR {image_path.name}",
            messages=[
                {"role": "system", "content": (
                    "You are a precise OCR system. Return only text visible on the slide. "
                    "Preserve headings, bullets, tables, numbers, and equations. Do not explain, "
                    "summarize, or invent content."
                )},
                {"role": "user", "content": [
                    {"type": "text", "text": "Transcribe this single lecture slide."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                ]},
            ],
        )

    def summarize(self, source: str, title: str) -> str:
        return self.complete(
            model=self.summary_model,
            max_tokens=2400,
            label="Notes generation",
            messages=[
                {"role": "system", "content": (
                    "You are an expert academic note maker who specializes in creating clear, structured, "
                    "and comprehensive university-level notes for any subject. You format notes perfectly "
                    "for Notion using Markdown, with strong organization, readability, and technical accuracy. "
                    "Always retain all key details, definitions, formulas, and examples."
                )},
                {"role": "user", "content": f"""
You will be given some academic text such as:
- a **lecture transcript**,  
- a **book chapter**,  
- a **handout**,  
- a **case study**, or  
- an **exercise/problem set**.

Your task:  
Transform it into **Notion-ready academic notes** that are concise, complete, and well-structured.

---

### 🧾 GENERAL FORMATTING RULES
- Use Markdown-style formatting:
  - `#` for main titles  
  - `##` for sections  
  - `###` for sub-sections  
  - **Bold** for key terms  
  - *Italics* for short clarifications
- Use bullet points and numbered lists for clarity.
- Keep explanations compact but **do not omit key information**.
- Include **formulas**, **examples**, **definitions**, and **tables** when appropriate.
- Maintain **clean indentation and spacing** for Notion readability.

---

### 🧩 IF INPUT LOOKS LIKE A CHAPTER OR LECTURE:
- Create the following structure:
  - `# Title`
  - `## Overview / Objectives`
  - `## Key Concepts`
  - `## Detailed Explanation`
  - `## Examples (if any)`
  - `## Summary / Takeaways`

---

### 🧮 IF INPUT LOOKS LIKE A CASE STUDY OR EXERCISE:
- Use **Q&A format**:
  - **Q:** (bold question)
  - **A:** (clear, structured answer)
- Show all numeric steps, equations, and logic clearly.
- Use tables for comparisons or results.

---

### 📊 IF INPUT COMPARES MULTIPLE TOPICS (e.g., architectures, models, approaches):
- Use a Markdown table with:
  - Columns: *Feature*, *Advantages*, *Disadvantages* (or others as needed)
- End with a short paragraph summarizing the comparison and practical use cases.

---

### 💡 IF INPUT IS A SHORT CONCEPT OR DEFINITION:
- Give a **1–2 sentence** concise explanation.
- Add a simple example, if relevant.

---

### 🎯 OBJECTIVE
Produce **Notion-optimized academic notes** that:
- Are structured, readable, and professional
- Preserve every important concept, formula, and example
- Work across **all subjects and course types**
- Are immediately ready for pasting into Notion with no further editing

---

Now format the following text into Notion-style university notes:

{source}
"""},
            ],
        )

    def qa(self, notes: str, title: str) -> str:
        return self.complete(
            model=self.summary_model,
            max_tokens=2600,
            label="Q&A generation",
            messages=[
                {"role": "system", "content": (
                    "You are a university professor creating exam-style questions.### 🎯 OBJECTIVE:Produce **Notion-optimized academic notes** that:- Are structured, readable, and professional- Preserve every important concept, formula, and example- Work across **all subjects and course types**- Are immediately ready for pasting into Notion with no further editing.- Show all numeric steps, equations, and logic clearly.- Use tables for comparisons or results. If the question requires code, provide code snippet."
                )},
                {"role": "user", "content": f"Generate 15 conceptual questions and their detailed answers from the following lecture text:\n\n{notes}"},
            ],
        )


def slide_blocks(slides: Iterable[Slide]) -> list[str]:
    return [f"--- Slide {slide.number} ---\n{slide.text.strip()}" for slide in slides if slide.text.strip()]


def group_blocks(blocks: list[str], limit: int = 11_000) -> list[str]:
    """Keep slides intact while staying comfortably below a text-model context limit."""
    groups: list[str] = []
    current: list[str] = []
    current_size = 0
    for block in blocks:
        if current and current_size + len(block) + 2 > limit:
            groups.append("\n\n".join(current))
            current, current_size = [], 0
        current.append(block)
        current_size += len(block) + 2
    if current:
        groups.append("\n\n".join(current))
    return groups


def process_document(
    source_path: Path,
    client: GroqNotesClient,
    output_root: Path,
    vision_fallback: bool,
    dpi: int,
    make_qa: bool,
) -> None:
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    if source_path.suffix.lower() not in PPT_EXTENSIONS | PDF_EXTENSIONS:
        raise ValueError(f"Unsupported input: {source_path.name}; use .pptx or .pdf")

    document_dir = output_root / source_path.stem
    document_dir.mkdir(parents=True, exist_ok=True)
    raw_path = document_dir / "source_slides.md"
    notes_path = document_dir / "notion_notes.md"
    qa_path = document_dir / "exam_qa.md"
    checkpoint_path = document_dir / "checkpoint.json"
    title = source_path.stem.replace("_", " ")

    if source_path.suffix.lower() == ".pptx":
        slides = extract_pptx_text(source_path)
    else:
        # Use native PDF text by default. Vision OCR is an explicit fallback for
        # image-only slides because it is substantially more expensive and may
        # be subject to provider output-token limits.
        from PyPDF2 import PdfReader
        reader = PdfReader(str(source_path))
        slides = [Slide(index, page.extract_text() or "") for index, page in enumerate(reader.pages, start=1)]

    checkpoint = load_checkpoint(checkpoint_path)
    empty = [slide for slide in slides if not slide.text.strip()]
    if empty and vision_fallback:
        work_dir = document_dir / ".work"
        work_dir.mkdir(exist_ok=True)
        pdf_path = source_path if source_path.suffix.lower() == ".pdf" else convert_pptx_to_pdf(source_path, work_dir)
        for slide in empty:
            key = f"ocr_slide_{slide.number}"
            if key in checkpoint:
                slide.text = checkpoint[key]
                continue
            image_path = work_dir / f"slide_{slide.number}.png"
            print(f"  OCR fallback: slide {slide.number}/{len(slides)}", flush=True)
            render_slide(pdf_path, slide.number, image_path, dpi)
            slide.text = client.ocr_image(image_path)
            checkpoint[key] = slide.text
            save_checkpoint(checkpoint_path, checkpoint)
            image_path.unlink(missing_ok=True)
        shutil.rmtree(work_dir, ignore_errors=True)
    elif empty:
        print(f"  {len(empty)} textless slide(s) retained as placeholders; use --vision-fallback to OCR them.")
        for slide in empty:
            slide.text = "[This slide contains no extractable text.]"

    raw_content = "\n\n".join(slide_blocks(slides)) + "\n"
    raw_path.write_text(f"# {title}\n\n{raw_content}", encoding="utf-8")
    groups = group_blocks(slide_blocks(slides))
    if not groups:
        raise RuntimeError("No text could be extracted from this document.")

    sections: list[str] = []
    for index, group in enumerate(groups, start=1):
        key = f"summary_group_{index}"
        if key not in checkpoint:
            print(f"  Generating notes section {index}/{len(groups)}", flush=True)
            checkpoint[key] = client.summarize(group, title)
            save_checkpoint(checkpoint_path, checkpoint)
        sections.append(checkpoint[key])
    notes = f"# {title}\n\n" + "\n\n".join(sections) + "\n"
    notes_path.write_text(notes, encoding="utf-8")

    if make_qa:
        if "qa" not in checkpoint:
            # Keep Q&A requests below common provider token-per-minute limits.
            # The complete notes remain in notion_notes.md; Q&A is a derived aid.
            print("  Generating exam Q&A", flush=True)
            checkpoint["qa"] = client.qa(notes[:16_000], title)
            save_checkpoint(checkpoint_path, checkpoint)
        qa_path.write_text(f"# Exam Q&A — {title}\n\n{checkpoint['qa']}\n", encoding="utf-8")
    print(f"  Done: {notes_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path, help="PPTX or PDF lecture files")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--vision-fallback", action="store_true", help="OCR only slides with no native text")
    parser.add_argument("--dpi", type=int, default=180, help="Fallback OCR render resolution (default: 180)")
    parser.add_argument("--no-qa", action="store_true", help="Generate notes only")
    parser.add_argument("--summary-model", default="openai/gpt-oss-120b")
    parser.add_argument("--vision-model", default="qwen/qwen3.8-27b")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("GROQ_API_KEY is missing. Add it to .env or the environment.", file=sys.stderr)
        return 2
    client = GroqNotesClient(api_key, args.summary_model, args.vision_model)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for path in args.files:
        print(f"Processing {path.name}...", flush=True)
        process_document(path, client, args.output_dir, args.vision_fallback, args.dpi, not args.no_qa)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
