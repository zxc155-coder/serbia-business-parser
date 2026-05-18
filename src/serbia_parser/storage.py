"""CSV storage for business records.

The on-disk CSV uses Russian column headers so the file is immediately
useful to the end user (they consume the file in Excel/Google Sheets,
not the code). Internal record dicts continue to key by the English
identifiers below; the writer maps those to the Russian headers when
emitting rows.

By default only "valid" records — those with at least a phone or email —
are written to disk, because the user has explicitly asked for files
that contain only contactable companies.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

# Internal record keys (used everywhere in code).
FIELDS = (
    "category",
    "company",
    "website",
    "phone",
    "email",
    "address",
    "city",
    "social",
    "description",
    "source",
    "source_url",
)

# Russian column headers — only used at CSV write time.
HEADERS_RU = {
    "category": "категория",
    "company": "компания",
    "website": "сайт",
    "phone": "телефон",
    "email": "email",
    "address": "адрес",
    "city": "город",
    "social": "соцсети",
    "description": "описание",
    "source": "источник",
    "source_url": "ссылка",
}


def is_valid_record(row: dict) -> bool:
    """A record is exportable when it has at least a phone or an email."""
    return bool((row.get("phone") or "").strip() or (row.get("email") or "").strip())


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
