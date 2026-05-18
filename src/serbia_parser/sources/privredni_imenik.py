"""privredni-imenik.com — large public Serbian business directory.

Search returns plenty of /Imenik/<NAME>-<ID> profile links. Profile pages expose
labeled <div>label:</div><div>value</div> rows for:
  - Sajt, E-mail, Telefon, Adresa, PIB, Matični broj, Delatnost, Direktor

Some fields (notably Telefon/Adresa) are sometimes blank for free listings; we
fill them in from the website crawl step in the pipeline.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http import HTTP

log = logging.getLogger(__name__)

BASE = "https://www.privredni-imenik.com"
_PROFILE_RE = re.compile(r"^/Imenik/[^/]+-\d+$")


def search(http: HTTP, query: str, max_results: int = 40) -> list[dict[str, str]]:
    """Yield {title,url,snippet,source,query} for distinct /Imenik/ profiles."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    resp = http.get(f"{BASE}/pretraga", params={"keyword": query})
    if not resp or resp.status_code != 200:
        return out
    soup = BeautifulSoup(resp.text, "lxml")
    for a in soup.select("a[href*='/Imenik/']"):
        href = a.get("href", "")
        path = href[len(BASE) :] if href.startswith(BASE) else href
        if not _PROFILE_RE.match(path):
            continue
        full = urljoin(BASE, path)
        if full in seen:
            continue
        seen.add(full)
        # Use the anchor text if present; otherwise derive from URL slug.
        name = a.get_text(" ", strip=True)
        if not name or name.lower() in {"more", "vise", "detalji"}:
            slug = path.rsplit("/", 1)[-1].rsplit("-", 1)[0]
            name = slug.replace("-", " ").strip()
        out.append(
            {
                "title": name,
                "url": full,
                "snippet": "",
                "source": "privredni_imenik",
                "query": query,
            }
        )
        if len(out) >= max_results:
            break
    return out


# Map label text (with trailing colon stripped) → record key.
_LABELS: dict[str, str] = {
    "Naziv": "name",
    "Sajt": "website",
    "Web": "website",
    "Email": "email",
    "E-mail": "email",
    "Telefon": "phone",
    "Telefoni": "phone",
    "Mob": "phone",
    "Mobilni": "phone",
    "Faks": "fax",
    "Adresa": "address",
    "Mesto": "city",
    "PIB": "pib",
    "Matični broj": "registration_id",
    "Maticni broj": "registration_id",
    "Delatnost": "activity",
    "Direktor": "owner",
}


def fetch_profile(http: HTTP, profile_url: str) -> dict[str, str]:
    resp = http.get(profile_url)
    if not resp or resp.status_code != 200:
        return {}
    soup = BeautifulSoup(resp.text, "lxml")
    # Strip top-level nav/footer to avoid picking up menu noise.
    for tag in soup.select("nav, header, footer, script, style"):
        tag.decompose()

    data: dict[str, str] = {}

    # Pattern A: label_text followed by an adjacent value element.
    for node in soup.find_all(string=True):
        txt = (node or "").strip().rstrip(":")
        if txt not in _LABELS:
            continue
        key = _LABELS[txt]
        if key in data:
            continue
        parent = node.parent
        if parent is None:
            continue
        # Look at parent's next sibling, then at parent's parent's next sibling.
        candidates = []
        for el in (parent.find_next_sibling(), parent.parent.find_next_sibling() if parent.parent else None):
            if el is not None:
                candidates.append(el)
        for cand in candidates:
            value = cand.get_text(" ", strip=True)
            if value:
                data[key] = value
                break

    # Pattern B: explicit mailto: / tel: anchors.
    if "email" not in data:
        a = soup.select_one("a[href^=mailto]")
        if a:
            data["email"] = a["href"].removeprefix("mailto:").split("?")[0].strip()
    if "phone" not in data:
        a = soup.select_one("a[href^=tel]")
        if a:
            data["phone"] = a["href"].removeprefix("tel:").strip()

    # Pattern C: name from <h1>.
    if "name" not in data:
        h1 = soup.select_one("h1")
        if h1:
            t = h1.get_text(" ", strip=True)
            if t:
                data["name"] = t

    # Normalize website (often comes without scheme).
    if "website" in data:
        w = data["website"].strip()
        if w and not w.startswith(("http://", "https://")):
            w = "http://" + w
        data["website"] = w

    return data
