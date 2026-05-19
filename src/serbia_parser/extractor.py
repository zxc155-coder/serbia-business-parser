"""Extract contacts (phone, email, address, social) from arbitrary HTML pages."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import tldextract
from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", re.IGNORECASE)

# Serbian phone numbers: +381..., 06X..., 011..., 021... etc.
# Accept `+381`, plain `381` (some sites omit the plus), or national `0XX`
# leading digits, followed by 6+ separated digit groups. Separators allowed:
# space, dash, dot, slash, parens, non-breaking space.
_SEP = r"[\s\-./()\u00a0]"
PHONE_RE = re.compile(
    r"(?:(?:\+|00)?\s*381" + _SEP + r"*\d" + r"(?:" + _SEP + r"*\d){5,12}"
    r"|0\s*\d{1,3}" + _SEP + r"*\d(?:" + _SEP + r"*\d){5,11})"
)

# `tel:` href fallback: easier pattern, just need digits with optional + prefix.
TEL_HREF_RE = re.compile(r'href=["\']?tel:\s*\+?([\d\s\-./()\u00a0]{6,})["\']?', re.I)

# Junk patterns commonly mis-matched as phone numbers (analytics ids, css hashes,
# image filenames, etc.).
PHONE_BLACKLIST_RE = re.compile(
    r"^\D*0+\D*$|sentry|cdn|maxcdn|css|js|\.png|\.jpg|\.gif|\.svg|\.webp",
    re.I,
)

# Address heuristic: tries to capture street + number + city in Latin Serbian / Cyrillic.
ADDRESS_KEYWORDS = (
    "ulica",
    "bulevar",
    "trg",
    "putu",
    "adresa",
    "address",
    "br.",
    "br ",
    "broj",
    "ул.",
    "адреса",
)

CONTACT_PATHS = (
    "/kontakt",
    "/kontakt/",
    "/kontakt.html",
    "/kontakti",
    "/kontakti/",
    "/kontakt-nas",
    "/kontaktirajte-nas",
    "/kontakt-info",
    "/контакт",
    "/contact",
    "/contact/",
    "/contact.html",
    "/contact-us",
    "/contacts",
    "/o-nama",
    "/o-nama/",
    "/about",
    "/about-us",
    "/impressum",
    "/imprint",
    "/sr/kontakt",
    "/en/contact",
    "/en/contact-us",
)


@dataclass
class ContactInfo:
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)
    socials: list[str] = field(default_factory=list)
    title: str | None = None
    description: str | None = None

    def merge(self, other: ContactInfo) -> ContactInfo:
        self.emails = _uniq(self.emails + other.emails)
        self.phones = _uniq(self.phones + other.phones)
        self.addresses = _uniq(self.addresses + other.addresses)
        self.socials = _uniq(self.socials + other.socials)
        self.title = self.title or other.title
        self.description = self.description or other.description
        return self

    def is_useful(self) -> bool:
        return bool(self.emails or self.phones or self.addresses)


def _uniq(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in seq:
        key = s.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(s.strip())
    return out


def _normalize_phone(raw: str) -> str | None:
    digits_only = re.sub(r"\D+", "", raw)
    if len(digits_only) < 7 or len(digits_only) > 15:
        return None
    if PHONE_BLACKLIST_RE.search(raw):
        return None
    # Compact display.
    return re.sub(r"\s+", " ", raw.strip())


def extract_from_html(html: str, base_url: str | None = None) -> ContactInfo:
    info = ContactInfo()
    if not html:
        return info

    soup = BeautifulSoup(html, "lxml")

    if soup.title and soup.title.string:
        info.title = soup.title.string.strip()[:200]
    desc = soup.find("meta", attrs={"name": "description"})
    if desc and desc.get("content"):
        info.description = desc["content"].strip()[:300]

    text = soup.get_text(" ", strip=True)

    info.emails = _uniq(EMAIL_RE.findall(text + " " + html))
    info.emails = [e for e in info.emails if not _looks_like_image(e)]

    # Search BOTH visible text AND raw HTML — many sites hide phones in
    # `data-phone` attributes or `<a href="tel:">` and the visible text only
    # says "Позови нас" / "Call us".
    phones_raw = list(PHONE_RE.findall(text))
    phones_raw.extend(PHONE_RE.findall(html))
    # Also pull from explicit `tel:` hrefs (most reliable signal).
    phones_raw.extend(TEL_HREF_RE.findall(html))
    info.phones = _uniq([p for p in (_normalize_phone(p) for p in phones_raw) if p])

    addresses: list[str] = []
    for tag in soup.find_all(["p", "div", "li", "span", "address"]):
        snippet = tag.get_text(" ", strip=True)
        if 10 < len(snippet) < 200 and any(k in snippet.lower() for k in ADDRESS_KEYWORDS):
            addresses.append(snippet)
    info.addresses = _uniq(addresses)[:5]

    socials: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if base_url and href.startswith("/"):
            href = urljoin(base_url, href)
        domain = urlparse(href).netloc.lower()
        if any(
            s in domain
            for s in (
                "facebook.com",
                "instagram.com",
                "linkedin.com",
                "twitter.com",
                "x.com",
                "youtube.com",
                "tiktok.com",
            )
        ):
            socials.append(href)
    info.socials = _uniq(socials)[:10]

    return info


def _looks_like_image(email: str) -> bool:
    return email.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"))


def base_domain(url: str) -> str:
    ext = tldextract.extract(url)
    if not ext.domain or not ext.suffix:
        return ""
    return f"{ext.domain}.{ext.suffix}".lower()


def candidate_contact_urls(base_url: str) -> list[str]:
    parsed = urlparse(base_url)
    root = f"{parsed.scheme or 'https'}://{parsed.netloc}"
    return [root + p for p in CONTACT_PATHS]
