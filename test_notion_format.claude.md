# test_notion_format.py — AI Reference & Test Guide

## 1. Overview & Purpose
`test_notion_format.py` provides regression test coverage for the math and Markdown normalization functions implemented in [regenerate_notion_notes.py](file:///media/giga-niga/b5bedfd4-42da-dc01-b0ba-ddd442dadc01/projects/Upwork/RAG/OCR/regenerate_notion_notes.claude.md).

It verifies conversion to the project's Notion inline format, `$` + backtick + expression + backtick + `$`, and display `$$` blocks. It also checks that conditional-probability pipe symbols become `\mid` and dollar signs inside code blocks remain unchanged.

---

## 2. Test Cases Covered

### 1. `test_normalize_inline_math()`
- **Input**: `r"Use \(D(x|y)\)."`
- **Expected Output**: `"Use $`D(x \\mid y)`$.\n"`
- **Verifies**:
  - `\(` and `\)` convert to Notion inline math delimiters.
  - Pipe `|` inside an equation becomes `\mid` so it does not collide with Markdown table syntax.

### 2. `test_normalize_display_math()`
- **Input**: `r"\[x^2 + y^2\]"`
- **Expected Output**: `"$$\nx^2 + y^2\n$$\n"`
- **Verifies**:
  - `\[` and `\]` convert to standalone display math blocks surrounded by `$$`.

### 3. `test_preserve_code_and_normalize_plain_dollars()`
- **Input**: `"x $y^2$\n```python\nprint('$literal$')\n```"`
- **Expected Output**: Checks that `"x $`y^2`$"` is created for the math segment, while `"print('$literal$')"` inside the fenced Python block remains untouched.
- **Verifies**:
  - Code fence boundary protection (`re.split(r"(```.*?```)", ...)`) prevents corrupting shell scripts, Python variables, or strings that contain dollar signs.

---

## 3. Execution Commands

The test file contains plain assertion functions and does not require pytest. Run it with:
```bash
python -c "import test_notion_format as t; t.test_normalize_inline_math(); t.test_normalize_display_math(); t.test_preserve_code_and_normalize_plain_dollars(); print('Notion format tests passed')"
```

Or execute directly:
```bash
python -c "import test_notion_format; test_notion_format.test_normalize_inline_math(); test_notion_format.test_normalize_display_math(); test_notion_format.test_preserve_code_and_normalize_plain_dollars(); print('Notion format tests passed!')"
```

---

## 4. Maintenance Notes
Whenever modifying `NOTION_RULES` or regex replacement patterns in `regenerate_notion_notes.py`, always run this test file first to ensure no regressions occur in code fence isolation or delimiter formatting.
