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


# Map normalized label text (lowercase, no trailing colon) → record key.
# Keys are matched case-insensitively.
_LABELS: dict[str, str] = {
    "naziv": "name",
    "sajt": "website",
    "web": "website",
    "email": "email",
    "e-mail": "email",
    "telefon": "phone",
    "telefoni": "phone",
    "mob": "phone",
    "mobilni": "phone",
    "telefaks": "fax",
    "faks": "fax",
    "adresa": "address",
    "mesto": "city",
    "pib": "pib",
    "matični broj": "registration_id",
    "maticni broj": "registration_id",
    "delatnost": "activity",
    "direktor": "owner",
}

_LABEL_NORMS = set(_LABELS.keys())


def _label_key(text: str) -> str | None:
    """Return the record key for a label cell, or None."""
    norm = (text or "").strip().rstrip(":").lower()
    return _LABELS.get(norm)


def fetch_profile(http: HTTP, profile_url: str) -> dict[str, str]:
    resp = http.get(profile_url)
    if not resp or resp.status_code != 200:
        return {}
    soup = BeautifulSoup(resp.text, "lxml")
    # Strip top-level nav/footer to avoid picking up menu noise.
    for tag in soup.select("nav, header, footer, script, style"):
        tag.decompose()

    data: dict[str, str] = {}
    # Phones / fax can repeat; collect all of them, dedup, join later.
    extras: dict[str, list[str]] = {"phone": [], "fax": []}

    # privredni-imenik mixes two row layouts inside the same .row container:
    #   Pattern A: <div col-md-4>label:</div><div col-md-8>value</div>
    #   Pattern B: <div col-md-4>value</div><div col-md-8>LABEL</div>   (TELEFON/TELEFAKS)
    # So for every <div> we treat its text as a possible label and look at
    # both the next AND the previous sibling for the value.
    for div in soup.find_all("div"):
        # Only consider "cell"-like divs, not big containers.
        cell_text = div.get_text(" ", strip=True)
        if not cell_text or len(cell_text) > 30:
            continue
        key = _label_key(cell_text)
        if key is None:
            continue
        for sibling in (div.find_next_sibling(), div.find_previous_sibling()):
            if sibling is None:
                continue
            value = sibling.get_text(" ", strip=True)
            if not value or _label_key(value) is not None:
                continue
            if key in extras:
                if value not in extras[key]:
                    extras[key].append(value)
            elif key not in data:
                data[key] = value
            break

    # Multi-valued fields: phone/fax.
    if extras["phone"]:
        data["phone"] = "; ".join(extras["phone"][:3])
    if extras["fax"] and "fax" not in data:
        data["fax"] = "; ".join(extras["fax"][:3])

    # mailto: anchor fallback.
    if "email" not in data:
        a = soup.select_one("a[href^=mailto]")
        if a:
            data["email"] = a["href"].removeprefix("mailto:").split("?")[0].strip()
    # tel: anchor fallback.
    if "phone" not in data:
        tels = [a["href"].removeprefix("tel:").strip() for a in soup.select("a[href^=tel]")]
        tels = [t for t in tels if t]
        if tels:
            data["phone"] = "; ".join(dict.fromkeys(tels[:3]))

    # Name from <h1>.
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
