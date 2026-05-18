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
            "detektori metala distributer",
            "ručni detektor metala",
            "detektori metala za hranu",
            "rudarski detektor metala",
            "detektori metala servis",
        ),
        keywords_en=(
            "metal detectors wholesale Serbia",
            "industrial metal detector Serbia distributor",
            "metal detector b2b Serbia",
            "food metal detector Serbia",
            "handheld metal detector Serbia supplier",
            "metal detector importer Belgrade",
        ),
        maps_queries=(
            "detektori metala",
            "metal detector store",
            "industrijski detektor metala",
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
            "polovne poljoprivredne masine",
            "rasipači đubriva prodaja",
            "prskalice za poljoprivredu",
            "plugovi prodaja srbija",
            "balirke prodaja",
            "voćarska mehanizacija prodaja",
        ),
        keywords_en=(
            "agricultural machinery Serbia",
            "tractors importer Serbia",
            "irrigation systems Serbia distributor",
            "combine harvester Serbia",
            "farm equipment wholesale Serbia",
            "agri machinery dealer Serbia",
            "sprayers Serbia agricultural",
        ),
        maps_queries=(
            "poljoprivredne mašine",
            "traktori prodaja",
            "sistemi za navodnjavanje",
            "poljoprivredna oprema",
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
            "struktura na cnc",
            "alatne masine prodaja",
            "strugovi prodaja srbija",
            "lasersko sečenje masine",
            "pneumatska oprema veleprodaja",
            "hidraulika industrijska prodaja",
        ),
        keywords_en=(
            "CNC machine distributor Serbia",
            "industrial compressors Serbia",
            "milling machines Serbia b2b",
            "industrial equipment supplier Serbia",
            "lathe machines Serbia",
            "laser cutting machines Serbia",
            "pneumatic equipment wholesale Serbia",
        ),
        maps_queries=(
            "CNC mašine",
            "industrijski kompresori",
            "industrijska oprema",
            "alatne mašine",
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
            "skela prodaja srbija",
            "ploce za beton prodaja",
            "valjci za asfalt prodaja",
            "rovokopaci prodaja",
            "viljuškari prodaja srbija",
            "tornjevi za beton prodaja",
        ),
        keywords_en=(
            "construction equipment Serbia",
            "excavators dealer Serbia",
            "loaders Serbia importer",
            "mini concrete plant Serbia",
            "forklifts Serbia distributor",
            "asphalt rollers Serbia",
            "scaffolding wholesale Serbia",
        ),
        maps_queries=(
            "građevinske mašine",
            "bageri prodaja",
            "utovarivači",
            "viljuškari prodaja",
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
            "stampane ploce pcb prodaja",
            "senzori industrijski prodaja",
            "elektromehanicki releji prodaja",
            "punjaci napajanja prodaja",
            "kondenzatori otpornici veleprodaja",
        ),
        keywords_en=(
            "electronic components distributor Serbia",
            "microcontrollers Serbia",
            "connectors wholesale Serbia",
            "RF modules Serbia",
            "FPGA distributor Serbia",
            "PCB manufacturer Serbia",
            "industrial sensors Serbia",
            "power supplies wholesale Serbia",
        ),
        maps_queries=(
            "elektronske komponente",
            "elektronika veleprodaja",
            "industrijski senzori",
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
            "filteri za auto veleprodaja",
            "akumulatori veleprodaja srbija",
            "amortizeri prodaja",
            "gume veleprodaja srbija",
            "menjaci prodaja srbija",
            "auto elektrika veleprodaja",
        ),
        keywords_en=(
            "auto parts wholesale Serbia",
            "motorcycle parts distributor Serbia",
            "turbochargers Serbia",
            "brake systems Serbia",
            "car batteries wholesale Serbia",
            "shock absorbers Serbia",
            "tires wholesale Serbia",
        ),
        maps_queries=(
            "auto delovi veleprodaja",
            "moto delovi",
            "turbo servis",
            "amortizeri prodaja",
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
            "rendgen aparati prodaja",
            "ekg aparati prodaja",
            "stomatoloska oprema prodaja",
            "operacione lampe prodaja",
            "medicinski potrosni materijal veleprodaja",
        ),
        keywords_en=(
            "medical equipment distributor Serbia",
            "ultrasound machine Serbia",
            "ventilators Serbia importer",
            "laboratory analyzers Serbia",
            "X-ray equipment Serbia",
            "ECG machines Serbia",
            "dental equipment Serbia",
        ),
        maps_queries=(
            "medicinska oprema",
            "ultrazvučni aparati",
            "laboratorijska oprema",
            "stomatološka oprema",
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
            "sla 3d stampac prodaja",
            "fdm 3d stampac veleprodaja",
            "3d skener za reverse engineering",
            "filament za 3d stampac veleprodaja",
            "3d stampaci servis srbija",
        ),
        keywords_en=(
            "3D printer distributor Serbia",
            "industrial 3D scanner Serbia",
            "medical 3D scanner Serbia",
            "SLA 3D printer Serbia",
            "FDM 3D printer wholesale Serbia",
            "3D printing service Serbia b2b",
        ),
        maps_queries=(
            "3D štampači",
            "3D skeneri",
            "3D printer Serbia",
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
            "puscani opticki nisani prodaja",
            "termalni monokular prodaja",
            "spektivi prodaja srbija",
            "lasersko ciljanje prodaja",
            "lovacka oprema veleprodaja",
        ),
        keywords_en=(
            "thermal imaging Serbia",
            "night vision Serbia distributor",
            "binoculars Serbia",
            "rangefinders Serbia",
            "rifle scopes Serbia",
            "thermal monocular Serbia",
            "hunting optics wholesale Serbia",
        ),
        maps_queries=(
            "lovačka optika",
            "termovizije",
            "noćni vid",
            "puščani nišani",
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
            "italijanski namestaj prodaja",
            "kancelarijski namestaj veleprodaja",
            "ugostiteljski namestaj prodaja",
            "namestaj po meri beograd",
            "rasvjeta dizajnerska prodaja",
            "hotelski namestaj veleprodaja",
        ),
        keywords_en=(
            "premium furniture Serbia",
            "designer furniture Belgrade",
            "commercial furniture Serbia",
            "luxury interior Serbia",
            "Italian furniture importer Serbia",
            "office furniture wholesale Serbia",
            "hotel furniture supplier Serbia",
        ),
        maps_queries=(
            "premium nameštaj",
            "dizajnerski nameštaj",
            "luksuzni enterijer",
            "italijanski nameštaj",
            "kancelarijski nameštaj",
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
