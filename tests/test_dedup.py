from serbia_parser.dedup import dedup_records


def test_dedup_by_domain():
    records = [
        {
            "company": "Acme A",
            "website": "https://acme.rs/",
            "phone": "011",
            "source": "ddg",
            "source_url": "u1",
        },
        {
            "company": "Acme B",
            "website": "https://www.acme.rs/contact",
            "phone": "",
            "source": "bing",
            "source_url": "u2",
        },
    ]
    out = dedup_records(records)
    assert len(out) == 1
    assert "ddg" in out[0]["source"] and "bing" in out[0]["source"]
    assert "u1" in out[0]["source_url"] and "u2" in out[0]["source_url"]


def test_dedup_by_phone_when_no_domain():
    records = [
        {"company": "X", "website": "", "phone": "+381 11 1234 567", "source": "a", "source_url": "u1"},
        {"company": "Y", "website": "", "phone": "011 1234567", "source": "b", "source_url": "u2"},
    ]
    out = dedup_records(records)
    assert len(out) == 1


def test_dedup_keeps_unrelated_records():
    records = [
        {"company": "A", "website": "https://a.rs", "source": "x", "source_url": "u1"},
        {"company": "B", "website": "https://b.rs", "source": "x", "source_url": "u2"},
        {"company": "C", "website": "", "phone": "065 111 222", "source": "x", "source_url": "u3"},
    ]
    out = dedup_records(records)
    assert len(out) == 3


def test_dedup_uses_name_when_no_other_identity():
    records = [
        {"company": "Alpha Co", "website": "", "phone": "", "source": "cw", "source_url": "u1"},
        {"company": "alpha CO", "website": "", "phone": "", "source": "cw", "source_url": "u2"},
        {"company": "Beta Co", "website": "", "phone": "", "source": "cw", "source_url": "u3"},
    ]
    out = dedup_records(records)
    # Two distinct names: alpha co (twice) + beta co.
    names = sorted({r["company"].lower() for r in out})
    assert names == ["alpha co", "beta co"]


def test_dedup_falls_back_to_unique_source_url():
    records = [
        {"company": "", "website": "", "phone": "", "source": "x", "source_url": "u1"},
        {"company": "", "website": "", "phone": "", "source": "x", "source_url": "u2"},
    ]
    out = dedup_records(records)
    assert len(out) == 2
