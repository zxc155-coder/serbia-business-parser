"""Google Maps scraper via headless Selenium.

We iterate (category_query, city) pairs, scroll the result panel, and pull cards.
For each card we open the side panel and read the structured fields.
"""

from __future__ import annotations

import logging
import re
import time
from contextlib import suppress

from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..driver import build_driver

log = logging.getLogger(__name__)

MAPS_URL = "https://www.google.com/maps/search/{q}/?hl=sr&gl=rs"
PHONE_RE = re.compile(r"(?:\+?\s*381|0)[\d\s\-./()]{6,}\d")


def search_places(
    query: str, city: str, max_results: int = 30, headless: bool = True
) -> list[dict[str, str]]:
    """Return Maps cards (name, address, phone, website, place_url) for a query/city."""
    full_query = f"{query} {city}".strip()
    out: list[dict[str, str]] = []
    driver = None
    try:
        driver = build_driver(headless=headless)
        driver.get(MAPS_URL.format(q=full_query.replace(" ", "+")))
        # Consent screen handling.
        with suppress(Exception):
            WebDriverWait(driver, 4).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//button[.//span[contains(., 'Prihvati') or contains(., 'Accept') or contains(., 'I agree')]]",
                    )
                )
            ).click()

        feed = _wait_for_feed(driver)
        if feed is None:
            log.warning("Maps: feed never appeared for %r", full_query)
            return out

        _scroll_feed(driver, feed, target=max_results)

        cards = feed.find_elements(By.XPATH, ".//a[contains(@href,'/maps/place/')]")
        log.info("Maps: %s cards for %r", len(cards), full_query)

        seen: set[str] = set()
        for card in cards[: max_results * 2]:
            href = card.get_attribute("href") or ""
            if not href or href in seen:
                continue
            seen.add(href)
            data = _open_card(driver, card)
            if not data:
                continue
            data["place_url"] = href
            data["query"] = full_query
            data["source"] = "google_maps"
            out.append(data)
            if len(out) >= max_results:
                break
    except WebDriverException as e:
        log.warning("Maps WebDriver error for %r: %s", full_query, e)
    finally:
        if driver:
            with suppress(Exception):
                driver.quit()
    return out


def _wait_for_feed(driver):
    try:
        return WebDriverWait(driver, 12).until(
            EC.presence_of_element_located((By.XPATH, "//div[@role='feed']"))
        )
    except TimeoutException:
        # Fallback: maybe single result page opened directly.
        with suppress(NoSuchElementException):
            return driver.find_element(By.XPATH, "//div[@role='main']")
    return None


def _scroll_feed(driver, feed, target: int, max_scrolls: int = 12) -> None:
    last_count = 0
    for _ in range(max_scrolls):
        cards = feed.find_elements(By.XPATH, ".//a[contains(@href,'/maps/place/')]")
        if len(cards) >= target:
            break
        if cards and len(cards) == last_count:
            # Try one more scroll then break next iter.
            pass
        last_count = len(cards)
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", feed)
        time.sleep(1.2)


def _open_card(driver, card) -> dict[str, str] | None:
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'})", card)
        time.sleep(0.2)
        card.click()
    except WebDriverException:
        return None
    try:
        WebDriverWait(driver, 6).until(
            EC.presence_of_element_located((By.XPATH, "//h1[contains(@class,'DUwDvf')]"))
        )
    except TimeoutException:
        return None
    time.sleep(0.6)

    info: dict[str, str] = {}
    try:
        info["name"] = driver.find_element(By.XPATH, "//h1[contains(@class,'DUwDvf')]").text.strip()
    except NoSuchElementException:
        return None

    # Buttons with aria-label carry the structured fields.
    for btn in driver.find_elements(By.XPATH, "//button[@data-item-id] | //a[@data-item-id]"):
        item_id = btn.get_attribute("data-item-id") or ""
        label = btn.get_attribute("aria-label") or btn.text or ""
        label = label.strip()
        if not label:
            continue
        if item_id.startswith("address"):
            info["address"] = re.sub(r"^Adresa:\s*", "", label, flags=re.I).strip()
        elif item_id.startswith("phone:tel:") or item_id == "phone":
            info["phone"] = re.sub(r"^Telefon:\s*", "", label, flags=re.I).strip()
        elif item_id == "authority":
            info["website"] = btn.get_attribute("href") or label.strip()

    # Fallback: regex scan if data-item-id missing.
    if "phone" not in info:
        body = driver.find_element(By.XPATH, "//div[@role='main']").text
        m = PHONE_RE.search(body)
        if m:
            info["phone"] = m.group(0).strip()

    info["title"] = info.get("name", "")
    return info
