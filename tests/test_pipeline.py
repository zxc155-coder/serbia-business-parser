from __future__ import annotations

from serbia_parser.pipeline import count_valid, is_valid_contact


def test_is_valid_contact_phone_only() -> None:
    assert is_valid_contact({"phone": "+381 11 234 5678", "email": ""}) is True


def test_is_valid_contact_email_only() -> None:
    assert is_valid_contact({"phone": "", "email": "office@example.rs"}) is True


def test_is_valid_contact_empty() -> None:
    assert is_valid_contact({"phone": "", "email": "", "website": "https://x.rs"}) is False
    assert is_valid_contact({}) is False


def test_is_valid_contact_whitespace_only() -> None:
    assert is_valid_contact({"phone": "  \n ", "email": " \t"}) is False


def test_count_valid() -> None:
    rows = [
        {"phone": "1", "email": ""},
        {"phone": "", "email": "x@y.rs"},
        {"phone": "", "email": ""},
        {"phone": "  ", "email": "  "},
    ]
    assert count_valid(rows) == 2
