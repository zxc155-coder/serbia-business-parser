import csv
from pathlib import Path

from serbia_parser.storage import FIELDS, HEADERS_RU, is_valid_record, write_csv


def _make(**overrides: str) -> dict:
    base = {
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
    base.update(overrides)
    return base


def test_csv_has_three_russian_columns_in_order():
    """Header row is exactly company / email / phone in Russian."""
    assert FIELDS == ("company", "email", "phone")
    assert [HEADERS_RU[k] for k in FIELDS] == ["компания", "email", "телефон"]


def test_write_csv_default_drops_phoneless_records(tmp_path: Path):
    rows = [
        _make(company="WithPhone", phone="+381 1", email="a@a.rs"),
        # No phone -> filtered out (email alone is no longer enough).
        _make(company="EmailOnly", phone="", email="b@b.rs"),
        _make(company="NothingAtAll", phone="", email=""),
        _make(company="Whitespace", phone="   ", email=""),
    ]
    out = tmp_path / "out.csv"
    n = write_csv(out, rows)
    assert n == 1

    with out.open(encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        data = list(reader)

    assert header == ["компания", "email", "телефон"]
    assert data == [["WithPhone", "a@a.rs", "+381 1"]]


def test_write_csv_emits_only_three_columns(tmp_path: Path):
    """Records carry many fields but only three end up on disk."""
    rows = [_make(company="Acme")]
    out = tmp_path / "out.csv"
    write_csv(out, rows)

    with out.open(encoding="utf-8") as f:
        reader = csv.reader(f)
        rows_out = list(reader)
    # Header + 1 data row, each with exactly 3 columns.
    assert all(len(r) == 3 for r in rows_out)
    assert rows_out[1] == ["Acme", "a@acme.rs", "+381 60 1234567"]


def test_write_csv_only_valid_false_keeps_everything(tmp_path: Path):
    rows = [
        _make(company="WithPhone"),
        _make(company="EmailOnly", phone="", email="x@y.rs"),
        _make(company="NoContact", phone="", email=""),
    ]
    out = tmp_path / "out.csv"
    n = write_csv(out, rows, only_valid=False)
    assert n == 3


def test_is_valid_record_phone_required():
    assert is_valid_record({"phone": "+381"}) is True
    # Email alone is no longer valid.
    assert is_valid_record({"phone": "", "email": "a@b.rs"}) is False
    assert is_valid_record({"phone": "   ", "email": "a@b.rs"}) is False
    assert is_valid_record({}) is False
