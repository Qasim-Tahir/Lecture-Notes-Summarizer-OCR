"""
Processor Module - PDF/PPTX to Notes Generator with Page Selection

Handles:
- PDF and PPTX input files
- Selective page processing (page ranges)
- OCR text extraction via Groq LLM
- Summary generation (full verbose or condensed ~40%)
- Q&A generation
- Hallucination verification

Memory efficient: Uses temporary files instead of RAM storage
"""

import os
import base64
import re
import time
from pathlib import Path
from typing import List, Tuple, Optional
from pdf2image import convert_from_path
from groq import Groq


class LectureProcessor:
    """Process lecture PDFs/PPTX into structured notes and Q&A"""

    def __init__(self, groq_api_key: str, batch_size: int = 3, dpi: int = 300):
        self.client = Groq(api_key=groq_api_key)
        self.batch_size = batch_size
        self.dpi = dpi
        self.model = "meta-llama/llama-4-scout-17b-16e-instruct"
        self.summary_model = "meta-llama/llama-4-scout-17b-16e-instruct"

    # ──────────────────────────────────────────────────────────────
    # PAGE RANGE PARSING
    # ──────────────────────────────────────────────────────────────

    def parse_page_range(self, page_range_str: str, total_pages: int) -> List[int]:
        if not page_range_str or page_range_str.lower() == "all":
            return list(range(total_pages))

        pages = []
        parts = page_range_str.split(',')

        try:
            for part in parts:
                part = part.strip()
                if '-' in part:
                    start, end = part.split('-')
                    start = int(start) - 1
                    end = int(end)
                    pages.extend(range(start, end))
                else:
                    pages.append(int(part) - 1)
        except ValueError as e:
            raise ValueError(
                f"Invalid page range format: '{page_range_str}'. "
                f"Expected format: '1-10' or '5,7,9' or '1-5,10-15'"
            ) from e

        pages = sorted(set(pages))
        valid_pages = [p for p in pages if 0 <= p < total_pages]

        if not valid_pages:
            raise ValueError(
                f"No valid pages selected. "
                f"Page range '{page_range_str}' is outside document bounds (1-{total_pages})"
            )

        invalid_pages = set(pages) - set(valid_pages)
        if invalid_pages:
            print(f"Warning: Skipping invalid page numbers: {[p+1 for p in invalid_pages]}")

        return valid_pages

    # ──────────────────────────────────────────────────────────────
    # PDF / PPTX UTILITIES
    # ──────────────────────────────────────────────────────────────

    def get_pdf_page_count(self, pdf_path: str) -> int:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(pdf_path)
            return len(reader.pages)
        except ImportError:
            import subprocess
            result = subprocess.run(
                ['pdfinfo', pdf_path],
                capture_output=True,
                text=True
            )
            for line in result.stdout.split('\n'):
                if line.startswith('Pages:'):
                    return int(line.split(':')[1].strip())
            raise RuntimeError(
                "Could not determine PDF page count. Install PyPDF2 or poppler-utils."
            )

    def convert_pptx_to_pdf(self, pptx_path: str) -> str:
        output_dir = os.path.dirname(pptx_path) or '.'
        cmd = f'libreoffice --headless --convert-to pdf --outdir "{output_dir}" "{pptx_path}"'
        result = os.system(cmd)

        if result != 0:
            raise RuntimeError(
                "Failed to convert PPTX to PDF. "
                "Ensure LibreOffice is installed: sudo apt-get install libreoffice"
            )

        pdf_path = str(Path(pptx_path).with_suffix('.pdf'))
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF conversion failed. Expected file: {pdf_path}")

        return pdf_path

    def convert_pages_to_files(
        self,
        file_path: str,
        page_range: Optional[str] = None
    ) -> Tuple[List[str], List[int]]:
        file_ext = Path(file_path).suffix.lower()

        if file_ext in ['.pptx', '.ppt']:
            print("Converting PPTX to PDF...")
            pdf_path = self.convert_pptx_to_pdf(file_path)
        elif file_ext == '.pdf':
            pdf_path = file_path
        else:
            raise ValueError(
                f"Unsupported file format: {file_ext}. "
                "Supported formats: .pdf, .pptx, .ppt"
            )

        print("Checking PDF page count...")
        total_pages = self.get_pdf_page_count(pdf_path)
        print(f"PDF has {total_pages} pages")

        if page_range:
            selected_indices = self.parse_page_range(page_range, total_pages)
            print(f"Will process {len(selected_indices)} pages: {[i+1 for i in selected_indices]}")
        else:
            selected_indices = list(range(total_pages))
            print(f"Will process all {total_pages} pages")

        print(f"Converting selected pages to images (DPI: {self.dpi})...")
        temp_files = []

        for idx in selected_indices:
            page_num = idx + 1
            temp_file = f"temp_page_{page_num}.png"
            print(f"  Converting page {page_num}...", end='\r')
            pages = convert_from_path(
                pdf_path,
                dpi=self.dpi,
                first_page=page_num,
                last_page=page_num
            )
            pages[0].save(temp_file, "PNG")
            temp_files.append(temp_file)

        print(f"\n✓ Converted {len(temp_files)} pages to image files")
        return temp_files, selected_indices

    # ──────────────────────────────────────────────────────────────
    # TEXT EXTRACTION
    # ──────────────────────────────────────────────────────────────

    def extract_text_from_images(self, image_paths: List[str]) -> str:
        image_contents = []
        for image_path in image_paths:
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
                image_contents.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"}
                })

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an OCR model. Extract ALL text exactly as seen, "
                    "preserving layout and equations. DO NOT ADD ANY '$' for equations."
                )
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract text from ALL these lecture pages:"}
                ] + image_contents
            }
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=8192,
            messages=messages
        )
        time.sleep(10)
        return response.choices[0].message.content.strip()

    def extract_text_from_files(
        self, temp_files: List[str], page_indices: List[int]
    ) -> str:
        all_text = ""

        print(f"Extracting text in batches of {self.batch_size}...")
        for i in range(0, len(temp_files), self.batch_size):
            batch_files = temp_files[i:i + self.batch_size]
            batch_pages = page_indices[i:i + len(batch_files)]

            print(f"Processing batch: pages {[p+1 for p in batch_pages]}")
            extracted = self.extract_text_from_images(batch_files)

            page_label = (
                f"Pages {batch_pages[0]+1} to {batch_pages[-1]+1}"
                if len(batch_pages) > 1
                else f"Page {batch_pages[0]+1}"
            )
            all_text += f"\n\n--- {page_label} ---\n\n{extracted}"

        print("Cleaning up temporary files...")
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)

        return all_text

    # ──────────────────────────────────────────────────────────────
    # CHUNKING
    # ──────────────────────────────────────────────────────────────

    def _chunk_text(self, text: str, max_tokens: int = 6000) -> List[str]:
        sections = re.split(r'\n(?=[A-Z][^\n]{0,80}\n[-=]{3,})', text)
        if len(sections) <= 1:
            max_words = int(max_tokens * 0.75)
            words = text.split()
            sections = [
                " ".join(words[i:i + max_words])
                for i in range(0, len(words), max_words)
            ]
        return [s.strip() for s in sections if s.strip()]

    # ──────────────────────────────────────────────────────────────
    # SUMMARIZATION — FULL VERBOSE
    # ──────────────────────────────────────────────────────────────

    def _summarize_chunk(self, chunk: str) -> str:
        max_retries = 4
        base_delay = 10

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.summary_model,
                    max_tokens=5000,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are an expert academic note-maker creating university-level "
                                "Notion-ready notes. Your notes must be detailed and complete. "
                                "For every concept in the input you must: write a full explanation "
                                "in 2-4 sentences, include every named person, company, and case study "
                                "with their specific details, reproduce all statistics and data points "
                                "exactly including their qualifying language, include direct quotes where "
                                "present, and reproduce any tables in Markdown format. "
                                "Producing a list of headings or terms without elaboration is a failure. "
                                "Your output length should be proportional to the input length. "
                                "CRITICAL: Only include information explicitly present in the provided "
                                "text. Do not add examples, quotes, people, companies, statistics, or "
                                "tables from your training data. If something is not in the input, do "
                                "not include it. An invented example is worse than a missing one."
                            )
                        },
                        {
                            "role": "user",
                            "content": f"""
Transform the following textbook section into detailed Notion-ready Markdown notes.

## ⚠️ REQUIREMENTS — ALL MUST BE SATISFIED

1. **Explain every concept fully** — do not just name it. Write 2-4 sentences of elaboration per concept.
2. **Include every named example** — for each person, company, or case study mentioned, include:
   - Their name and role
   - What they did or represent
   - Any specific details, outcomes, or quotes tied to them
3. **Preserve all numbers and statistics exactly** — reproduce figures with their full qualifying
   language (e.g. "firms with fewer than 500 employees", not just "500 employees").
4. **Reproduce all quotes** — if the source contains a direct quote, include it in the notes.
5. **Reproduce all tables** in Markdown table format.
6. **Do not compress** — if the input is long, the notes should be long. Brevity is not a goal here.
7. **ABSOLUTE RULE** — Every person, company, statistic, and quote in your output must appear
   verbatim in the provided input text. Do not draw on training knowledge to fill gaps.

## Output Format
- `##` for major topics
- `###` for sub-topics
- **Bold** for key terms on first use
- Bullet points for lists, numbered lists for sequences
- Markdown tables for any tabular data

## Textbook Section

{chunk}
"""
                        }
                    ]
                )
                time.sleep(60)
                return response.choices[0].message.content.strip()

            except Exception as e:
                error_code = getattr(e, 'status_code', None)

                if error_code == 413:
                    raise RuntimeError(
                        f"[_summarize_chunk] Chunk still too large. "
                        f"Reduce max_tokens in _chunk_text. Error: {e}"
                    )

                tpd_match = re.search(r'Please try again in (\d+)m([\d.]+)s', str(e))
                if tpd_match:
                    wait = int(tpd_match.group(1)) * 60 + float(tpd_match.group(2)) + 5
                    print(f"[_summarize_chunk] Daily limit hit. Waiting {wait:.0f}s...")
                    time.sleep(wait)
                    continue

                if attempt == max_retries - 1:
                    raise RuntimeError(
                        f"[_summarize_chunk] Failed after {max_retries} attempts: {e}"
                    )

                wait = base_delay * (2 ** attempt)
                print(f"[_summarize_chunk] Attempt {attempt+1} failed: {e}. "
                      f"Retrying in {wait}s...")
                time.sleep(wait)

    # ──────────────────────────────────────────────────────────────
    # SUMMARIZATION — CONDENSED (~40%)
    # ──────────────────────────────────────────────────────────────

    def _summarize_chunk_condensed(self, chunk: str) -> str:
        max_retries = 4
        base_delay = 10

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.summary_model,
                    max_tokens=5000,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are an academic note-maker creating concise university-level notes. "
                                "Your target output is approximately 60% of the input length. "
                                "For every concept include: 2-3 clear definition sentence, "
                                "the single most illustrative named example with its key detail, "
                                "and any critical statistics or quotes — reproduced exactly with their "
                                "full qualifying language. "
                                "Cut all transitional prose, redundant elaboration, and secondary examples. "
                                "Never invent content not present in the input. "
                                "A response that omits key concepts entirely is worse than one that is "
                                "slightly too long."
                            )
                        },
                        {
                            "role": "user",
                            "content": f"""
Transform the following textbook section into concise Notion-ready Markdown notes.

## ⚠️ REQUIREMENTS

1. **One definition per concept** — clear and complete in a single sentence.
2. **One named example per concept maximum** — include the person/company name and
   the single most important detail about them. Drop secondary examples.
3. **Keep all statistics exactly** — reproduce numbers with their full qualifying language
   (e.g. "firms with fewer than 500 employees", not just "500 employees").
4. **Keep direct quotes** — only if they are the primary illustration of a concept.
   Drop quotes that are secondary to another quote already kept.
5. **Reproduce all tables** — in condensed Markdown format, no rows omitted.
6. **Target ~60% of input length** — cut elaboration ruthlessly, keep substance.
7. **ABSOLUTE RULE** — Only include information explicitly present in the input.
   Do not draw on training knowledge to fill gaps.

## Output Format
- `##` for major topics
- `###` for sub-topics
- **Bold** for key terms
- Bullet points for supporting detail
- Numbered lists for sequences

## Textbook Section

{chunk}
"""
                        }
                    ]
                )
                time.sleep(60)
                return response.choices[0].message.content.strip()

            except Exception as e:
                error_code = getattr(e, 'status_code', None)

                if error_code == 413:
                    raise RuntimeError(
                        f"[_summarize_chunk_condensed] Chunk too large. Error: {e}"
                    )

                tpd_match = re.search(r'Please try again in (\d+)m([\d.]+)s', str(e))
                if tpd_match:
                    wait = int(tpd_match.group(1)) * 60 + float(tpd_match.group(2)) + 5
                    print(f"[_summarize_chunk_condensed] Daily limit hit. Waiting {wait:.0f}s...")
                    time.sleep(wait)
                    continue

                if attempt == max_retries - 1:
                    raise RuntimeError(
                        f"[_summarize_chunk_condensed] Failed after {max_retries} attempts: {e}"
                    )

                wait = base_delay * (2 ** attempt)
                print(f"[_summarize_chunk_condensed] Attempt {attempt+1} failed: {e}. "
                      f"Retrying in {wait}s...")
                time.sleep(wait)

    # ──────────────────────────────────────────────────────────────
    # SUMMARIZATION — ORCHESTRATOR
    # ──────────────────────────────────────────────────────────────

    def summarize_text(
        self,
        text: str,
        title: Optional[str] = None,
        condensed: bool = False,
        output_dir: str = "outputs"
    ) -> str:
        title_str = title or "Academic Notes"
        chunks = self._chunk_text(text, max_tokens=6000)
        mode = "condensed" if condensed else "full"
        print(f"[summarize_text] Split into {len(chunks)} chunks ({mode})")

        suffix = "condensed" if condensed else "summary"
        safe_title = title_str.replace(' ', '_').replace('/', '_')
        output_path = os.path.join(output_dir, f"{safe_title}_{suffix}.md")

        summarize_fn = (
            self._summarize_chunk_condensed if condensed
            else self._summarize_chunk
        )

        os.makedirs(output_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# {title_str}\n\n")
            for i, chunk in enumerate(chunks):
                print(f"[summarize_text] Processing chunk {i+1}/{len(chunks)}...")
                chunk_summary = summarize_fn(chunk)
                f.write(chunk_summary)
                f.write("\n\n")
                time.sleep(6)

        print(f"[summarize_text] {mode.capitalize()} notes written to {output_path}")
        return output_path

    # ──────────────────────────────────────────────────────────────
    # HALLUCINATION VERIFICATION (two-pass)
    # ──────────────────────────────────────────────────────────────

    def _verify_entities(self, summary_path: str, source_text: str) -> str:
        """
        Two-pass verification:
        Pass 1 — extract named entities from summary file.
        Pass 2 — check each entity against source text.
        """
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = f.read()

        # Pass 1: Extract entities
        extract_response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Extract every named person, company, organization, product, "
                        "and numeric statistic from the following text. "
                        "Return them as a simple numbered list, one item per line. "
                        "Keep multi-word names together (e.g., 'Grace & Lace', "
                        "'Barbara Corcoran', 'Shark Tank', 'Room to Read').\n\n"
                        f"TEXT:\n{summary}"
                    )
                }
            ]
        )
        entities_raw = extract_response.choices[0].message.content.strip()
        time.sleep(60)

        # Pass 2: Verify against source
        verify_response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=5000,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "You are a fact-checker. Below is a list of named entities "
                        "extracted from a summary, and the original source text.\n\n"
                        "For each entity, check if it appears in the source text.\n"
                        "Be generous with matching — 'Steven Jobs' and 'Steve Jobs' "
                        "are the same person. Multi-word names must be checked as a "
                        "complete unit, not split into parts.\n\n"
                        "Output format:\n"
                        "VERIFIED: [comma-separated list]\n"
                        "NOT IN SOURCE: [comma-separated list — genuine hallucinations only]\n\n"
                        f"ENTITIES TO CHECK:\n{entities_raw}\n\n"
                        f"SOURCE TEXT:\n{source_text}"
                    )
                }
            ]
        )
        time.sleep(60)
        return verify_response.choices[0].message.content.strip()

    # ──────────────────────────────────────────────────────────────
    # Q&A GENERATION
    # ──────────────────────────────────────────────────────────────

    def generate_qa(self, text: str, num_questions: int = 20) -> str:
        max_retries = 4
        base_delay = 10

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=8192,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a university professor creating exam-style questions.### 🎯 OBJECTIVE:Produce **Notion-optimized academic notes** that:- Are structured, readable, and professional- Preserve every important concept, formula, and example- Work across **all subjects and course types**- Are immediately ready for pasting into Notion with no further editing."
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Generate {num_questions} conceptual questions and their detailed "
                                f"answers from the following lecture text:\n\n{text}"
                            )
                        }
                    ]
                )
                return response.choices[0].message.content.strip()

            except Exception as e:
                error_code = getattr(e, 'status_code', None)

                if error_code == 413:
                    raise RuntimeError(
                        f"[generate_qa] Request too large. Error: {e}"
                    )

                tpd_match = re.search(r'Please try again in (\d+)m([\d.]+)s', str(e))
                if tpd_match:
                    wait = int(tpd_match.group(1)) * 60 + float(tpd_match.group(2)) + 5
                    print(f"[generate_qa] Daily limit hit. Waiting {wait:.0f}s...")
                    time.sleep(wait)
                    continue

                if attempt == max_retries - 1:
                    raise RuntimeError(
                        f"[generate_qa] Failed after {max_retries} attempts: {e}"
                    )

                wait = base_delay * (2 ** attempt)
                print(f"[generate_qa] Attempt {attempt+1} failed: {e}. "
                      f"Retrying in {wait}s...")
                time.sleep(wait)

    # ──────────────────────────────────────────────────────────────
    # MAIN PIPELINE
    # ──────────────────────────────────────────────────────────────

    def process(
        self,
        file_path: str,
        page_range: Optional[str] = None,
        output_dir: str = "outputs",
        title: Optional[str] = None,
        skip_extraction: bool = False,
        skip_summary: bool = False,
        skip_qa: bool = False,
        skip_verify: bool = False,
        condensed_summary: bool = False,
        extracted_text_path: Optional[str] = None,
    ) -> dict:

        print(f"\n{'='*60}")
        print(f"Processing: {file_path}")
        if page_range:
            print(f"Page range: {page_range}")
        print(f"{'='*60}\n")

        os.makedirs(output_dir, exist_ok=True)

        base_name = Path(file_path).stem
        if page_range:
            page_range_clean = page_range.replace(',', '_').replace('-', 'to')
            base_name += f"_pages_{page_range_clean}"

        extracted_path     = os.path.join(output_dir, f"{base_name}_extracted.txt")
        summary_suffix     = "condensed" if condensed_summary else "summary"
        summary_path       = os.path.join(output_dir, f"{base_name}_{summary_suffix}.txt")
        qa_path            = os.path.join(output_dir, f"{base_name}_qa.txt")
        verification_path  = None

        # initialise to avoid UnboundLocalError with any skip combination
        all_text  = None
        summary   = None
        qa_pairs  = None

        # ── STEP 1: Extraction ──────────────────────────────────
        if skip_extraction:
            source = extracted_text_path or extracted_path
            if not os.path.exists(source):
                raise FileNotFoundError(
                    f"[process] skip_extraction=True but no extracted file found at: {source}\n"
                    "Provide the path via --extracted or run without --skip-extraction first."
                )
            print(f"⏭️  Skipping extraction. Loading from: {source}")
            with open(source, "r", encoding="utf-8") as f:
                all_text = f.read()
        else:
            print("\nConverting pages to images...")
            temp_files, page_indices = self.convert_pages_to_files(file_path, page_range)
            print("\nExtracting text from images...")
            all_text = self.extract_text_from_files(temp_files, page_indices)
            with open(extracted_path, "w", encoding="utf-8") as f:
                f.write(all_text)
            print(f"✅ Extracted text saved to: {extracted_path}")

        # ── STEP 2: Summary ─────────────────────────────────────
        if skip_summary:
            print("⏭️  Skipping summary generation.")
        else:
            mode_label = "condensed (~40%)" if condensed_summary else "full verbose"
            print(f"\nGenerating {mode_label} summary notes...")
            summary_output_path = self.summarize_text(
                all_text,
                title=title,
                condensed=condensed_summary,
                output_dir=output_dir
            )
            summary = summary_output_path  # path to written file
            # copy to standard summary_path for consistent return dict naming
            if summary_output_path != summary_path:
                import shutil
                shutil.copy(summary_output_path, summary_path)
            print(f"✅ Summary saved to: {summary_path}")

        # ── STEP 3: Verification ────────────────────────────────
        if not skip_verify:
            if summary is None:
                print("⏭️  Skipping verification — no summary was generated.")
            else:
                print("\nVerifying summary for hallucinations...")
                verification = self._verify_entities(summary_path, all_text)
                verification_path = os.path.join(
                    output_dir, f"{base_name}_verification.txt"
                )
                with open(verification_path, "w", encoding="utf-8") as f:
                    f.write(verification)
                for line in verification.splitlines():
                    if line.strip().startswith("NOT IN SOURCE"):
                        print(f"\n⚠️  Potential hallucinations detected:\n{line}")
                        break
                print(f"✅ Verification report saved to: {verification_path}")
        else:
            print("⏭️  Skipping verification.")

        # ── STEP 4: Q&A ─────────────────────────────────────────
        if skip_qa:
            print("⏭️  Skipping Q&A generation.")
        else:
            print("\nGenerating Q&A pairs...")
            qa_pairs = self.generate_qa(all_text)
            with open(qa_path, "w", encoding="utf-8") as f:
                f.write(qa_pairs)
            print(f"✅ Q&A saved to: {qa_path}")

        print(f"\n{'='*60}")
        print(f"✅ Processing complete!")
        print(f"{'='*60}\n")

        return {
            "source_file":        file_path,
            "page_range":         page_range,
            "extracted_path":     extracted_path,
            "summary_path":       summary_path       if not skip_summary else None,
            "verification_path":  verification_path  if not skip_summary and not skip_verify else None,
            "qa_path":            qa_path            if not skip_qa else None,
            "title":              title,
            "condensed":          condensed_summary,
        }


