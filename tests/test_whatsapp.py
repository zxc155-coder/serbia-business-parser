from __future__ import annotations

from serbia_parser.sources.whatsapp import normalize_phone


def test_normalize_phone_strips_punct_and_keeps_digits():
    assert normalize_phone("+381 (11) 234-5678") == "381112345678"
    assert normalize_phone("+381112345678") == "381112345678"


def test_normalize_phone_local_zero_to_country_code():
    # 06x / 011 local Serbian numbers should become 381... .
    assert normalize_phone("064 123 45 67") == "381641234567"
    assert normalize_phone("011/234-5678") == "3811123456" + "78"


def test_normalize_phone_handles_00_prefix():
    assert normalize_phone("00 381 64 1234567") == "381641234567"


def test_normalize_phone_rejects_too_short():
    assert normalize_phone("123") is None
    assert normalize_phone("") is None
    assert normalize_phone("abc") is None


def test_normalize_phone_rejects_too_long():
    assert normalize_phone("1" * 20) is None
