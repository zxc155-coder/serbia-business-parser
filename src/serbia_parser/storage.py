"""CSV storage for business records."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

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


def write_csv(path: Path, rows: Iterable[dict], append: bool = False) -> int:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append and path.exists() else "w"
    write_header = mode == "w"
    written = 0
    with path.open(mode, encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if write_header:
            w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in FIELDS})
            written += 1
    return written
