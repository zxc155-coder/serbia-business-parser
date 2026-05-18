import csv
from pathlib import Path

from serbia_parser.storage import FIELDS, HEADERS_RU, is_valid_record, write_csv

SAMPLE_VALID = {
    "category": "Тест",
    "company": "Acme",
    "website": "https://acme.rs/",
    "phone": "+381 60 1234567",
    "email": "a@acme.rs",
    "address": "Ulica 1",
    "city": "Beograd",
    "social": "",
    "description": "Test",
    "source": "ddg",
    "source_url": "https://example.com/1",
}


def test_write_csv_default_drops_invalid_and_uses_russian_headers(tmp_path: Path):
    rows = [
        SAMPLE_VALID,
        # No phone, no email -> filtered out by default.
        {"company": "NoContact", "website": "https://nope.rs/"},
        # Only email -> still valid.
        {"company": "EmailOnly", "email": "x@y.rs"},
        # Whitespace-only -> still invalid.
        {"company": "Whitespace", "phone": "   ", "email": ""},
    ]
    out = tmp_path / "out.csv"
    n = write_csv(out, rows)
    assert n == 2

    with out.open(encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        data = list(reader)

    # Header row is in Russian, in the same order as FIELDS.
    assert header == [HEADERS_RU[k] for k in FIELDS]
    assert [row[FIELDS.index("company")] for row in data] == ["Acme", "EmailOnly"]


def test_write_csv_only_valid_false_keeps_everything(tmp_path: Path):
    rows = [SAMPLE_VALID, {"company": "NoContact"}]
    out = tmp_path / "out.csv"
    n = write_csv(out, rows, only_valid=False)
    assert n == 2

    with out.open(encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # header
        data = list(reader)
    assert [row[FIELDS.index("company")] for row in data] == ["Acme", "NoContact"]


def test_is_valid_record():
    assert is_valid_record({"phone": "+381"}) is True
    assert is_valid_record({"email": "a@b.rs"}) is True
    assert is_valid_record({"phone": "", "email": "  "}) is False
    assert is_valid_record({}) is False
