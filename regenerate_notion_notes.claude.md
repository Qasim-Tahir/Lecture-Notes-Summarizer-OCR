# regenerate_notion_notes.py — AI Reference & Architecture Guide

## 1. Overview & Purpose
`regenerate_notion_notes.py` is a specialized post-processing and generation tool designed to produce academic lecture notes and comprehensive exam Q&As that render perfectly inside **Notion**.

Standard Markdown output from LLMs often breaks Notion's Markdown parser, particularly when handling:
- Inline mathematical equations (`$x$` or `\(x\)` rendering as broken plain text).
- Display equations (`\[...\]` or `\begin{equation}`).
- Pipe characters (`|`) inside table cells containing conditional probability notation like $P(x|y)$ destroying table column alignments.
- Token truncation during 15-question Q&A generation causing skipped question numbers.

This script enforces the project's Notion syntax rules, normalizes common delimiters, and generates Q&A in configurable batches. Provider limits can still produce empty or truncated responses, so validate the output before publication.

---

## 2. Input Types & Requirements

### Inputs
- **Source Markdown Files (`source_slides.md`)**:
  - Delimited with `--- Slide N ---` markers (typically produced by [robust_lecture_notes.py](file:///media/giga-niga/b5bedfd4-42da-dc01-b0ba-ddd442dadc01/projects/Upwork/RAG/OCR/robust_lecture_notes.claude.md) or [extract_lecture_sources.py](file:///media/giga-niga/b5bedfd4-42da-dc01-b0ba-ddd442dadc01/projects/Upwork/RAG/OCR/extract_lecture_sources.claude.md)).
- **Existing `notion_notes.md` / `exam_qa.md` files**:
  - When running with `--normalize-only` or `--qa-only`.

### Prerequisites
- Python libraries: `groq`, `python-dotenv`, `pathlib`.
- Environment: `GROQ_API_KEY` set in `.env` or system environment.

---

## 3. Notion Syntax Specification & Math Normalization

The script implements `normalize_notion_math(text: str)`, which guarantees the following syntax:

| Syntax Type | Standard / LLM Output | Notion-Required Output | Transformation in Script |
| :--- | :--- | :--- | :--- |
| **Inline Math** | `\(x\)` or `$x$` | Dollar + backtick + expression + backtick + dollar | Converted to the project's Notion inline syntax |
| **Display Math** | `\[ x^2 \]` or `\begin{equation}` | `$$\nx^2\n$$` | Converted to block `$$\n...\n$$` |
| **Pipes in Math** | `$P(x \mid y)$` | Inline Notion math with `\mid` | A math pipe becomes `\mid` so it cannot break a Markdown table |
| **Subscripts** | `<sub>i</sub>` | `_i` | Strips HTML tags to Markdown |
| **Table Equations** | Cells with complex math | Bullet list conversion | Prevents table corruption |
| **Bold Spans** | Bold text touching math delimiters | Bold text followed by separate inline math | Math is moved outside bold spans |
| **Trailing Backticks**| An extra backtick after inline math | One correctly closed inline expression | Cleans duplicate model backticks |

---

## 4. Architecture & Workflow

```
source_slides.md
       │
       ├──► [slide_segments()] (Splits into ~5,500-char blocks at slide boundaries)
       │
       ├──► [Notes Generation] (Groq LLM with NOTES_PROMPT + NOTION_RULES)
       │       - Uses `###` and `####` headings
       │       - Preserves formulas, comparisons, derivations
       │       - Merges into: ## Overview, ## Key Concepts, ## Summary
       │       - Saves to outputs/<title>/notion_notes.md
       │
       └──► [Batched Q&A Generation]
               - Total target: 15 university-level conceptual questions
               - Batched into chunks of 2 questions per prompt (`--qa-batch-size 2`)
               - Reduces, but does not guarantee, model token-cap truncation and missing questions
               - Normalizes each batch via normalize_notion_math()
               - Saves to outputs/<title>/exam_qa.md
```

---

## 5. Key Functions

- **`normalize_notion_math(text: str) -> str`**:
  - Splits text by fenced code blocks (` ```...``` `) to protect code from accidental math replacement.
  - Normalizes inline math, display math, conditional probability pipes, and HTML tags.
- **`complete(client, model, system, user, max_tokens) -> str`**:
  - Executes chat completion against Groq API and immediately filters the output through `normalize_notion_math`.
- **`slide_segments(raw: str, limit: int = 6_500) -> list[str]`**:
  - Partitions slide text into coherent chunks without splitting individual slides.
- **`main()`**:
  - CLI parser and orchestrator supporting full generation, `--qa-only`, or `--normalize-only`.

---

## 6. CLI Usage & Flags

```bash
# Full generation (Notes + 15 Q&As) from pre-extracted slides
python regenerate_notion_notes.py outputs/raw/lecture1/source_slides.md \
    --output-dir outputs/notion_final

# Process multiple lectures in batch
python regenerate_notion_notes.py \
    outputs/raw/lec1/source_slides.md \
    outputs/raw/lec2/source_slides.md \
    --output-dir outputs/notion_final

# Regenerate only the 15 Q&As (using existing notion_notes.md in output-dir)
python regenerate_notion_notes.py outputs/raw/lecture1/source_slides.md \
    --output-dir outputs/notion_final \
    --qa-only

# Adjust Q&A batch size (default: 2 questions per request to avoid truncation)
python regenerate_notion_notes.py outputs/raw/lecture1/source_slides.md \
    --qa-batch-size 3

# Fast offline normalization without calling Groq (cleans up existing markdown)
python regenerate_notion_notes.py outputs/raw/lecture1/source_slides.md \
    --output-dir outputs/notion_final \
    --normalize-only

# Specify a custom Groq model
python regenerate_notion_notes.py outputs/raw/lecture1/source_slides.md \
    --model openai/gpt-oss-120b
```

---

## 7. AI Agent Guidelines & Troubleshooting
- **Empty Output Error**: If Groq returns empty content (`RuntimeError: Groq returned empty content`), check if the model endpoint is overloaded. Reduce `--qa-batch-size` or switch to another supported Groq model.
- **Notion Math Display**: When verifying output in Notion, check that inline formulas use a dollar sign, backtick, expression, backtick, dollar sign sequence. If testing syntax changes, run the direct assertion command in `test_notion_format.claude.md`.
