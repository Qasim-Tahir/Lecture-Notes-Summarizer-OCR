from pdf2image import convert_from_path
import os
from pathlib import Path
import dotenv
from dotenv import load_dotenv
dotenv.load_dotenv()

def convert_pptx_to_pdf(pptx_path):
    """Convert PPTX to PDF using LibreOffice"""
    output_dir = os.path.dirname(pptx_path)
    cmd = f'libreoffice --headless --convert-to pdf --outdir "{output_dir}" "{pptx_path}"'
    os.system(cmd)
    pdf_path = str(Path(pptx_path).with_suffix('.pdf'))
    return pdf_path

def process_file(file_path):
    file_ext = Path(file_path).suffix.lower()
    
    if file_ext == '.pdf':
        pages = convert_from_path(file_path, dpi=300)
    elif file_ext in ['.pptx', '.ppt']:
        # Convert to PDF first
        pdf_path = convert_pptx_to_pdf(file_path)
        pages = convert_from_path(pdf_path, dpi=300)
    else:
        raise ValueError(f"Unsupported file format: {file_ext}")
    
    return pages

# Usage
pages = process_file("Lecture7 & 8 Event loop + DOM + Jquery.pptx.pdf")
for i, page in enumerate(pages):
    page.save(f"page_{i+1}.png", "PNG")


from groq import Groq
import base64

api_key= os.getenv('GROQ_API_KEY')
client = Groq(api_key=api_key)

def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

# def extract_text_from_image(image_path):
#     image_b64 = encode_image(image_path)

#     response = client.chat.completions.create(
#     model="meta-llama/llama-4-scout-17b-16e-instruct",
#     messages=[
#             {
#                 "role": "system",
#                 "content": "You are an OCR model. Extract all text from the image exactly as seen, preserving layout, equations, formulas and formatting."
#             },
#             {
#                 "role": "user",
#                 "content": [
#                     {
#                         "type": "text",
#                         "text": "Extract all text from this lecture image."
#                     },
#                     {
#                         "type": "image_url",
#                         "image_url": {
#                             "url": f"data:image/png;base64,{image_b64}"
#                         }
#                     }
#                 ]
#             }
#         ]
#     )
#     return response.choices[0].message.content.strip()
def extract_text_from_images(image_paths):
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

    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",#replace with your model name
        messages=messages
    )

    return response.choices[0].message.content.strip()


# all_text = ""
# for i in range(len(pages)):
#     extracted = extract_text_from_image(f"page_{i+1}.png")
#     all_text += f"\n\n--- Page {i+1} ---\n\n{extracted}"

#replace with your batch size
BATCH_SIZE = 3  # try 3–5 depending on image size
all_text = ""

for i in range(0, len(pages), BATCH_SIZE):
    batch_files = [f"page_{j+1}.png" for j in range(i, min(i + BATCH_SIZE, len(pages)))]
    extracted = extract_text_from_images(batch_files)
    all_text += f"\n\n--- Pages {i+1} to {i+len(batch_files)} ---\n\n{extracted}"


def summarize_text(text):
    response = client.chat.completions.create(
    model="meta-llama/llama-4-scout-17b-16e-instruct",#replace with your model name
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

Now format the following text into Notion-style university notes:

{text}
"""
            }
        ]
    )

    return response.choices[0].message.content.strip()

summary = summarize_text(all_text)



def generate_qa(text):
    response = client.chat.completions.create(
    model="meta-llama/llama-4-scout-17b-16e-instruct",        messages=[
            {"role": "system", "content": "You are a university professor creating exam-style questions.### 🎯 OBJECTIVE:Produce **Notion-optimized academic notes** that:- Are structured, readable, and professional- Preserve every important concept, formula, and example- Work across **all subjects and course types**- Are immediately ready for pasting into Notion with no further editing.- Show all numeric steps, equations, and logic clearly.- Use tables for comparisons or results. If the question requires code, provide code snippet."},
            {"role": "user", "content": f"Generate 15 conceptual questions and their detailed answers from the following lecture text:\n\n{text}"}
        ]
    )
    return response.choices[0].message.content.strip()

qa_pairs = generate_qa(all_text)



with open("extracted_text.txt", "w", encoding="utf-8") as f:
    f.write(all_text)

with open("summary_notes.txt", "w", encoding="utf-8") as f:
    f.write(summary)

with open("qa_pairs.txt", "w", encoding="utf-8") as f:
    f.write(qa_pairs)
