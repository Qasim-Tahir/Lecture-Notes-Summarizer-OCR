from classroom_ingest import is_google_attachment, safe_name


def test_google_attachment_hosts():
    assert is_google_attachment("https://drive.google.com/file/d/abc/view")
    assert is_google_attachment("https://docs.google.com/presentation/d/abc/edit")
    assert not is_google_attachment("https://classroom.google.com/c/abc")
    assert not is_google_attachment("https://evil.example/drive.google.com/file")


def test_safe_name():
    assert safe_name('lecture:/week?.pdf') == "lecture__week_.pdf"
    assert safe_name("  ") == "attachment"
