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
        self.model = "meta-llama/llama-4-scout-17b-16e-instruct"
    
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
        Extract text from multiple images using Groq vision model.
        
        Args:
            image_paths: List of paths to image files
        
        Returns:
            Extracted text from all images
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
                "content": "You are an OCR model. Extract all text exactly as seen, preserving layout and equations. DO NOT ADD ANY '$' for the equations."
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": "Extract text from all these lecture pages:"}] + image_contents
            }
        ]
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )
        
        return response.choices[0].message.content.strip()
    
    def extract_text_from_files(self, temp_files: List[str], page_indices: List[int]) -> str:
        """
        Extract text from page image files in batches, then delete temp files.
        
        Args:
            temp_files: List of temporary image file paths
            page_indices: Original page numbers (for labeling)
        
        Returns:
            Combined text from all pages
        """
        all_text = ""
        
        print(f"Extracting text in batches of {self.batch_size}...")
        for i in range(0, len(temp_files), self.batch_size):
            batch_files = temp_files[i:i+self.batch_size]
            batch_pages = page_indices[i:i+len(batch_files)]
            
            print(f"Processing batch: pages {[p+1 for p in batch_pages]}")
            extracted = self.extract_text_from_images(batch_files)
            
            page_label = f"Pages {batch_pages[0]+1} to {batch_pages[-1]+1}" if len(batch_pages) > 1 else f"Page {batch_pages[0]+1}"
            all_text += f"\n\n--- {page_label} ---\n\n{extracted}"
        
        print("Cleaning up temporary files...")
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        
        return all_text
    
    def summarize_text(self, text: str, title: Optional[str] = None) -> str:
        """
        Generate Notion-ready summary notes from extracted text.
        
        Args:
            text: Extracted text from pages
            title: Optional title for the notes
        
        Returns:
            Formatted summary notes
        """
        title_prompt = f"\n\nTitle: {title}" if title else ""
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert academic note maker who specializes in creating clear, structured, "
                        "and comprehensive university-level notes for any subject. You format notes perfectly "
                        "for Notion using Markdown, with strong organization, readability, and technical accuracy. "
                        "Always retain all key details, definitions, formulas, and examples."
                    )
                },
                {
                    "role": "user",
                    "content": f"""
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

Now format the following text into Notion-style university notes:{title_prompt}

{text}
"""
                }
            ]
        )
        
        return response.choices[0].message.content.strip()
    
    def generate_qa(self, text: str, num_questions: int = 10) -> str:
        """
        Generate Q&A pairs from text.
        
        Args:
            text: Text to generate questions from
            num_questions: Number of questions to generate
        
        Returns:
            Formatted Q&A pairs
        """
        response = self.client.chat.completions.create(
            model=self.model,
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
    
    def process(
        self, 
        file_path: str, 
        page_range: Optional[str] = None,
        output_dir: str = "outputs",
        title: Optional[str] = None
    ) -> dict:
        """
        Full processing pipeline: convert -> extract -> summarize -> generate Q&A.
        
        Args:
            file_path: Path to PDF or PPTX file
            page_range: Page range string (e.g., "1-10,15") or None for all
            output_dir: Directory to save output files
            title: Optional title for the notes
        
        Returns:
            Dictionary with paths to generated files and metadata
        """
        print(f"\n{'='*60}")
        print(f"Processing: {file_path}")
        if page_range:
            print(f"Page range: {page_range}")
        print(f"{'='*60}\n")
        
        temp_files, page_indices = self.convert_pages_to_files(file_path, page_range)
        
        print("\nExtracting text from images...")
        all_text = self.extract_text_from_files(temp_files, page_indices)
        
        print("\nGenerating summary notes...")
        summary = self.summarize_text(all_text, title)
        
        print("\nGenerating Q&A pairs...")
        qa_pairs = self.generate_qa(all_text)
        
        os.makedirs(output_dir, exist_ok=True)
        
        base_name = Path(file_path).stem
        if page_range:
            page_range_clean = page_range.replace(',', '_').replace('-', 'to')
            base_name += f"_pages_{page_range_clean}"
        
        extracted_path = os.path.join(output_dir, f"{base_name}_extracted.txt")
        summary_path = os.path.join(output_dir, f"{base_name}_summary.txt")
        qa_path = os.path.join(output_dir, f"{base_name}_qa.txt")
        
        with open(extracted_path, "w", encoding="utf-8") as f:
            f.write(all_text)
        
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary)
        
        with open(qa_path, "w", encoding="utf-8") as f:
            f.write(qa_pairs)
        
        print(f"\n{'='*60}")
        print(f"✅ Processing complete!")
        print(f"{'='*60}")
        print(f"Extracted text: {extracted_path}")
        print(f"Summary notes:  {summary_path}")
        print(f"Q&A pairs:      {qa_path}")
        print(f"{'='*60}\n")
        
        return {
            "source_file": file_path,
            "page_range": page_range,
            "pages_processed": [i+1 for i in page_indices],
            "total_pages": len(page_indices),
            "extracted_text_path": extracted_path,
            "summary_path": summary_path,
            "qa_path": qa_path,
            "title": title
        }


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    
    processor = LectureProcessor(
        groq_api_key=GROQ_API_KEY,
        batch_size=3,
        dpi=300
    )
    
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        page_range = sys.argv[2] if len(sys.argv) > 2 else None
        
        result = processor.process(
            file_path=file_path,
            page_range=page_range,
            output_dir="outputs"
        )
    else:
        print("Usage: python processor.py <file_path> [page_range]")
        print("\nExamples:")
        print("  python processor.py lecture.pdf")
        print("  python processor.py book.pdf 45-67")
        print("  python processor.py slides.pptx 1-10,15,20-25")
        print("  python processor.py textbook.pdf 1-50")