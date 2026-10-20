from regenerate_notion_notes import normalize_notion_math


def test_normalize_inline_math():
    assert normalize_notion_math(r"Use \(D(x|y)\).") == "Use $`D(x \\mid y)`$.\n"


def test_normalize_display_math():
    result = normalize_notion_math(r"\[x^2 + y^2\]")
    assert result == "$$\nx^2 + y^2\n$$\n"


def test_preserve_code_and_normalize_plain_dollars():
    result = normalize_notion_math("x $y^2$\n```python\nprint('$literal$')\n```")
    assert "x $`y^2`$" in result
    assert "print('$literal$')" in result
