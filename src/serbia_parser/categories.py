"""10 business categories with Serbian + English search keywords.

Keywords are tuned for B2B / wholesale where possible. Each category lists multiple
synonyms so we can fan out search queries across DuckDuckGo, Bing, Google Maps and
Serbian directories.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    key: str
    title_ru: str
    title_sr: str
    keywords_sr: tuple[str, ...]
    keywords_en: tuple[str, ...]
    maps_queries: tuple[str, ...]


CATEGORIES: tuple[Category, ...] = (
    Category(
        key="metal_detectors",
        title_ru="Металлоискатели и детекторы (B2B опт)",
        title_sr="Detektori metala (veleprodaja)",
        keywords_sr=(
            "detektori metala veleprodaja",
            "detektor metala prodaja",
            "industrijski detektor metala",
            "detektori metala b2b",
            "uvoznik detektora metala srbija",
        ),
        keywords_en=(
            "metal detectors wholesale Serbia",
            "industrial metal detector Serbia distributor",
            "metal detector b2b Serbia",
        ),
        maps_queries=(
            "detektori metala",
            "metal detector store",
        ),
    ),
    Category(
        key="agri_machinery",
        title_ru="Сельхозтехника",
        title_sr="Poljoprivredna mehanizacija",
        keywords_sr=(
            "traktori prodaja srbija",
            "kombajni prodaja srbija",
            "sistemi za navodnjavanje prodaja",
            "poljoprivredna mehanizacija prodaja",
            "poljoprivredne masine veleprodaja",
            "uvoznik traktora srbija",
        ),
        keywords_en=(
            "agricultural machinery Serbia",
            "tractors importer Serbia",
            "irrigation systems Serbia distributor",
            "combine harvester Serbia",
        ),
        maps_queries=(
            "poljoprivredne mašine",
            "traktori prodaja",
            "sistemi za navodnjavanje",
        ),
    ),
    Category(
        key="industrial_equipment",
        title_ru="Промышленное оборудование (ЧПУ, фрезеры, компрессоры)",
        title_sr="Industrijska oprema (CNC, glodalice, kompresori)",
        keywords_sr=(
            "cnc masine prodaja srbija",
            "glodalice prodaja",
            "industrijski kompresori prodaja",
            "industrijska oprema veleprodaja",
            "metalska industrija oprema srbija",
        ),
        keywords_en=(
            "CNC machine distributor Serbia",
            "industrial compressors Serbia",
            "milling machines Serbia b2b",
            "industrial equipment supplier Serbia",
        ),
        maps_queries=(
            "CNC mašine",
            "industrijski kompresori",
            "industrijska oprema",
        ),
    ),
    Category(
        key="construction_equipment",
        title_ru="Строительная техника",
        title_sr="Građevinske mašine",
        keywords_sr=(
            "gradjevinske masine prodaja",
            "bageri prodaja srbija",
            "utovarivaci prodaja srbija",
            "mini fabrike betona",
            "uvoznik gradjevinske mehanizacije",
        ),
        keywords_en=(
            "construction equipment Serbia",
            "excavators dealer Serbia",
            "loaders Serbia importer",
            "mini concrete plant Serbia",
        ),
        maps_queries=(
            "građevinske mašine",
            "bageri prodaja",
            "utovarivači",
        ),
    ),
    Category(
        key="electronic_components",
        title_ru="Электронные компоненты",
        title_sr="Elektronske komponente",
        keywords_sr=(
            "elektronske komponente prodaja srbija",
            "mikrokontroleri prodaja",
            "konektori veleprodaja",
            "rf moduli prodaja",
            "fpga prodaja srbija",
        ),
        keywords_en=(
            "electronic components distributor Serbia",
            "microcontrollers Serbia",
            "connectors wholesale Serbia",
            "RF modules Serbia",
            "FPGA distributor Serbia",
        ),
        maps_queries=(
            "elektronske komponente",
            "elektronika veleprodaja",
        ),
    ),
    Category(
        key="auto_moto_parts",
        title_ru="Запчасти для авто/мото",
        title_sr="Delovi za auto i moto",
        keywords_sr=(
            "auto delovi veleprodaja srbija",
            "moto delovi veleprodaja",
            "turbine prodaja",
            "kocioni sistemi prodaja",
            "klipovi prodaja srbija",
        ),
        keywords_en=(
            "auto parts wholesale Serbia",
            "motorcycle parts distributor Serbia",
            "turbochargers Serbia",
            "brake systems Serbia",
        ),
        maps_queries=(
            "auto delovi veleprodaja",
            "moto delovi",
            "turbo servis",
        ),
    ),
    Category(
        key="medical_equipment",
        title_ru="Медицинское оборудование",
        title_sr="Medicinska oprema",
        keywords_sr=(
            "medicinska oprema prodaja srbija",
            "ultrazvucni aparati prodaja",
            "respiratori prodaja",
            "laboratorijski analizatori prodaja",
            "uvoznik medicinske opreme srbija",
        ),
        keywords_en=(
            "medical equipment distributor Serbia",
            "ultrasound machine Serbia",
            "ventilators Serbia importer",
            "laboratory analyzers Serbia",
        ),
        maps_queries=(
            "medicinska oprema",
            "ultrazvučni aparati",
            "laboratorijska oprema",
        ),
    ),
    Category(
        key="3d_scanners_printers",
        title_ru="3D-сканеры и принтеры",
        title_sr="3D skeneri i štampači",
        keywords_sr=(
            "3d stampaci prodaja srbija",
            "3d skeneri prodaja",
            "industrijski 3d stampac",
            "medicinski 3d skener",
        ),
        keywords_en=(
            "3D printer distributor Serbia",
            "industrial 3D scanner Serbia",
            "medical 3D scanner Serbia",
        ),
        maps_queries=(
            "3D štampači",
            "3D skeneri",
        ),
    ),
    Category(
        key="optical_devices",
        title_ru="Оптические приборы",
        title_sr="Optički uređaji",
        keywords_sr=(
            "termovizije prodaja srbija",
            "nocni vid prodaja",
            "dvogled prodaja srbija",
            "daljinomeri prodaja",
            "lovacka optika prodaja",
        ),
        keywords_en=(
            "thermal imaging Serbia",
            "night vision Serbia distributor",
            "binoculars Serbia",
            "rangefinders Serbia",
        ),
        maps_queries=(
            "lovačka optika",
            "termovizije",
            "noćni vid",
        ),
    ),
    Category(
        key="furniture_interior",
        title_ru="Мебель и интерьер (премиум)",
        title_sr="Nameštaj i enterijer (premium)",
        keywords_sr=(
            "premium namestaj prodaja srbija",
            "dizajnerski namestaj beograd",
            "komercijalni namestaj veleprodaja",
            "enterijer luksuz srbija",
        ),
        keywords_en=(
            "premium furniture Serbia",
            "designer furniture Belgrade",
            "commercial furniture Serbia",
            "luxury interior Serbia",
        ),
        maps_queries=(
            "premium nameštaj",
            "dizajnerski nameštaj",
            "luksuzni enterijer",
        ),
    ),
)


SERBIAN_CITIES: tuple[str, ...] = (
    "Beograd",
    "Novi Sad",
    "Niš",
    "Kragujevac",
    "Subotica",
    "Pančevo",
    "Čačak",
    "Kraljevo",
    "Leskovac",
    "Zrenjanin",
    "Užice",
    "Šabac",
    "Smederevo",
    "Valjevo",
)


def by_key(key: str) -> Category:
    for c in CATEGORIES:
        if c.key == key:
            return c
    raise KeyError(f"Unknown category: {key}")
