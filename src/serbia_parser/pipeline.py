"""End-to-end pipeline: search → crawl → dedup → save per category.

Tuned for throughput: parallel keyword fan-out, parallel directory profile
fetches, parallel website crawls, and per-host rate limiting in HTTP so that
concurrent workers hitting different hosts do not stall each other.

A category run can be capped with `target_valid` so the pipeline stops once
enough records with a phone or email have been collected — useful when the
caller has a "N contacts per session" goal (e.g. ~500 / 20 min from the bot).
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .categories import CATEGORIES, SERBIAN_CITIES, Category, by_key
from .crawler import crawl_site
from .dedup import dedup_records
from .extractor import base_domain
from .http import HTTP
from .sources import bing, companywall, duckduckgo, privredni_imenik
from .sources import maps as maps_src
from .storage import write_csv

# Concurrency knobs. Conservative defaults that we have validated locally; can
# be overridden via env vars in bot.py / cli.py for deployments with different
# upstream tolerance.
SEARCH_WORKERS = 8
DIRECTORY_WORKERS = 8
CRAWL_WORKERS = 16

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
    valid: int = 0
    detail: str = ""


class Cancelled(Exception):
    """Raised when the user requested cancellation."""


class _TargetReached(Exception):
    """Internal marker: enough valid records collected, stop early."""


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


def is_valid_contact(rec: dict) -> bool:
    """A record is considered valid if it has a phone OR an email."""
    return bool((rec.get("phone") or "").strip() or (rec.get("email") or "").strip())


def count_valid(records: Iterable[dict]) -> int:
    return sum(1 for r in records if is_valid_contact(r))


def run_category(
    category: Category,
    out_dir: Path,
    *,
    use_maps: bool = True,
    max_search_results: int = 25,
    max_maps_results: int = 20,
    cities: Iterable[str] = SERBIAN_CITIES,
    max_websites: int | None = None,
    target_valid: int | None = None,
    deadline_s: float | None = None,
    on_progress: ProgressCB | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    http = HTTP()
    out_path = out_dir / f"{category.key}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    log.info("=== %s (%s) ===", category.key, category.title_sr)
    started = time.monotonic()

    def _time_left() -> float | None:
        if deadline_s is None:
            return None
        return deadline_s - (time.monotonic() - started)

    def _out_of_time() -> bool:
        left = _time_left()
        return left is not None and left <= 0

    records: list[dict] = []
    valid_lock = threading.Lock()

    def _add_record(rec: dict | None) -> None:
        if rec is None:
            return
        with valid_lock:
            records.append(rec)

    def _enough() -> bool:
        if target_valid is None:
            return False
        with valid_lock:
            return count_valid(records) >= target_valid

    # --- 1. Search-engine fan-out → candidate websites (parallel). ---------
    keywords = (*category.keywords_sr, *category.keywords_en)
    search_hits: list[dict[str, str]] = []
    search_lock = threading.Lock()

    def _search_one(kw: str) -> int:
        local: list[dict[str, str]] = []
        try:
            local.extend(duckduckgo.search(http, kw, max_results=max_search_results))
        except Exception as e:
            log.warning("DDG error for %r: %s", kw, e)
        try:
            local.extend(bing.search(http, kw, max_results=max_search_results))
        except Exception as e:
            log.warning("Bing error for %r: %s", kw, e)
        with search_lock:
            search_hits.extend(local)
        return len(local)

    done_search = 0
    total_search = len(keywords)
    with ThreadPoolExecutor(max_workers=SEARCH_WORKERS) as ex:
        futs = {ex.submit(_search_one, kw): kw for kw in keywords}
        try:
            for fut in as_completed(futs):
                _check_cancel(cancel_event)
                done_search += 1
                _emit(
                    on_progress,
                    Progress(
                        category.key,
                        "search",
                        done_search,
                        total_search,
                        len(search_hits),
                        0,
                        futs[fut],
                    ),
                )
                if _out_of_time():
                    log.info("search: out of time after %s/%s keywords", done_search, total_search)
                    break
        except Cancelled:
            for f in futs:
                f.cancel()
            raise
    log.info("search hits: %s", len(search_hits))

    # --- 2. Directory lookups (companywall + privredni-imenik) -- parallel. -
    # Use more SR keywords than before — directories are the highest-yield
    # source for valid (phone+email) contacts, so we lean on them harder.
    dir_keywords = list(category.keywords_sr[:8])
    cw_hits: list[dict[str, str]] = []
    pi_hits: list[dict[str, str]] = []
    cw_lock = threading.Lock()
    pi_lock = threading.Lock()

    def _cw_search(kw: str) -> None:
        try:
            local = companywall.search(http, kw, max_results=20)
        except Exception as e:
            log.warning("companywall search error for %r: %s", kw, e)
            return
        with cw_lock:
            cw_hits.extend(local)

    def _pi_search(kw: str) -> None:
        try:
            local = privredni_imenik.search(http, kw, max_results=60)
        except Exception as e:
            log.warning("privredni_imenik search error for %r: %s", kw, e)
            return
        with pi_lock:
            pi_hits.extend(local)

    dir_tasks: list[tuple[str, Callable[[str], None]]] = []
    for kw in dir_keywords:
        dir_tasks.append((f"companywall: {kw}", lambda k=kw: _cw_search(k)))
        dir_tasks.append((f"privredni-imenik: {kw}", lambda k=kw: _pi_search(k)))

    done_dir = 0
    total_dir = len(dir_tasks)
    with ThreadPoolExecutor(max_workers=DIRECTORY_WORKERS) as ex:
        futs2 = {ex.submit(fn): label for label, fn in dir_tasks}
        try:
            for fut in as_completed(futs2):
                _check_cancel(cancel_event)
                done_dir += 1
                _emit(
                    on_progress,
                    Progress(
                        category.key,
                        "directory",
                        done_dir,
                        total_dir,
                        len(cw_hits) + len(pi_hits),
                        0,
                        futs2[fut],
                    ),
                )
                if _out_of_time():
                    log.info("dir search: out of time")
                    break
        except Cancelled:
            for f in futs2:
                f.cancel()
            raise

    # Deduplicate directory hits by url.
    cw_seen: set[str] = set()
    cw_hits = [h for h in cw_hits if h["url"] not in cw_seen and not cw_seen.add(h["url"])]
    pi_seen: set[str] = set()
    pi_hits = [h for h in pi_hits if h["url"] not in pi_seen and not pi_seen.add(h["url"])]
    log.info("companywall hits: %s, privredni_imenik hits: %s", len(cw_hits), len(pi_hits))

    # --- 3. Directory profiles -- parallel, yield highest-quality contacts. -
    # We do these BEFORE Maps and BEFORE the website crawl because they are by
    # far the cheapest per valid contact (one HTTP request → name + phone +
    # email + address + activity) and let us short-circuit early if we hit
    # the target.

    def _pi_one(pi: dict[str, str]) -> dict | None:
        try:
            profile = privredni_imenik.fetch_profile(http, pi["url"])
        except Exception as e:
            log.warning("privredni_imenik profile error for %s: %s", pi["url"], e)
            return None
        if not profile and not pi.get("title"):
            return None
        address = profile.get("address", "")
        company = profile.get("name") or pi.get("title", "")
        return {
            "category": category.title_ru,
            "company": company,
            "website": profile.get("website", ""),
            "phone": profile.get("phone", ""),
            "email": profile.get("email", ""),
            "address": address,
            "city": _guess_city([address] if address else []),
            "social": "",
            "description": profile.get("activity", ""),
            "source": "privredni_imenik",
            "source_url": pi["url"],
        }

    def _cw_one(cw: dict[str, str]) -> dict | None:
        try:
            profile = companywall.fetch_profile(http, cw["url"])
        except Exception as e:
            log.warning("companywall profile error for %s: %s", cw["url"], e)
            return None
        if not profile and not cw.get("title"):
            return None
        address = profile.get("address", "")
        return {
            "category": category.title_ru,
            "company": cw["title"],
            "website": profile.get("website", ""),
            "phone": profile.get("phone", ""),
            "email": profile.get("email", ""),
            "address": address,
            "city": profile.get("city", "") or _guess_city([address] if address else []),
            "social": "",
            "description": profile.get("activity", ""),
            "source": "companywall",
            "source_url": cw["url"],
        }

    # Privredni-imenik first — highest yield of valid contacts per request.
    if pi_hits and not _out_of_time():
        done = 0
        total = len(pi_hits)
        with ThreadPoolExecutor(max_workers=DIRECTORY_WORKERS) as ex:
            futures = {ex.submit(_pi_one, pi): pi for pi in pi_hits}
            try:
                for fut in as_completed(futures):
                    _check_cancel(cancel_event)
                    done += 1
                    rec = fut.result()
                    _add_record(rec)
                    _emit(
                        on_progress,
                        Progress(
                            category.key,
                            "directory",
                            done,
                            total,
                            len(records),
                            count_valid(records),
                            futures[fut].get("title", ""),
                        ),
                    )
                    if _enough() or _out_of_time():
                        for f in futures:
                            f.cancel()
                        break
            except Cancelled:
                for f in futures:
                    f.cancel()
                raise

    if cw_hits and not _enough() and not _out_of_time():
        done = 0
        total = len(cw_hits)
        with ThreadPoolExecutor(max_workers=DIRECTORY_WORKERS) as ex:
            futures = {ex.submit(_cw_one, cw): cw for cw in cw_hits}
            try:
                for fut in as_completed(futures):
                    _check_cancel(cancel_event)
                    done += 1
                    rec = fut.result()
                    _add_record(rec)
                    _emit(
                        on_progress,
                        Progress(
                            category.key,
                            "directory",
                            done,
                            total,
                            len(records),
                            count_valid(records),
                            futures[fut].get("title", ""),
                        ),
                    )
                    if _enough() or _out_of_time():
                        for f in futures:
                            f.cancel()
                        break
            except Cancelled:
                for f in futures:
                    f.cancel()
                raise

    # --- 4. Website crawl on search-engine hits -----------------------------
    if not _enough() and not _out_of_time():
        seen_domains: set[str] = set()
        # If we already pulled websites from directory profiles, skip those domains.
        for rec in records:
            d = base_domain(rec.get("website") or "")
            if d:
                seen_domains.add(d)

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

        log.info("crawling %s unique websites in parallel", len(websites_to_crawl))

        def _crawl_one(args: tuple[str, dict]) -> dict | None:
            homepage, hit = args
            try:
                info = crawl_site(http, homepage)
            except Exception as e:
                log.warning("crawl failed for %s: %s", homepage, e)
                return None
            if not info.is_useful():
                return None
            return {
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

        if websites_to_crawl:
            done = 0
            total = len(websites_to_crawl)
            with ThreadPoolExecutor(max_workers=CRAWL_WORKERS) as ex:
                futures = {ex.submit(_crawl_one, args): args for args in websites_to_crawl}
                try:
                    for fut in as_completed(futures):
                        _check_cancel(cancel_event)
                        done += 1
                        args = futures[fut]
                        rec = fut.result()
                        _add_record(rec)
                        _emit(
                            on_progress,
                            Progress(
                                category.key,
                                "crawl",
                                done,
                                total,
                                len(records),
                                count_valid(records),
                                args[0],
                            ),
                        )
                        if _enough() or _out_of_time():
                            for f in futures:
                                f.cancel()
                            break
                except Cancelled:
                    for f in futures:
                        f.cancel()
                    raise

    # --- 5. Maps lookups (city × category query) -- only if requested AND we
    #         still need more contacts AND time allows.
    if use_maps and not _enough() and not _out_of_time():
        city_list = list(cities)
        total_maps = len(category.maps_queries) * len(city_list)
        step = 0
        stop = False
        for q in category.maps_queries:
            if stop:
                break
            for city in city_list:
                _check_cancel(cancel_event)
                step += 1
                try:
                    rows = maps_src.search_places(q, city, max_results=max_maps_results)
                except Exception as e:
                    log.warning("Maps error for %s / %s: %s", q, city, e)
                    rows = []
                for mh in rows:
                    rec = {
                        "category": category.title_ru,
                        "company": mh.get("name") or mh.get("title", ""),
                        "website": mh.get("website", ""),
                        "phone": mh.get("phone", ""),
                        "email": "",
                        "address": mh.get("address", ""),
                        "city": _guess_city([mh.get("address", "")]),
                        "social": "",
                        "description": "",
                        "source": "google_maps",
                        "source_url": mh.get("place_url", ""),
                    }
                    _add_record(rec)
                _emit(
                    on_progress,
                    Progress(
                        category.key,
                        "maps",
                        step,
                        total_maps,
                        len(records),
                        count_valid(records),
                        f"{q} / {city}",
                    ),
                )
                if _enough() or _out_of_time():
                    stop = True
                    break

    # --- 6. Dedup + write. --------------------------------------------------
    merged = dedup_records(records)
    written = write_csv(out_path, merged)
    valid = count_valid(merged)
    log.info("wrote %s rows (%s valid) → %s", written, valid, out_path)
    _emit(
        on_progress,
        Progress(category.key, "done", 1, 1, written, valid, str(out_path)),
    )
    return out_path


def run_all(out_dir: Path, **kwargs) -> dict[str, Path]:
    return {c.key: run_category(c, out_dir, **kwargs) for c in CATEGORIES}


def _homepage(url: str) -> str:
    p = urlparse(url)
    if not p.netloc:
        return url
    return f"{p.scheme or 'https'}://{p.netloc}/"


_CITY_RE = re.compile("|".join(re.escape(c) for c in SERBIAN_CITIES), re.IGNORECASE)


def _guess_city(addresses: Iterable[str]) -> str:
    for addr in addresses:
        if not addr:
            continue
        m = _CITY_RE.search(addr)
        if m:
            return m.group(0)
    return ""


__all__ = [
    "CATEGORIES",
    "Cancelled",
    "Progress",
    "ProgressCB",
    "by_key",
    "count_valid",
    "is_valid_contact",
    "run_all",
    "run_category",
]
