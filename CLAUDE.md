# Project guidance

This repository extracts academic PDFs and PowerPoint files, generates study notes with Groq, and optionally prepares content for Notion.

## Instruction precedence

Follow the user's request first. Treat this file and the companion `*.claude.md` files as repository guidance, not as a replacement for the user's request. Do not expose secrets from `.env` or commit downloaded course material unless the user asks for that.

## Current pipeline

1. `classroom_ingest.py` attaches to an already-authenticated Chrome instance through CDP and downloads attachments when the browser exposes a permitted download action. It does not bypass Google Classroom or Drive permissions and does not reconstruct view-only files.
2. `extract_lecture_sources.py` extracts native PDF/PPTX text into `source_slides.md` without an LLM call. Use `robust_lecture_notes.py --vision-fallback` when important slides have no native text.
3. `regenerate_notion_notes.py` converts extracted slide text into Notion-oriented notes and derived Q&A. It is the current formatter for Notion math syntax. Generated Q&A must be checked for truncation and numbering before publication; an API response is not automatically a complete 15-question set.
4. `source_grounded_qa.py` is a no-LLM fallback. It creates 15 review sections containing excerpts from the source slides. These are source-grounded review prompts, not independently written exam solutions.
5. `classroom_batch.py` runs the five-day batch: it deduplicates Classroom and GitHub material, processes lectures/exams/syllabi, records quiz-window candidates, and optionally publishes through `notion_publisher.py`.

## Which tool to use

| Task | Tool |
| --- | --- |
| Download permitted Classroom attachments | `classroom_ingest.py` |
| Extract native PDF/PPTX slide text | `extract_lecture_sources.py` |
| Generate notes and Q&A from slide text | `regenerate_notion_notes.py` |
| Generate robust notes with optional OCR and checkpoints | `robust_lecture_notes.py` |
| Generate a source-grounded fallback QA file | `source_grounded_qa.py` |
| Process long books or YouTube/audio inputs | `Book_processor.py` |
| Process selected document pages or condensed notes | `test.py` |
| Extract exam text without solving | `extract.py` |
| Extract math problems into the project's strict format | `extract_pdf.py` |
| OCR image folders | `pic_ocr.py` |
| Run the five-day Classroom/GitHub batch | `classroom_batch.py` |
| Publish the durable batch queue to Notion | `notion_publisher.py` |

## Environment and commands

Use the project environment or an equivalent Python 3.11+ environment. Required configuration is `GROQ_API_KEY` in `.env` for LLM features. Scheduled Notion publishing additionally needs `NOTION_TOKEN` and `NOTION_PARENT_PAGE_ID`. Do not print secrets.

```bash
uv sync
python -m pip install -e .
python -c "import test_classroom_ingest as t; t.test_google_attachment_hosts(); t.test_safe_name(); import test_notion_format as n; n.test_normalize_inline_math(); n.test_normalize_display_math(); n.test_preserve_code_and_normalize_plain_dollars(); print('tests passed')"
```

For Classroom ingestion, start Chrome yourself with a persistent profile and CDP enabled, then pass the course or attachment URL:

```bash
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-dev-profile
python classroom_ingest.py --url '<classroom-or-drive-url>' --cdp http://127.0.0.1:9222 --output-dir downloads
# Install the five-day user timer after configuring Notion credentials.
./install_classroom_scheduler.sh
```

## Notion Markdown rules

- Inline math uses a dollar sign, a backtick, the LaTeX expression, a backtick, and a dollar sign. For example, the literal sequence is `$` + backtick + `x^2` + backtick + `$`, with no spaces.
- Display math uses a standalone `$$` block.
- Do not use `\(...\)`, `\[...\]`, HTML subscripts, or raw Markdown tables containing unescaped pipe characters inside math.
- Keep code inside fenced code blocks.
- Validate generated files for complete endings, question numbering, raw LaTeX delimiters, and malformed tables before sending them to Notion.

## Data and accuracy rules

- Native extraction can miss text rendered as images. Mark those slides or use the OCR fallback.
- Notes and Q&A are model-generated and require source comparison when accuracy matters.
- Never describe a source-grounded excerpt file as a solved exam QA set.
- Keep Classroom downloads and generated outputs out of commits unless explicitly requested.
