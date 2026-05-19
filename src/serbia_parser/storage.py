"""CSV storage for business records.

The on-disk CSV uses Russian column headers so the file is immediately
useful to the end user (they consume the file in Excel/Google Sheets,
not the code). Internal record dicts continue to key by the English
identifiers below; the writer maps those to the Russian headers when
emitting rows.

The user has explicitly asked the file to only contain companies that
have a phone number, and to only show the company name, email, and
phone columns — so by default `write_csv` filters records to those
with a phone and emits only those three columns.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

# Internal record keys (used everywhere in code). The pipeline still
# builds rich dicts; the CSV writer only emits a subset of these columns.
FIELDS = (
    "company",
    "email",
    "phone",
)

# Russian column headers — only used at CSV write time.
HEADERS_RU = {
    "company": "компания",
    "email": "email",
    "phone": "телефон",
}


def is_valid_record(row: dict) -> bool:
    """A record is exportable when it has a phone number.

    The user has asked the bot to ignore companies without a phone, so
    email-only records are intentionally dropped here as well.
    """
    return bool((row.get("phone") or "").strip())


def write_csv(
    path: Path,
    rows: Iterable[dict],
    append: bool = False,
    *,
    only_valid: bool = True,
) -> int:
    rows = list(rows)
    if only_valid:
        rows = [r for r in rows if is_valid_record(r)]
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append and path.exists() else "w"
    write_header = mode == "w"
    written = 0
    russian_headers = [HEADERS_RU[k] for k in FIELDS]
    with path.open(mode, encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(russian_headers)
        for row in rows:
            w.writerow([(row.get(k) or "") for k in FIELDS])
            written += 1
    return written
