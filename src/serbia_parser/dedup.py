"""Dedup business records across sources.

Primary key: base domain of the website. Fallback: normalized first phone.
When the same company appears in multiple sources we merge contact fields.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .extractor import base_domain


def _norm_phone(p: str) -> str:
    digits = re.sub(r"\D+", "", p or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) >= 8:
        digits = "381" + digits[1:]
    return digits


def dedup_records(records: Iterable[dict]) -> list[dict]:
    by_key: dict[str, dict] = {}
    for rec in records:
        website = rec.get("website") or ""
        domain = base_domain(website) if website else ""
        phone = _norm_phone((rec.get("phone") or "").split("\n")[0])
        name = (rec.get("company") or "").lower().strip()
        if domain:
            key = f"dom:{domain}"
        elif phone:
            key = f"phone:{phone}"
        elif name:
            key = f"name:{name}"
        else:
            # No identity at all — keep, use source URL (or object id) as unique key.
            key = f"url:{rec.get('source_url') or rec.get('place_url') or id(rec)}"

        existing = by_key.get(key)
        if existing is None:
            by_key[key] = dict(rec)
            continue

        # Merge: prefer first non-empty value, accumulate sources/links.
        for k, v in rec.items():
            if k in ("source", "source_url", "place_url"):
                continue
            if not existing.get(k) and v:
                existing[k] = v

        sources = set(filter(None, [existing.get("source", ""), rec.get("source", "")]))
        existing["source"] = ",".join(sorted(sources))

        urls = set(filter(None, [existing.get("source_url", ""), rec.get("source_url", "")]))
        existing["source_url"] = " | ".join(sorted(urls))

    return list(by_key.values())
