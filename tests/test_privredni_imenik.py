from __future__ import annotations

from types import SimpleNamespace

from serbia_parser.sources import privredni_imenik as pi


class _FakeHTTP:
    def __init__(self, html: str):
        self._html = html

    def get(self, url, params=None):
        return SimpleNamespace(status_code=200, text=self._html)


SEARCH_HTML = """
<html><body>
  <ul>
    <li><a href="/Imenik/Tehno-Doo-12345">Tehno Doo</a></li>
    <li><a href="/Imenik/Other-Company-67890">Other Company</a></li>
    <li><a href="/Imenik/Other-Company-67890">duplicate link</a></li>
    <li><a href="/kontakt">not a profile</a></li>
  </ul>
</body></html>
"""


def test_search_extracts_distinct_profiles():
    http = _FakeHTTP(SEARCH_HTML)
    results = pi.search(http, "metal detektori", max_results=10)
    urls = [r["url"] for r in results]
    assert "https://www.privredni-imenik.com/Imenik/Tehno-Doo-12345" in urls
    assert "https://www.privredni-imenik.com/Imenik/Other-Company-67890" in urls
    # Deduped.
    assert len(urls) == 2
    # Each row carries source label and original query.
    for r in results:
        assert r["source"] == "privredni_imenik"
        assert r["query"] == "metal detektori"


PROFILE_HTML = """
<html><body>
  <h1>Tehno Doo</h1>
  <div class="row">
    <div>Sajt:</div><div>www.tehno-doo.rs</div>
  </div>
  <div class="row">
    <div>E-mail:</div><div>office@tehno-doo.rs</div>
  </div>
  <div class="row">
    <div>Telefon:</div><div>+381 11 234 5678</div>
  </div>
  <div class="row">
    <div>Adresa:</div><div>Bulevar 1, 11000 Beograd</div>
  </div>
</body></html>
"""


def test_fetch_profile_extracts_basic_fields():
    http = _FakeHTTP(PROFILE_HTML)
    data = pi.fetch_profile(http, "https://www.privredni-imenik.com/Imenik/Tehno-Doo-12345")
    assert data["name"] == "Tehno Doo"
    assert data["website"].startswith("http")
    assert "tehno-doo.rs" in data["website"]
    assert data["email"] == "office@tehno-doo.rs"
    assert "234" in data["phone"]
    assert "Beograd" in data["address"]


PROFILE_WITH_TEL_MAILTO = """
<html><body>
  <h1>Mini Co</h1>
  <a href="mailto:hi@mini.rs">write us</a>
  <a href="tel:+381641112233">call</a>
</body></html>
"""


def test_fetch_profile_falls_back_to_mailto_tel():
    http = _FakeHTTP(PROFILE_WITH_TEL_MAILTO)
    data = pi.fetch_profile(http, "https://www.privredni-imenik.com/Imenik/Mini-Co-1")
    assert data["email"] == "hi@mini.rs"
    assert data["phone"] == "+381641112233"
    assert data["name"] == "Mini Co"
