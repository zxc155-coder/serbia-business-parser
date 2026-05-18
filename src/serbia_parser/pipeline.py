"""End-to-end pipeline: search → crawl → dedup → save per category.

Supports progress callbacks and cancellation so it can be driven from a Telegram
bot or any UI that wants live updates.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .categories import CATEGORIES, SERBIAN_CITIES, Category, by_key
from .crawler import crawl_site
from .dedup import dedup_records
from .extractor import base_domain
from .http import HTTP
from .sources import bing, companywall, duckduckgo
from .sources import maps as maps_src
from .storage import write_csv

log = logging.getLogger(__name__)

# Domains we never treat as company sites (search engines, marketplaces, social, etc.).
DOMAIN_BLACKLIST = {
    "google.com",
    "youtube.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "wikipedia.org",
    "duckduckgo.com",
    "bing.com",
    "yahoo.com",
    "kupujemprodajem.com",
    "olx.ba",
    "halooglasi.com",
    "limundo.com",
    "amazon.com",
    "ebay.com",
    "alibaba.com",
    "aliexpress.com",
    "companywall.rs",
}


@dataclass
class Progress:
    category: str
    stage: str  # "search" | "directory" | "maps" | "crawl" | "save" | "done"
    current: int
    total: int
    found: int = 0
    detail: str = ""


class Cancelled(Exception):
    """Raised when the user requested cancellation."""


ProgressCB = Callable[[Progress], None]


def _emit(cb: ProgressCB | None, p: Progress) -> None:
    if cb is None:
        return
    try:
        cb(p)
    except Exception as e:  # never let UI break the pipeline
        log.warning("progress callback raised: %s", e)


def _check_cancel(evt: threading.Event | None) -> None:
    if evt is not None and evt.is_set():
        raise Cancelled()


def run_category(
    category: Category,
    out_dir: Path,
    *,
    use_maps: bool = True,
    max_search_results: int = 25,
    max_maps_results: int = 20,
    cities: Iterable[str] = SERBIAN_CITIES,
    max_websites: int | None = None,
    on_progress: ProgressCB | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    http = HTTP()
    out_path = out_dir / f"{category.key}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    log.info("=== %s (%s) ===", category.key, category.title_sr)

    # --- 1. Search-engine fan-out → candidate websites. ----------------------
    keywords = (*category.keywords_sr, *category.keywords_en)
    search_hits: list[dict[str, str]] = []
    for i, kw in enumerate(keywords, 1):
        _check_cancel(cancel_event)
        _emit(
            on_progress,
            Progress(category.key, "search", i, len(keywords), len(search_hits), kw),
        )
        try:
            search_hits.extend(duckduckgo.search(http, kw, max_results=max_search_results))
        except Exception as e:
            log.warning("DDG error for %r: %s", kw, e)
        try:
            search_hits.extend(bing.search(http, kw, max_results=max_search_results))
        except Exception as e:
            log.warning("Bing error for %r: %s", kw, e)
    log.info("search hits: %s", len(search_hits))

    # --- 2. companywall.rs directory lookups. -------------------------------
    cw_hits: list[dict[str, str]] = []
    cw_keywords = category.keywords_sr[:3]
    for i, kw in enumerate(cw_keywords, 1):
        _check_cancel(cancel_event)
        _emit(
            on_progress,
            Progress(category.key, "directory", i, len(cw_keywords), len(cw_hits), kw),
        )
        try:
            cw_hits.extend(companywall.search(http, kw, max_results=20))
        except Exception as e:
            log.warning("companywall search error for %r: %s", kw, e)
    log.info("companywall hits: %s", len(cw_hits))

    # --- 3. Maps lookups (city × category query). ---------------------------
    maps_hits: list[dict[str, str]] = []
    if use_maps:
        city_list = list(cities)
        total_maps = len(category.maps_queries) * len(city_list)
        step = 0
        for q in category.maps_queries:
            for city in city_list:
                _check_cancel(cancel_event)
                step += 1
                _emit(
                    on_progress,
                    Progress(
                        category.key,
                        "maps",
                        step,
                        total_maps,
                        len(maps_hits),
                        f"{q} / {city}",
                    ),
                )
                try:
                    maps_hits.extend(maps_src.search_places(q, city, max_results=max_maps_results))
                except Exception as e:
                    log.warning("Maps error for %s / %s: %s", q, city, e)
    log.info("maps hits: %s", len(maps_hits))

    # --- 4. Convert hits into business records. -----------------------------
    records: list[dict] = []

    seen_domains: set[str] = set()
    websites_to_crawl: list[tuple[str, dict]] = []
    for hit in search_hits:
        url = hit.get("url", "")
        domain = base_domain(url)
        if not domain or domain in DOMAIN_BLACKLIST:
            continue
        if domain in seen_domains:
            continue
        seen_domains.add(domain)
        homepage = _homepage(url)
        websites_to_crawl.append((homepage, hit))
        if max_websites and len(websites_to_crawl) >= max_websites:
            break

    log.info("crawling %s unique websites", len(websites_to_crawl))
    for i, (homepage, hit) in enumerate(websites_to_crawl, 1):
        _check_cancel(cancel_event)
        _emit(
            on_progress,
            Progress(
                category.key,
                "crawl",
                i,
                len(websites_to_crawl),
                len(records),
                homepage,
            ),
        )
        info = crawl_site(http, homepage)
        if not info.is_useful():
            continue
        records.append(
            {
                "category": category.title_ru,
                "company": info.title or hit.get("title", "")[:200],
                "website": homepage,
                "phone": "; ".join(info.phones[:3]),
                "email": "; ".join(info.emails[:3]),
                "address": info.addresses[0] if info.addresses else "",
                "city": _guess_city(info.addresses),
                "social": "; ".join(info.socials[:5]),
                "description": info.description or hit.get("snippet", ""),
                "source": hit["source"],
                "source_url": hit["url"],
            }
        )

    for i, cw in enumerate(cw_hits, 1):
        _check_cancel(cancel_event)
        _emit(
            on_progress,
            Progress(category.key, "directory", i, len(cw_hits), len(records), cw["title"]),
        )
        profile = companywall.fetch_profile(http, cw["url"])
        if not profile and not cw.get("title"):
            continue
        website = profile.get("website", "")
        address = profile.get("address", "")
        records.append(
            {
                "category": category.title_ru,
                "company": cw["title"],
                "website": website,
                "phone": profile.get("phone", ""),
                "email": profile.get("email", ""),
                "address": address,
                "city": profile.get("city", "") or _guess_city([address] if address else []),
                "social": "",
                "description": profile.get("activity", ""),
                "source": "companywall",
                "source_url": cw["url"],
            }
        )

    for mh in maps_hits:
        website = mh.get("website", "")
        records.append(
            {
                "category": category.title_ru,
                "company": mh.get("name") or mh.get("title", ""),
                "website": website,
                "phone": mh.get("phone", ""),
                "email": "",
                "address": mh.get("address", ""),
                "city": _guess_city([mh.get("address", "")]),
                "social": "",
                "description": "",
                "source": "google_maps",
                "source_url": mh.get("place_url", ""),
            }
        )

    # --- 5. Dedup + write. --------------------------------------------------
    merged = dedup_records(records)
    written = write_csv(out_path, merged)
    log.info("wrote %s rows → %s", written, out_path)
    _emit(
        on_progress,
        Progress(category.key, "done", 1, 1, written, str(out_path)),
    )
    return out_path


def run_all(out_dir: Path, **kwargs) -> dict[str, Path]:
    return {c.key: run_category(c, out_dir, **kwargs) for c in CATEGORIES}


def _homepage(url: str) -> str:
    p = urlparse(url)
    if not p.netloc:
        return url
    return f"{p.scheme or 'https'}://{p.netloc}/"


def _guess_city(addresses: Iterable[str]) -> str:
    for addr in addresses:
        if not addr:
            continue
        for city in SERBIAN_CITIES:
            if city.lower() in addr.lower():
                return city
    return ""


__all__ = [
    "CATEGORIES",
    "Cancelled",
    "Progress",
    "ProgressCB",
    "by_key",
    "run_all",
    "run_category",
]
