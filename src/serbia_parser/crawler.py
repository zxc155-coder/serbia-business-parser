"""Crawl candidate websites for contact info.

Given a homepage URL, fetch the home page plus a handful of likely contact pages
(/kontakt, /contact, /o-nama, …) and aggregate emails / phones / addresses.

Contact pages are visited first because they are several times more likely than
the home page to yield a phone + email pair; we stop as soon as we have one of
each so a typical site costs 1–2 HTTP requests instead of 6.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .extractor import ContactInfo, candidate_contact_urls, extract_from_html
from .http import HTTP

log = logging.getLogger(__name__)


def crawl_site(http: HTTP, start_url: str, max_pages: int = 4) -> ContactInfo:
    info = ContactInfo()
    if not start_url:
        return info
    parsed = urlparse(start_url)
    if not parsed.scheme:
        start_url = "https://" + start_url.lstrip("/")
        parsed = urlparse(start_url)
    if not parsed.netloc:
        return info

    visited: set[str] = set()

    # Visit contact-style paths first — much higher yield than the homepage.
    contact_urls = candidate_contact_urls(start_url)
    discovered_from_home: list[str] = []

    home_resp = http.get(start_url, allow_redirects=True)
    if home_resp is not None and home_resp.status_code < 400:
        visited.add(start_url)
        info.merge(extract_from_html(home_resp.text, base_url=home_resp.url))
        discovered_from_home = _extract_contact_links(home_resp.text, home_resp.url)

    queue: list[str] = []
    # Prioritise contact paths that the home page actually linked to (real
    # routes) over the generic /kontakt /contact /o-nama guesses.
    queue.extend(discovered_from_home)
    queue.extend(contact_urls)

    for url in queue:
        if len(visited) >= max_pages:
            break
        if url in visited:
            continue
        visited.add(url)
        resp = http.get(url, allow_redirects=True)
        if resp is None or resp.status_code >= 400:
            continue
        info.merge(extract_from_html(resp.text, base_url=resp.url))
        if info.phones and info.emails:
            break

    return info


def _extract_contact_links(html: str, base_url: str) -> list[str]:
    out: list[str] = []
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        text = (a.get_text(" ", strip=True) or "").lower()
        href = a["href"]
        if any(
            kw in text
            for kw in (
                "kontakt",
                "contact",
                "o nama",
                "about",
                "impressum",
                "imprint",
                "контакт",
            )
        ):
            out.append(urljoin(base_url, href))
        elif any(kw in href.lower() for kw in ("/kontakt", "/contact", "/o-nama", "/about", "/impressum")):
            out.append(urljoin(base_url, href))
    # Dedup while preserving order.
    seen: set[str] = set()
    uniq: list[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq[:6]