# ──────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="Process lecture/book PDF or PPTX.")
    parser.add_argument("file_path",  help="Path to PDF or PPTX file")
    parser.add_argument("page_range", nargs="?", help="Page range e.g. 1-10,15,20-25")

    parser.add_argument("--title",            default=None,  help="Title for the notes")
    parser.add_argument("--output-dir",       default="outputs")
    parser.add_argument("--skip-extraction",  action="store_true",
                        help="Skip OCR/extraction, load existing extracted text file")
    parser.add_argument("--skip-summary",     action="store_true",
                        help="Skip summary generation")
    parser.add_argument("--skip-qa",          action="store_true",
                        help="Skip Q&A generation")
    parser.add_argument("--skip-verify",      action="store_true",
                        help="Skip hallucination verification step")
    parser.add_argument("--condensed",        action="store_true",
                        help="Generate condensed notes (~40% of source length) instead of full notes")
    parser.add_argument("--extracted",        default=None,
                        help="Path to existing extracted text file (use with --skip-extraction)")

    args = parser.parse_args()

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    processor = LectureProcessor(
        groq_api_key=GROQ_API_KEY,
        batch_size=3,
        dpi=300
    )

    processor.process(
        file_path=args.file_path,
        page_range=args.page_range,
        output_dir=args.output_dir,
        title=args.title,
        skip_extraction=args.skip_extraction,
        skip_summary=args.skip_summary,
        skip_qa=args.skip_qa,
        skip_verify=args.skip_verify,
        condensed_summary=args.condensed,
        extracted_text_path=args.extracted,
    )