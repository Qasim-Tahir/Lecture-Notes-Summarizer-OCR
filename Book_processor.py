"""
Processor Module - PDF/PPTX to Notes Generator with Page Selection

Handles:
- PDF and PPTX input files
- Selective page processing (page ranges)
- OCR text extraction via Groq LLM
- Summary generation
- Q&A generation

Memory efficient: Uses temporary files instead of RAM storage
"""

import os
import base64
from pathlib import Path
from typing import List, Tuple, Optional
from pdf2image import convert_from_path
from groq import Groq
import time
import re




class LectureProcessor:
    """Process lecture PDFs/PPTX into structured notes and Q&A"""
    
    def __init__(self, groq_api_key: str, batch_size: int = 3, dpi: int = 300):
        """
        Initialize the processor.
        
        Args:
            groq_api_key: Groq API key for LLM access
            batch_size: Number of images to process at once
            dpi: Resolution for PDF to image conversion
        """
        self.client = Groq(api_key=groq_api_key)
        self.batch_size = batch_size
        self.dpi = dpi
        self.model = "openai/gpt-oss-120b"
        self.vision_model = "qwen/qwen3.8-27b"
    
    def parse_page_range(self, page_range_str: str, total_pages: int) -> List[int]:
        """
        Parse page range string into list of page indices.
        
        Args:
            page_range_str: "1-10,15,20-25" or "all"
            total_pages: Total number of pages in document
        
        Returns:
            List of 0-indexed page numbers: [0,1,2,...,9,14,19,20,...,24]
        
        Examples:
            parse_page_range("1-5", 100) -> [0,1,2,3,4]
            parse_page_range("1,3,5", 100) -> [0,2,4]
            parse_page_range("1-3,7-9", 100) -> [0,1,2,6,7,8]
        """
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
    
    def get_pdf_page_count(self, pdf_path: str) -> int:
        """Get total number of pages in PDF without loading images."""
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
            raise RuntimeError("Could not determine PDF page count. Install PyPDF2 or poppler-utils.")
    
    def convert_pptx_to_pdf(self, pptx_path: str) -> str:
        """
        Convert PPTX to PDF using LibreOffice.
        
        Args:
            pptx_path: Path to PPTX file
        
        Returns:
            Path to generated PDF file
        """
        output_dir = os.path.dirname(pptx_path) or '.'
        cmd = f'libreoffice --headless --convert-to pdf --outdir "{output_dir}" "{pptx_path}"'
        result = os.system(cmd)
        
        if result != 0:
            raise RuntimeError(
                f"Failed to convert PPTX to PDF. "
                f"Ensure LibreOffice is installed: sudo apt-get install libreoffice"
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
        """
        Convert PDF/PPTX pages directly to temporary image files.
        No RAM storage - files are created on disk immediately.
        
        Args:
            file_path: Path to PDF or PPTX file
            page_range: Page range string (e.g., "1-10,15,20-25") or None for all
        
        Returns:
            Tuple of (list of temp image file paths, list of selected page indices)
        """
        file_ext = Path(file_path).suffix.lower()
        
        if file_ext in ['.pptx', '.ppt']:
            print(f"Converting PPTX to PDF...")
            pdf_path = self.convert_pptx_to_pdf(file_path)
        elif file_ext == '.pdf':
            pdf_path = file_path
        else:
            raise ValueError(
                f"Unsupported file format: {file_ext}. "
                f"Supported formats: .pdf, .pptx, .ppt"
            )
        
        print(f"Checking PDF page count...")
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
    
    def extract_text_from_images(self, image_paths: List[str]) -> str:
        """
        Extract text from images using Groq Vision model (qwen/qwen3.8-27b).
        """
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
                "content": "You are an OCR model. Extract ALL text exactly as seen, preserving layout and equations. DO NOT ADD ANY '$' for the equations."
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": "Extract text from ALL these lecture pages:"}] + image_contents
            }
        ]
        
        response = self.client.chat.completions.create(
            model=self.vision_model,
            max_tokens=800,
            messages=messages
        )
        time.sleep(3)
        return response.choices[0].message.content.strip()

    def extract_text_from_files(self, temp_files: List[str], page_indices: List[int], file_path: Optional[str] = None) -> str:
        """
        Extract text from page image files in batches using Groq Vision model.
        """
        all_text = ""
        
        print(f"Extracting text in batches of {self.batch_size} using Groq Vision ({self.vision_model})...")
        for i in range(0, len(temp_files), self.batch_size):
            batch_files = temp_files[i:i+self.batch_size]
            batch_pages = page_indices[i:i+len(batch_files)]
            
            print(f"Processing batch: pages {[p+1 for p in batch_pages]}...")
            try:
                extracted = self.extract_text_from_images(batch_files)
            except Exception as e:
                print(f"Warning: Batch Vision OCR failed ({e}). Retrying page-by-page...")
                extracted = ""
                for bf in batch_files:
                    try:
                        extracted += "\n" + self.extract_text_from_images([bf])
                    except Exception as single_err:
                        print(f"Single page OCR failed for {bf}: {single_err}")
            
            page_label = f"Pages {batch_pages[0]+1} to {batch_pages[-1]+1}" if len(batch_pages) > 1 else f"Page {batch_pages[0]+1}"
            all_text += f"\n\n--- {page_label} ---\n\n{extracted}"
        
        print("Cleaning up temporary files...")
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        
        return all_text
    # def summarize_text(self, text: str, title: Optional[str] = None) -> str:
    #     title_str = title or "Academic Notes"
    #     chunks = self._chunk_text(text, max_tokens=6000)
    #     print(f"[summarize_text] Split into {len(chunks)} chunks")

    #     output_path = f"{title_str.replace(' ', '_')}_summary.md"

    #     with open(output_path, "w", encoding="utf-8") as f:
    #         f.write(f"# {title_str}\n\n")
    #         for i, chunk in enumerate(chunks):
    #             print(f"[summarize_text] Summarizing chunk {i+1}/{len(chunks)}...")
    #             chunk_summary = self._summarize_chunk(chunk)
    #             f.write(chunk_summary)
    #             f.write("\n\n")
    #             time.sleep(6)

    #     print(f"[summarize_text] Summary written to {output_path}")
    #     return output_path
    def summarize_text(self, text: str, title: Optional[str] = None) -> str:
        title_str = title or "Academic Notes"
        chunks = self._chunk_text(text, max_tokens=1500)
        print(f"[summarize_text] Split into {len(chunks)} chunks")

        all_summaries = []
        for i, chunk in enumerate(chunks):
            print(f"[summarize_text] Summarizing chunk {i+1}/{len(chunks)}...")
            chunk_summary = self._summarize_chunk(chunk)
            all_summaries.append(chunk_summary)
            time.sleep(6)

        return f"# {title_str}\n\n" + "\n\n".join(all_summaries)



    def _chunk_text(self, text: str, max_tokens: int = 1000) -> list[str]:
        max_words = max(100, int(max_tokens * 0.6))
        words = text.split()
        if not words:
            return []
        sections = [" ".join(words[i:i+max_words]) for i in range(0, len(words), max_words)]
        return [s.strip() for s in sections if s.strip()]


    def _summarize_chunk(self, chunk: str) -> str:
        max_retries = 4
        base_delay = 10

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=1000,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are an expert academic note-maker creating university-level Notion-ready notes. "
                                "Your notes must be detailed and complete. For every concept in the input you must: "
                                "write a full explanation in 2-4 sentences, include every named person, company, and "
                                "case study with their specific details, reproduce all statistics and data points exactly, "
                                "include direct quotes where present, and reproduce any tables in Markdown format. "
                                "Producing a list of headings or terms without elaboration is a failure. "
                                "Your output length should be proportional to the input length — a long input requires long notes."
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
    3. **Preserve all numbers and statistics exactly** — do not round, drop, or paraphrase figures.
    4. **Reproduce all quotes** — if the source contains a direct quote, include it in the notes.
    5. **Reproduce all tables** in Markdown table format.
    6. **Do not compress** — if the input is long, the notes should be long. Brevity is not a goal here.
    7. **ABSOLUTE RULE: Every person, company, statistic, and quote in your output must appear verbatim in the provided input text. Before including any named entity or statistic, verify it exists in the input. If you cannot find it in the input text, do not include it under any circumstances. Do not draw on training knowledge to fill gaps."
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
                time.sleep(20)
                return response.choices[0].message.content.strip()

            except Exception as e:
                error_code = getattr(e, 'status_code', None)

                if error_code == 413:
                    raise RuntimeError(
                        f"[_summarize_chunk] Chunk still too large. Reduce max_tokens in _chunk_text. Error: {e}"
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
                print(f"[_summarize_chunk] Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)


    def _merge_summaries(self, chunks: list[str], title: Optional[str] = None) -> str:
        """Merge chunk summaries into a single coherent structured document."""
        combined = "\n\n---\n\n".join(chunks)
        title_str = title or "Academic Notes"

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=1000,
            messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert academic editor specializing in creating university-level "
                    "Notion-ready notes. Your output must be a single, coherent, well-structured "
                    "Markdown document. You never drop content — if a concept, example, statistic, "
                        "quote, or table exists in any chunk, it must appear in the final document. "
                        "Merging means unifying structure and removing repetition, never removing substance."
                    )
                },
                {
                    "role": "user",
                    "content": f"""
            You are given multiple summarized chunks from the same academic text, separated by `---`.
            Your task is to merge them into one complete, Notion-ready Markdown document.

            ## Document Title
            {title_str}

            ## ⚠️ STRICT REQUIREMENTS

            1. **Preserve every piece of content** — every definition, named person, company, case study, 
            statistic, quote, and table from any chunk must appear in the final output.
            2. **Deduplicate without dropping** — if the same concept appears in multiple chunks, 
            keep the most detailed version, not the shortest.
            3. **Unify the structure** — create one logical hierarchy of `#`, `##`, `###` headings 
            that reflects the natural flow of the academic content.
            4. **Do not summarize the summaries** — your job is to merge, not to compress further. 
            The output should be at least as long as the longest chunk combined with unique 
            content from the others.
            5. **Reproduce all Markdown tables** from any chunk in the final document.

            ## Output Structure
            ```
            # {title_str}
            ## Learning Objectives (if present)
            ## Key Concepts & Definitions
            ## [One ## section per major topic — mirror the source structure]
            ## Examples & Case Studies
            ## Summary / Key Takeaways
            ```

            ## Chunk Summaries to Merge

            {combined}
            """
                }
            ]
        )
        time.sleep(15)
        return response.choices[0].message.content.strip()
