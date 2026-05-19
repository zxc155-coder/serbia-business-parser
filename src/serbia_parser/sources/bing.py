"""Bing HTML search scraper (backup search source)."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..http import HTTP

log = logging.getLogger(__name__)


def search(http: HTTP, query: str, max_results: int = 25) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    # Bing tends to gate aggressive pagination behind captchas; two pages is a
    # good balance between coverage and speed.
    for first in (1, 11):
        resp = http.get(
            "https://www.bing.com/search",
            params={"q": query, "first": str(first), "setlang": "sr"},
        )
        if not resp or resp.status_code != 200:
            break
        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select("li.b_algo")
        if not items:
            break
        for item in items:
            a = item.find("a", href=True)
            if not a:
                continue
            url = a["href"]
            host = urlparse(url).netloc
            if not host or "bing.com" in host or "microsoft.com" in host:
                continue
            if url in seen:
                continue
            seen.add(url)
            snippet_tag = item.select_one("p, .b_caption p, .b_lineclamp4")
            results.append(
                {
                    "title": a.get_text(" ", strip=True),
                    "url": url,
                    "snippet": snippet_tag.get_text(" ", strip=True) if snippet_tag else "",
                    "source": "bing",
                    "query": query,
                }
            )
            if len(results) >= max_results:
                return results
    return results
