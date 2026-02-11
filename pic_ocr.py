import os
import base64
from groq import Groq
from dotenv import load_dotenv
load_dotenv()
# ---------------- CONFIG ----------------
IMAGE_FOLDER = "path/to/images"#replace with your image folder path
OUTPUT_FILE = "pic_text.txt"#replace with your output file path
BATCH_SIZE = 3  # 3–5 is safe
MODEL_NAME = "meta-llama/llama-4-scout-17b-16e-instruct"#replace with your model name

api_key= os.getenv('GROQ_API_KEY')
client = Groq(api_key=api_key)
# ---------------------------------------


def extract_text_from_images(image_paths):
    image_contents = []

    for image_path in image_paths:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
            image_contents.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{b64}"
                }
            })

    messages = [
        {
            "role": "system",
            "content": (
                "You are an OCR model. Extract all text exactly as seen, "
                "preserving layout, equations, and formatting. "
                "DO NOT add any extra symbols like '$'."
            )
        },
        {
            "role": "user",
            "content": [{"type": "text", "text": "Extract text from all these images:"}] + image_contents
        }
    ]

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages
    )

    return response.choices[0].message.content.strip()


# ---------------- LOAD IMAGES ----------------
image_files = sorted([
    os.path.join(IMAGE_FOLDER, f)
    for f in os.listdir(IMAGE_FOLDER)
    if f.lower().startswith("pasted image") and f.lower().endswith(".png")
])

# Ensure "pasted image.png" comes first
image_files.sort(key=lambda x: (x != os.path.join(IMAGE_FOLDER, "pasted image.png"), x))

# ---------------- OCR IN BATCHES ----------------
all_text = ""

for i in range(0, len(image_files), BATCH_SIZE):
    batch = image_files[i:i + BATCH_SIZE]
    extracted = extract_text_from_images(batch)

    all_text += (
        f"\n\n--- Images {i + 1} to {i + len(batch)} ---\n\n"
        f"{extracted}"
    )

# ---------------- SAVE OUTPUT ----------------
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(all_text)

print(f"OCR completed. Text saved to {OUTPUT_FILE}")
