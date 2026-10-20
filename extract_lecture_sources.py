"""Extract slide text into the source format used by the Notion generator."""
from pathlib import Path
import sys

from robust_lecture_notes import Slide, extract_pptx_text, slide_blocks


def extract_pdf(path: Path) -> list[Slide]:
    from PyPDF2 import PdfReader
    reader = PdfReader(str(path))
    return [Slide(i, page.extract_text() or "[This slide contains no extractable text.]")
            for i, page in enumerate(reader.pages, 1)]


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: extract_lecture_sources.py OUTPUT_DIR FILE...")
    output = Path(sys.argv[1])
    for raw in sys.argv[2:]:
        path = Path(raw)
        slides = extract_pptx_text(path) if path.suffix.lower() == ".pptx" else extract_pdf(path)
        target = output / path.stem / "source_slides.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        title = path.stem.replace("_", " ")
        target.write_text(f"# {title}\n\n" + "\n\n".join(slide_blocks(slides)) + "\n", encoding="utf-8")
        print(f"{target}: {len(slides)} slides")


if __name__ == "__main__":
    main()
