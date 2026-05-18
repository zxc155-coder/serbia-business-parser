"""DuckDuckGo HTML search scraper.

Uses the lite/HTML endpoint which does not require JavaScript and rarely blocks
single-IP residential traffic. Returns a list of (title, url, snippet).
"""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from ..http import HTTP

log = logging.getLogger(__name__)

DDG_URL = "https://html.duckduckgo.com/html/"


def _unwrap(url: str) -> str:
    """DDG wraps results in //duckduckgo.com/l/?uddg=<encoded>."""
    if "duckduckgo.com/l/" in url:
        qs = parse_qs(urlparse(url).query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    if url.startswith("//"):
        url = "https:" + url
    return url


def search(http: HTTP, query: str, max_results: int = 25) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for page in range(3):
        params = {"q": query}
        if page:
            params["s"] = str(page * 30)
        resp = http.get(DDG_URL, params=params)
        if not resp or resp.status_code != 200:
            break
        soup = BeautifulSoup(resp.text, "lxml")
        anchors = soup.select("a.result__a")
        if not anchors:
            break
        for a in anchors:
            href = a.get("href", "")
            if not href:
                continue
            url = _unwrap(href)
            if url in seen:
                continue
            seen.add(url)
            snippet_tag = a.find_parent("div", class_=re.compile("result"))
            snippet = ""
            if snippet_tag:
                sn = snippet_tag.find(class_="result__snippet")
                if sn:
                    snippet = sn.get_text(" ", strip=True)
            results.append(
                {
                    "title": a.get_text(" ", strip=True),
                    "url": url,
                    "snippet": snippet,
                    "source": "duckduckgo",
                    "query": query,
                }
            )
            if len(results) >= max_results:
                return results
    return results