#     def summarize_text(self, text: str, title: Optional[str] = None) -> str:
#         """
#         Generate Notion-ready summary notes from extracted text.
        
#         Args:
#             text: Extracted text from pages
#             title: Optional title for the notes
        
#         Returns:
#             Formatted summary notes
#         """
#         title_prompt = f"\n\nTitle: {title}" if title else ""
        
#         response = self.client.chat.completions.create(
#             model=self.model,
#             messages=[
#                 {
#                     "role": "system",
#                     "content": (
#                         "You are an expert academic note maker who specializes in creating clear, structured, "
#                         "and comprehensive university-level notes for any subject. You format notes perfectly "
#                         "for Notion using Markdown, with strong organization, readability, and technical accuracy. "
#                         "Always retain all key details, definitions, formulas, and examples."
#                     )
#                 },
#                 {
#                     "role": "user",
#                     "content": f"""
# You will be given some academic text such as:
# - a **lecture transcript**,  
# - a **book chapter**,  
# - a **handout**,  
# - a **case study**, or  
# - an **exercise/problem set**.

# Your task:  
# Transform it into **Notion-ready academic notes** that are concise, complete, and well-structured.

# ---

# ### 🧾 GENERAL FORMATTING RULES
# - Use Markdown-style formatting:
#   - `#` for main titles  
#   - `##` for sections  
#   - `###` for sub-sections  
#   - **Bold** for key terms  
#   - *Italics* for short clarifications
# - Use bullet points and numbered lists for clarity.
# - Keep explanations compact but **do not omit key information**.
# - Include **formulas**, **examples**, **definitions**, and **tables** when appropriate.
# - Maintain **clean indentation and spacing** for Notion readability.

