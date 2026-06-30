from backend.app.services.indexing import split_text


def test_split_text_preserves_overlap_and_tail():
    text = "a" * 2200
    chunks = split_text(text, size=1000, overlap=100)
    assert [len(chunk) for chunk in chunks] == [1000, 1000, 400]


def test_empty_text_has_no_chunks():
    assert split_text("   ") == []

