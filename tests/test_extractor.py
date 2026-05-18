from serbia_parser.extractor import base_domain, candidate_contact_urls, extract_from_html


def test_extract_basic_html():
    html = """
    <html><head>
      <title>Acme Doo - prodaja</title>
      <meta name="description" content="Wholesale agri equipment in Serbia">
    </head><body>
      <p>Adresa: Bulevar Kralja Aleksandra 12, Beograd</p>
      <p>Pišite nam na info@acme.rs ili pozovite +381 11 1234 567.</p>
      <a href="https://facebook.com/acme">FB</a>
      <a href="https://instagram.com/acme">IG</a>
    </body></html>
    """
    info = extract_from_html(html, base_url="https://acme.rs/")
    assert info.title == "Acme Doo - prodaja"
    assert "info@acme.rs" in info.emails
    assert any("381" in p or "1234" in p for p in info.phones), info.phones
    assert any("Bulevar" in a for a in info.addresses)
    assert any("facebook.com" in s for s in info.socials)
    assert any("instagram.com" in s for s in info.socials)
    assert info.is_useful()


def test_extract_ignores_image_emails():
    html = "<p>logo@image.png in text and info@example.rs is real</p>"
    info = extract_from_html(html)
    assert "info@example.rs" in info.emails
    assert all(not e.endswith(".png") for e in info.emails)


def test_extract_empty():
    info = extract_from_html("")
    assert not info.is_useful()


def test_base_domain():
    assert base_domain("https://www.acme.rs/page") == "acme.rs"
    assert base_domain("http://shop.acme.co.rs") == "acme.co.rs"
    assert base_domain("not a url") == ""


def test_candidate_contact_urls():
    urls = candidate_contact_urls("https://acme.rs/some/page")
    assert "https://acme.rs/kontakt" in urls
    assert "https://acme.rs/contact" in urls
    assert all(u.startswith("https://acme.rs/") for u in urls)