# ---

# ### 🧩 IF INPUT LOOKS LIKE A CHAPTER OR LECTURE:
# - Create the following structure:
#   - `# Title`
#   - `## Overview / Objectives`
#   - `## Key Concepts`
#   - `## Detailed Explanation`
#   - `## Examples (if any)`
#   - `## Summary / Takeaways`

# ---

# ### 🧮 IF INPUT LOOKS LIKE A CASE STUDY OR EXERCISE:
# - Use **Q&A format**:
#   - **Q:** (bold question)
#   - **A:** (clear, structured answer)
# - Show all numeric steps, equations, and logic clearly.
# - Use tables for comparisons or results.

# ---

# ### 📊 IF INPUT COMPARES MULTIPLE TOPICS (e.g., architectures, models, approaches):
# - Use a Markdown table with:
#   - Columns: *Feature*, *Advantages*, *Disadvantages* (or others as needed)
# - End with a short paragraph summarizing the comparison and practical use cases.

# ---

# ### 💡 IF INPUT IS A SHORT CONCEPT OR DEFINITION:
# - Give a **1–2 sentence** concise explanation.
# - Add a simple example, if relevant.

# ---

# ### 🎯 OBJECTIVE
# Produce **Notion-optimized academic notes** that:
# - Are structured, readable, and professional
# - Preserve every important concept, formula, and example
# - Work across **all subjects and course types**
# - Are immediately ready for pasting into Notion with no further editing

