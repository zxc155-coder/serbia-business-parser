from serbia_parser.categories import CATEGORIES, SERBIAN_CITIES, by_key


def test_ten_categories():
    assert len(CATEGORIES) == 10
    keys = {c.key for c in CATEGORIES}
    assert keys == {
        "metal_detectors",
        "agri_machinery",
        "industrial_equipment",
        "construction_equipment",
        "electronic_components",
        "auto_moto_parts",
        "medical_equipment",
        "3d_scanners_printers",
        "optical_devices",
        "furniture_interior",
    }


def test_each_category_has_keywords():
    for c in CATEGORIES:
        assert c.keywords_sr and c.keywords_en and c.maps_queries
        assert all(kw.strip() for kw in c.keywords_sr)
        assert all(kw.strip() for kw in c.keywords_en)


def test_by_key_lookup_and_error():
    cat = by_key("metal_detectors")
    assert cat.key == "metal_detectors"
    try:
        by_key("nope")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError")


def test_serbian_cities_populated():
    assert "Beograd" in SERBIAN_CITIES
    assert "Novi Sad" in SERBIAN_CITIES
    assert len(SERBIAN_CITIES) >= 10
