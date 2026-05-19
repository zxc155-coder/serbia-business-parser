"""companywall.rs — Serbian business registry / data aggregator.

Searches the catalog and yields company links. We then fetch each company page to
extract structured fields (name, PIB, MB, email, activity).

Note: companywall.rs gates phone/website/address behind a paid login. The free
profile pages reliably expose name, PIB (tax id), MB (registration id), e-mail,
ownership and activity — that's what we extract here. Phone/website/address are
filled in by the website crawl step in the pipeline whenever a homepage URL is
discovered from a search engine.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http import HTTP

log = logging.getLogger(__name__)

BASE = "https://www.companywall.rs"


def search(http: HTTP, query: str, max_results: int = 20) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for page in range(1, 4):
        url = f"{BASE}/pretraga"
        resp = http.get(url, params={"n": query, "page": str(page)})
        if not resp or resp.status_code != 200:
            break
        soup = BeautifulSoup(resp.text, "lxml")
        anchors = soup.select('a[href^="/firma/"]')
        if not anchors:
            break
        added = 0
        for a in anchors:
            href = a.get("href", "")
            if not href.startswith("/firma/"):
                continue
            full = urljoin(BASE, href)
            if full in seen:
                continue
            seen.add(full)
            name = a.get_text(" ", strip=True)
            if not name:
                continue
            out.append(
                {
                    "title": name,
                    "url": full,
                    "snippet": "",
                    "source": "companywall",
                    "query": query,
                }
            )
            added += 1
            if len(out) >= max_results:
                return out
        if added == 0:
            break
    return out


# Map labeled <dt>/<dd> pairs from the public profile page.
# Anything not in this list is ignored on purpose — companywall puts platform-
# level info (its own phone, website, support address) in unlabeled blocks.
_LABEL_KEYS: dict[str, str] = {
    "Naziv": "name",
    "Sedište": "address",
    "Adresa": "address",
    "PIB": "pib",
    "MB": "registration_id",
    "Matični broj": "registration_id",
    "Delatnost": "activity",
    "E-mail": "email",
    "Email": "email",
    "Vlasnik": "owner",
    "Zastupnik": "representative",
    "Datum osnivanja": "founded",
}


def fetch_profile(http: HTTP, profile_url: str) -> dict[str, str]:
    resp = http.get(profile_url)
    if not resp or resp.status_code != 200:
        return {}
    soup = BeautifulSoup(resp.text, "lxml")
    data: dict[str, str] = {}

    for dt in soup.find_all("dt"):
        label = dt.get_text(" ", strip=True).rstrip(":")
        if label not in _LABEL_KEYS:
            continue
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue
        value = dd.get_text(" ", strip=True)
        if value:
            data.setdefault(_LABEL_KEYS[label], value)

    # Schema.org microdata fallback.
    for tag in soup.select("[itemprop]"):
        prop = tag.get("itemprop", "")
        if prop == "vatID" and "pib" not in data:
            data["pib"] = tag.get_text(" ", strip=True)
        elif prop == "email" and "email" not in data:
            data["email"] = tag.get_text(" ", strip=True)
        elif prop == "name" and "name" not in data:
            data["name"] = tag.get_text(" ", strip=True)

    return data
