"""Regenerate lecture notes in a Notion-safe format.

This keeps the original lecture_notes.py prompt structure, but adds the
Notion-flavored Markdown rules that the old generic Markdown prompt lacked.
Each lecture is processed as one document so sections and QA do not get
duplicated or mixed across chunk boundaries.
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq


NOTION_RULES = """
NOTION OUTPUT RULES (mandatory):
- Return only the requested document body; do not add commentary.
- Use headings, bullets, numbered lists, and Markdown tables.
- For inline equations use exactly $`LaTeX equation`$.
- For display equations use exactly:
  $$
  LaTeX equation
  $$
- Never use \\( ... \\), \\[ ... \\], HTML tags such as <sub>, or raw LaTeX outside an equation block.
- Never put a pipe character | inside a table cell; use \\mid inside equations instead.
- Put code only inside fenced code blocks with a language such as ```python.
- Do not put math delimiters inside bold or italic spans; bold only plain words.
- Do not use a heading level above the requested structure and do not repeat the lecture title.
"""


NOTES_PROMPT = """You are an expert academic note maker who specializes in clear, structured, comprehensive university-level notes. Format the result for direct reading in Notion, preserving important definitions, formulas, examples, derivations, and comparisons.

This is one segment of a larger lecture. Create a self-contained notes fragment. Use `###` and `####` headings for topics in this segment; do not repeat the lecture title or add `#`/`##` headings.

Use concise explanations, but do not omit important lecture content. Use tables for comparisons and show equations and numeric reasoning clearly.

""" + NOTION_RULES


QA_PROMPT = """You are a university professor creating exam-style questions from a lecture.
Generate 15 conceptual questions with concise but accurate answers. Cover definitions, mechanisms, formulas, derivations, examples, comparisons, and practical implications. Use this structure:
## Question 1 — ...
**Answer**
...

Continue through Question 15. Keep each answer focused and complete, normally under 100 words. Do not include an introduction or conclusion outside the questions.

""" + NOTION_RULES


def normalize_notion_math(text: str) -> str:
    """Convert common generic-Markdown/LaTeX delimiters to Notion syntax."""
    chunks = re.split(r"(```.*?```)", text, flags=re.S)
    for index, chunk in enumerate(chunks):
        if chunk.startswith("```"):
            continue
        # Tables containing inline equations are frequently emitted with an
        # extra backtick around the cell delimiter. Convert those rows to
        # readable bullets before equation normalization; this avoids Notion
        # treating the equation delimiters as literal table text.
        cleaned_lines = []
        for line in chunk.splitlines():
            if line.lstrip().startswith("|") and line.rstrip().endswith("|"):
                cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
                if cells and not all(set(cell) <= {"-", ":", " "} for cell in cells):
                    cleaned_lines.append("- " + " — ".join(cells))
                continue
            cleaned_lines.append(line)
        chunk = "\n".join(cleaned_lines)
        chunk = re.sub(r"\\\[(.*?)\\\]", lambda m: "$$\n" + m.group(1).strip() + "\n$$", chunk, flags=re.S)
        chunk = re.sub(r"\\\((.*?)\\\)", lambda m: "$`" + m.group(1).strip().replace("|", r" \mid ") + "`$", chunk, flags=re.S)
        chunk = re.sub(r"<sub>(.*?)</sub>", r"_\1", chunk, flags=re.S)
        chunk = re.sub(r"</?sup>", "", chunk)
        # Repair the common model form $`x`$` (one trailing backtick too many).
        chunk = re.sub(r"\$`([^`\n]+)`\$`", r"$`\1`$", chunk)
        # Keep math outside bold spans; Notion otherwise turns the delimiters
        # into literal text (for example **term **$`x`$).
        chunk = re.sub(r"\*\*([^*\n]+?)\s+\*\*\$`", r"**\1** $`", chunk)
        chunk = chunk.replace("\\begin{equation}", "$$").replace("\\end{equation}", "$$")
        # Notion's inline equation syntax is $`...`$, not generic Markdown $...$.
        chunk = re.sub(r"(?<!\$)\$(?!\$|`)([^$\n]+?)(?<!`)\$(?!\$)", lambda m: "$`" + m.group(1).replace("|", r" \mid ") + "`$", chunk)
        chunks[index] = chunk
    return "".join(chunks).strip() + "\n"


def complete(client: Groq, model: str, system: str, user: str, max_tokens: int) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("Groq returned empty content")
    return normalize_notion_math(content)


def slide_segments(raw: str, limit: int = 6_500) -> list[str]:
    blocks = [block.strip() for block in raw.split("\n--- Slide ") if block.strip()]
    segments: list[str] = []
    current: list[str] = []
    size = 0
    for block in blocks:
        block = ("--- Slide " + block) if not block.startswith("--- Slide ") else block
        if current and size + len(block) + 2 > limit:
            segments.append("\n\n".join(current))
            current, size = [], 0
        current.append(block)
        size += len(block) + 2
    if current:
        segments.append("\n\n".join(current))
    return segments


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/notion-regenerated"))
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    parser.add_argument("--qa-only", action="store_true")
    parser.add_argument("--normalize-only", action="store_true")
    parser.add_argument("--qa-batch-size", type=int, default=2)
    args = parser.parse_args()
    load_dotenv()
    import os
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise SystemExit("GROQ_API_KEY is missing")
    client = Groq(api_key=api_key)

    for source in args.sources:
        title = source.parent.name
        raw = source.read_text(encoding="utf-8")
        # Remove the generated file title; keep slide labels as provenance.
        raw = raw.split("\n", 2)[-1]
        out = args.output_dir / title
        out.mkdir(parents=True, exist_ok=True)
        if args.normalize_only:
            for name in ("notion_notes.md", "exam_qa.md"):
                path = out / name
                if path.exists():
                    path.write_text(normalize_notion_math(path.read_text(encoding="utf-8")), encoding="utf-8")
            print(f"Normalized {out}", flush=True)
            continue
        if args.qa_only:
            notes = (out / "notion_notes.md").read_text(encoding="utf-8")
        else:
            print(f"Generating notes: {title}", flush=True)
            fragments = []
            for index, segment in enumerate(slide_segments(raw, limit=5_500), start=1):
                print(f"  notes segment {index}", flush=True)
                fragments.append(complete(client, args.model, NOTES_PROMPT, segment, 2600))
                time.sleep(2)
            notes = "## Overview / Objectives\n\nGenerated from the lecture slides.\n\n## Key Concepts and Detailed Explanation\n\n" + "\n\n---\n\n".join(fragments) + "\n\n## Summary / Takeaways\n\nReview the definitions, equations, examples, and comparisons above.\n"
        print(f"Generating QA: {title}", flush=True)
        qa_parts = []
        batch_count = (15 + args.qa_batch_size - 1) // args.qa_batch_size
        segments = [notes[i * len(notes) // batch_count:(i + 1) * len(notes) // batch_count] for i in range(batch_count)]
        for index, segment in enumerate(segments):
            start = index * args.qa_batch_size + 1
            end = min(15, start + args.qa_batch_size - 1)
            count = end - start + 1
            prompt = QA_PROMPT.replace("Generate 15 conceptual questions", f"Generate exactly Questions {start}–{end} ({count} total)")
            qa_parts.append(complete(client, args.model, prompt, segment, 900))
            time.sleep(2)
        qa = "\n\n---\n\n".join(qa_parts)
        (out / "notion_notes.md").write_text(notes, encoding="utf-8")
        (out / "exam_qa.md").write_text(qa, encoding="utf-8")
        print(f"Wrote {out}", flush=True)


if __name__ == "__main__":
    main()
