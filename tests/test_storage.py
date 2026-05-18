import csv
from pathlib import Path

from serbia_parser.storage import FIELDS, write_csv


def test_write_csv_round_trip(tmp_path: Path):
    rows = [
        {
            "category": "Тест",
            "company": "Acme",
            "website": "https://acme.rs/",
            "phone": "+381",
            "email": "a@acme.rs",
            "address": "Ulica 1",
            "city": "Beograd",
            "social": "",
            "description": "Test",
            "source": "ddg",
            "source_url": "https://example.com/1",
        },
        # Extra unknown field should be silently dropped.
        {"company": "Other", "unknown_field": "x"},
    ]
    out = tmp_path / "out.csv"
    n = write_csv(out, rows)
    assert n == 2
    with out.open() as f:
        reader = csv.DictReader(f)
        loaded = list(reader)
    assert [r["company"] for r in loaded] == ["Acme", "Other"]
    assert set(loaded[0].keys()) == set(FIELDS)
