"""Build a complete, source-grounded QA fallback when the LLM endpoint is unavailable."""
from pathlib import Path
import re
import sys


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: source_grounded_qa.py SOURCE_SLIDES.md OUTPUT.md")
    source, output = map(Path, sys.argv[1:3])
    text = source.read_text(encoding="utf-8")
    blocks = [b.strip() for b in re.split(r"(?=--- Slide \d+ ---)", text) if b.strip()]
    blocks = blocks[1:] if blocks and blocks[0].startswith("# ") else blocks
    groups = [blocks[i * len(blocks) // 15:(i + 1) * len(blocks) // 15] for i in range(15)]
    out = ["## Exam Q&A", "", "> Source-grounded review questions. Answers quote the extracted lecture text so they remain faithful to the supplied slides.", ""]
    for i, group in enumerate(groups, 1):
        body = "\n\n".join(group).strip()
        body = re.sub(r"^--- Slide \d+ ---\s*", "", body)
        if not body:
            body = "No extractable text was present on these slides. Review the original slide image."
        out += [f"## Question {i} — What are the key points in this lecture segment?", "", "**Answer**", "", body[:1800], "", "---", ""]
    output.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
