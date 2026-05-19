from __future__ import annotations

from serbia_parser.pipeline import count_valid, is_valid_contact


def test_is_valid_contact_phone_only() -> None:
    assert is_valid_contact({"phone": "+381 11 234 5678", "email": ""}) is True


def test_is_valid_contact_email_only_is_invalid() -> None:
    # The user requires a phone number; email alone is not enough.
    assert is_valid_contact({"phone": "", "email": "office@example.rs"}) is False


def test_is_valid_contact_empty() -> None:
    assert is_valid_contact({"phone": "", "email": "", "website": "https://x.rs"}) is False
    assert is_valid_contact({}) is False


def test_is_valid_contact_whitespace_only() -> None:
    assert is_valid_contact({"phone": "  \n ", "email": " \t"}) is False


def test_count_valid() -> None:
    rows = [
        {"phone": "1", "email": ""},
        {"phone": "", "email": "x@y.rs"},  # email-only no longer counts
        {"phone": "", "email": ""},
        {"phone": "  ", "email": "  "},
        {"phone": "+381 60 1234567"},
    ]
    assert count_valid(rows) == 2
