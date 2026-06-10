from kagent.tools.pdf_utils import PDF_MAX_PAGES_PER_READ, parse_pdf_page_range


def test_single_page():
    assert parse_pdf_page_range("3") == (3, 3)


def test_range():
    assert parse_pdf_page_range("1-5") == (1, 5)


def test_range_with_spaces():
    assert parse_pdf_page_range("  1-5  ") == (1, 5)


def test_invalid_non_digit():
    assert parse_pdf_page_range("abc") is None


def test_invalid_reverse():
    assert parse_pdf_page_range("5-1") is None


def test_invalid_zero_single():
    assert parse_pdf_page_range("0") is None


def test_invalid_zero_start():
    assert parse_pdf_page_range("0-5") is None


def test_invalid_empty():
    assert parse_pdf_page_range("") is None
    assert parse_pdf_page_range("   ") is None


def test_invalid_comma_list():
    assert parse_pdf_page_range("1,2,3") is None


def test_invalid_non_string():
    assert parse_pdf_page_range(None) is None  # type: ignore[arg-type]
    assert parse_pdf_page_range(5) is None     # type: ignore[arg-type]


def test_max_pages_constant():
    assert PDF_MAX_PAGES_PER_READ == 20