# ---

# Now format the following text into Notion-style university notes:{title_prompt}

# {text}
# """
#                 }
#             ]
#         )
        
#         return response.choices[0].message.content.strip()
    
    def generate_qa(self, text: str, num_questions: int = 15) -> str:
        """
        Generate Q&A pairs from text.
        
        Args:
            text: Text to generate questions from
            num_questions: Number of questions to generate
        
        Returns:
            Formatted Q&A pairs
        """
        # Truncate text if needed to avoid TPM limits
        truncated_text = text[:4000] if len(text) > 4000 else text
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=1000,
            messages=[
                {
                    "role": "system", 
                    "content": "You are a university professor creating exam-style questions."
                },
                {
                    "role": "user", 
                    "content": f"Generate {num_questions} conceptual questions and their detailed answers from the following lecture text:\n\n{text}"
                }
            ]
        )
        
        return response.choices[0].message.content.strip()
    def _verify_entities(self, summary: str, source_text: str) -> str:
        """
        Extract named entities from summary, check each against source text,
        and flag any that don't appear in the source.
        """
        truncated_source = source_text[:4000] if len(source_text) > 4000 else source_text
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": f"""
    You are a fact-checker. 

    1. Extract every named person, company, statistic, and quote from the SUMMARY.
    2. For each one, check if it appears in the SOURCE TEXT.
    3. List any items present in the SUMMARY but NOT in the SOURCE TEXT.

    SUMMARY:
    {summary}

    SOURCE TEXT:
    {source_text}

    Output format:
    VERIFIED: [items found in source]
    NOT IN SOURCE: [items not found in source — these are hallucinations]
    """
                }
            ]
        )
        return response.choices[0].message.content.strip()




    def _download_audio(self, video_url: str, output_path: str) -> str:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_path.replace('.m4a', ''),  # yt-dlp adds extension
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
            }],
            'extractor_args': {'youtube': {'skip': ['dash', 'hls']}},
            'quiet': False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        return output_path

    def _extract_audio(self, video_path: str, audio_path: str = "extracted_audio.m4a") -> str:
        clip = AudioFileClip(video_path)           # simpler, from older
        clip.write_audiofile(audio_path, codec="aac")
        clip.close()                               # from newer
        return audio_path

    def _transcribe_audio(self, audio_path: str) -> str:
        with open(audio_path, "rb") as f:
            transcription = self.client.audio.transcriptions.create(
                file=(audio_path, f.read()),
                model="whisper-large-v3-turbo",
                response_format="verbose_json",
            )
        return transcription.text                  # .text not ['text']
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

        extracted_path = os.path.join(output_dir, f"{base_name}_extracted.txt")
        summary_path   = os.path.join(output_dir, f"{base_name}_summary.txt")
        qa_path        = os.path.join(output_dir, f"{base_name}_qa.txt")

        # ── STEP 1: Extraction ──────────────────────────────────────────
        if skip_extraction:
            source = extracted_text_path or extracted_path
            if not os.path.exists(source):
                raise FileNotFoundError(
                    f"[process] skip_extraction=True but no extracted file found at: {source}\n"
                    f"Provide the path via --extracted or run without --skip-extraction first."
                )
            print(f"⏭️  Skipping extraction. Loading from: {source}")
            with open(source, "r", encoding="utf-8") as f:
                all_text = f.read()
        else:
            print("\nConverting pages to images...")
            temp_files, page_indices = self.convert_pages_to_files(file_path, page_range)
            print("\nExtracting text from images...")
            all_text = self.extract_text_from_files(temp_files, page_indices, file_path=file_path)
            with open(extracted_path, "w", encoding="utf-8") as f:
                f.write(all_text)
            print(f"✅ Extracted text saved to: {extracted_path}")

        # ── STEP 2: Summary ─────────────────────────────────────────────
        if skip_summary:
            print("⏭️  Skipping summary generation.")
            summary = None
        else:
            print("\nGenerating summary notes...")
            summary = self.summarize_text(all_text, title)
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(summary)
            print(f"✅ Summary saved to: {summary_path}")
        if not skip_verify:
            print("\nVerifying summary for hallucinations...")
            verification = self._verify_entities(summary, all_text)
            verification_path = os.path.join(output_dir, f"{base_name}_verification.txt")
            with open(verification_path, "w", encoding="utf-8") as f:
                f.write(verification)
            for line in verification.splitlines():
                if line.strip().startswith("NOT IN SOURCE"):
                    print(f"\n⚠️  Potential hallucinations detected:\n{line}")
                    break
            print(f"✅ Verification report saved to: {verification_path}")
        else:
            print("⏭️  Skipping verification.")
            verification_path = None
        # ── STEP 3: Q&A ─────────────────────────────────────────────────
        if skip_qa:
            print("⏭️  Skipping Q&A generation.")
            qa_pairs = None
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
            "source_file": file_path,
            "page_range": page_range,
            "extracted_path": extracted_path,
            "summary_path": summary_path if not skip_summary else None,
            "verification_path": verification_path if not skip_summary and not skip_verify else None,
            "qa_path": qa_path if not skip_qa else None,
            "title": title,
        }
    def process_video(
    self,
    video_url: str,
    title: Optional[str] = None,
    output_dir: str = "outputs",
    skip_summary: bool = False,
    skip_qa: bool = False,
    skip_verify: bool = False,
) -> dict:
        os.makedirs(output_dir, exist_ok=True)

        # derive a clean base name from the URL
        safe_name = re.sub(r'[^\w\-]', '_', video_url.split("/")[-1])[:50]
        base_name = f"video_{safe_name}"

        extracted_path   = os.path.join(output_dir, f"{base_name}_extracted.txt")
        summary_path     = os.path.join(output_dir, f"{base_name}_summary.txt")
        qa_path          = os.path.join(output_dir, f"{base_name}_qa.txt")
        verification_path = os.path.join(output_dir, f"{base_name}_verification.txt")

        print(f"\n{'='*60}")
        print(f"Processing video: {video_url}")
        print(f"{'='*60}\n")

        # ── STEP 1: Download → Audio → Transcript ───────────────────────

        audio_path = os.path.join(output_dir, f"{base_name}.m4a")

        print("Downloading audio...")
        self._download_audio(video_url, audio_path)

        print("Transcribing...")
        all_text = self._transcribe_audio(audio_path)

        with open(extracted_path, "w", encoding="utf-8") as f:
            f.write(all_text)
        print(f"✅ Transcript saved to: {extracted_path}")

        # clean up video/audio files to save space
        if os.path.exists(audio_path):
            os.remove(audio_path)

        # ── STEP 2: Summary ─────────────────────────────────────────────
        summary = None
        if not skip_summary:
            print("\nGenerating summary notes...")
            summary = self.summarize_text(all_text, title)
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(summary)
            print(f"✅ Summary saved to: {summary_path}")

        # ── STEP 3: Verification ────────────────────────────────────────
        if not skip_verify and summary:
            print("\nVerifying summary for hallucinations...")
            verification = self._verify_entities(summary, all_text)
            with open(verification_path, "w", encoding="utf-8") as f:
                f.write(verification)
            for line in verification.splitlines():
                if line.strip().startswith("NOT IN SOURCE"):
                    flagged = line.split("NOT IN SOURCE:", 1)[-1].strip()
                    if flagged:
                        print(f"\n⚠️  Potential hallucinations detected:\n{line}")
                    break
            print(f"✅ Verification report saved to: {verification_path}")

        # ── STEP 4: Q&A ─────────────────────────────────────────────────
        qa_pairs = None
        if not skip_qa:
            print("\nGenerating Q&A pairs...")
            qa_pairs = self.generate_qa(all_text)
            with open(qa_path, "w", encoding="utf-8") as f:
                f.write(qa_pairs)
            print(f"✅ Q&A saved to: {qa_path}")

        print(f"\n{'='*60}")
        print(f"✅ Processing complete!")
        print(f"{'='*60}\n")

        return {
            "source_url": video_url,
            "extracted_path": extracted_path,
            "summary_path": summary_path if not skip_summary else None,
            "verification_path": verification_path if not skip_summary and not skip_verify else None,
            "qa_path": qa_path if not skip_qa else None,
            "title": title,
        }

# # ── CLI ─────────────────────────────────────────────────────────────
# if __name__ == "__main__":
#     import sys
#     import argparse
#     from dotenv import load_dotenv
#     load_dotenv()

#     parser = argparse.ArgumentParser(description="Process lecture/book PDF or PPTX.")
#     parser.add_argument("file_path",                    help="Path to PDF or PPTX file")
#     parser.add_argument("page_range",      nargs="?",   help="Page range e.g. 1-10,15,20-25")
#     parser.add_argument("--title",         default=None,help="Title for the notes")
#     parser.add_argument("--output-dir",    default="outputs")
#     parser.add_argument("--skip-extraction", action="store_true",
#                         help="Skip OCR/extraction, load existing extracted text file")
#     parser.add_argument("--skip-summary",    action="store_true",
#                         help="Skip summary generation")
#     parser.add_argument("--skip-qa",         action="store_true",
#                         help="Skip Q&A generation")
#     parser.add_argument("--extracted",       default=None,
#                         help="Path to existing extracted text file (use with --skip-extraction)")
#     parser.add_argument("--skip-verify", action="store_true",
#                     help="Skip hallucination verification step")
#     args = parser.parse_args()
#     parser.add_argument("--video", default=None, help="YouTube or Instagram video URL")

#     # in the execution block:
    
    
#     GROQ_API_KEY = os.getenv("GROQ_API_KEY")
#     processor = LectureProcessor(
#         groq_api_key=GROQ_API_KEY,
#         batch_size=3,
#         dpi=300
#     )
#     if args.video:
#         processor.process_video(
#             video_url=args.video,
#             title=args.title,
#             output_dir=args.output_dir,
#             skip_summary=args.skip_summary,
#             skip_qa=args.skip_qa,
#             skip_verify=args.skip_verify,
#         )
#     else:
#         processor.process(
#             file_path=args.file_path,
#             page_range=args.page_range,
#             output_dir=args.output_dir,
#             title=args.title,
#             skip_extraction=args.skip_extraction,
#             skip_summary=args.skip_summary,
#             skip_qa=args.skip_qa,
#             skip_verify=args.skip_verify,
#             extracted_text_path=args.extracted,
#         )
if __name__ == "__main__":
    import sys
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="Process lecture/book PDF or PPTX.")
    parser.add_argument("file_path",  nargs="?", default=None,  help="Path to PDF or PPTX file")
    parser.add_argument("page_range", nargs="?",                help="Page range e.g. 1-10,15,20-25")
    parser.add_argument("--title",         default=None, help="Title for the notes")
    parser.add_argument("--output-dir",    default="outputs")
    parser.add_argument("--video",         default=None, help="YouTube or Instagram video URL")
    parser.add_argument("--skip-extraction", action="store_true")
    parser.add_argument("--skip-summary",    action="store_true")
    parser.add_argument("--skip-qa",         action="store_true")
    parser.add_argument("--skip-verify",     action="store_true")
    parser.add_argument("--extracted",       default=None)
    args = parser.parse_args()

    if not args.video and not args.file_path:
        parser.error("Provide either a file_path or --video URL.")

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    processor = LectureProcessor(
        groq_api_key=GROQ_API_KEY,
        batch_size=3,
        dpi=300
    )

    if args.video:
        processor.process_video(
            video_url=args.video,
            title=args.title,
            output_dir=args.output_dir,
            skip_summary=args.skip_summary,
            skip_qa=args.skip_qa,
            skip_verify=args.skip_verify,
        )
    else:
        processor.process(
            file_path=args.file_path,
            page_range=args.page_range,
            output_dir=args.output_dir,
            title=args.title,
            skip_extraction=args.skip_extraction,
            skip_summary=args.skip_summary,
            skip_qa=args.skip_qa,
            skip_verify=args.skip_verify,
            extracted_text_path=args.extracted,
        )