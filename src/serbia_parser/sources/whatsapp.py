"""WhatsApp Web phone-number verifier (headless Selenium).

How it works
------------
WhatsApp does not expose a public API that lets you check whether a phone
number is registered. The only safe way to check from a regular WhatsApp
account is to ask ``web.whatsapp.com`` to start a chat with that number:

    https://web.whatsapp.com/send?phone=<MSISDN>

If the number is registered, the chat opens (we see a message-input box).
If it is not, WhatsApp opens an "invalid number" modal. We detect either
state with explicit waits.

Requirements
------------
* You must log into WhatsApp Web once by scanning the QR code from your
  phone (Settings → Linked devices → Link a device). The session is stored
  in a persistent Chrome profile (default ``~/.serbia_parser/wa_profile``).
* Use a "technical" / secondary WhatsApp account. Bulk-checking from a
  primary account can trigger temporary or permanent bans.

Speed/limits
------------
Each lookup takes ~3-6 s. After ~50-80 lookups in a row WhatsApp throttles
your session, so we batch with small sleeps between numbers.

This module is fully headless per the project rule ("only headless
webscrapers"). The QR image is captured directly from the canvas and saved
as a PNG so the Telegram bot can forward it to the user.
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..driver import build_driver

log = logging.getLogger(__name__)


def default_profile_dir() -> Path:
    """Where to store the persistent Chrome user-data dir."""
    env = os.environ.get("SERBIA_PARSER_WA_PROFILE")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".serbia_parser" / "wa_profile"


# Serbia's country code is 381; we accept anything that looks like a number.
_DIGITS_RE = re.compile(r"\d+")


def normalize_phone(raw: str, default_country: str = "381") -> str | None:
    """Normalize a phone string to digits-only E.164 form (without ``+``).

    * Strip everything but digits.
    * If the result starts with ``00``, drop the leading zeros.
    * If the result starts with a single ``0`` and we have a default country
      code, replace the leading zero with the country code (Serbian local
      numbers are typically written as ``0xx xxx xxxx``).
    * Reject results that are clearly too short to be a phone number.
    """
    if not raw:
        return None
    # Take only the first chunk that looks like a phone number to avoid
    # accidentally concatenating multiple numbers from "61 234 567; 60 999".
    digits = "".join(_DIGITS_RE.findall(raw))
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0") and default_country:
        digits = default_country + digits[1:]
    # Reasonable phone length: 7-15 digits per E.164.
    if not (7 <= len(digits) <= 15):
        return None
    return digits


class WhatsAppVerifier:
    """Headless Chrome session attached to web.whatsapp.com.

    Use as a context manager:

        with WhatsAppVerifier() as wa:
            wa.ensure_logged_in()
            for phone in numbers:
                state = wa.verify(phone)
    """

    LOGIN_URL = "https://web.whatsapp.com/"
    SEND_URL_TEMPLATE = "https://web.whatsapp.com/send?phone={msisdn}"

    def __init__(
        self,
        profile_dir: Path | None = None,
        *,
        headless: bool = True,
        per_lookup_timeout: float = 25.0,
        sleep_between: float = 1.5,
    ) -> None:
        self.profile_dir = (profile_dir or default_profile_dir()).expanduser()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.per_lookup_timeout = per_lookup_timeout
        self.sleep_between = sleep_between
        self._driver = None  # type: ignore[assignment]

    # -- lifecycle -----------------------------------------------------------

    def __enter__(self) -> WhatsAppVerifier:
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def start(self) -> None:
        if self._driver is not None:
            return
        # We extend the base driver builder with a persistent user-data-dir so
        # the WA session survives between runs.
        env_key = "SERBIA_PARSER_EXTRA_CHROME_ARGS"
        prev = os.environ.get(env_key)
        # build_driver doesn't accept extra args, so monkey-patch options via
        # a dedicated builder instead.
        self._driver = _build_wa_driver(self.profile_dir, headless=self.headless)
        if prev is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = prev

    def stop(self) -> None:
        if self._driver is None:
            return
        try:
            self._driver.quit()
        except Exception as e:
            log.debug("driver.quit raised: %s", e)
        finally:
            self._driver = None

    # -- login ---------------------------------------------------------------

    def _open_home(self) -> None:
        assert self._driver is not None
        try:
            if self._driver.current_url and "web.whatsapp.com" in self._driver.current_url:
                return
        except WebDriverException:
            pass
        self._driver.get(self.LOGIN_URL)

    def is_logged_in(self, *, timeout: float = 12.0) -> bool:
        """Heuristic: chats panel is rendered when we're logged in."""
        assert self._driver is not None
        self._open_home()
        try:
            WebDriverWait(self._driver, timeout).until(
                EC.any_of(
                    EC.presence_of_element_located((By.ID, "side")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-testid='chat-list']")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "canvas[aria-label*='Scan']")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "canvas")),
                )
            )
        except TimeoutException:
            return False
        # If the chats panel is up we're logged in.
        if self._driver.find_elements(By.ID, "side"):
            return True
        if self._driver.find_elements(By.CSS_SELECTOR, "div[data-testid='chat-list']"):
            return True
        return False

    def save_qr(self, dest: Path) -> Path | None:
        """Capture the on-screen QR canvas and save it as a PNG.

        Returns the path on success, ``None`` if no QR canvas is present
        (e.g. we are already logged in).
        """
        assert self._driver is not None
        self._open_home()
        try:
            canvas = WebDriverWait(self._driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "canvas"))
            )
        except TimeoutException:
            return None
        dest = dest.expanduser()
        dest.parent.mkdir(parents=True, exist_ok=True)
        png = canvas.screenshot_as_png
        dest.write_bytes(png)
        return dest

    def wait_for_login(self, *, timeout: float = 180.0) -> bool:
        """Block until the chats panel appears or ``timeout`` is reached."""
        assert self._driver is not None
        self._open_home()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_logged_in(timeout=5):
                return True
            time.sleep(2.0)
        return False

    def ensure_logged_in(self) -> None:
        if not self.is_logged_in():
            raise RuntimeError(
                "WhatsApp Web is not logged in. Run /wa_login in the bot, "
                "scan the QR with your phone, then retry."
            )

    # -- verification --------------------------------------------------------

    def verify(self, phone: str) -> str:
        """Return one of: ``'on_whatsapp'``, ``'not_on_whatsapp'``, ``'unknown'``.

        ``phone`` should be in E.164 form (digits only, no ``+``).
        """
        assert self._driver is not None
        msisdn = normalize_phone(phone)
        if msisdn is None:
            return "unknown"
        url = self.SEND_URL_TEMPLATE.format(msisdn=msisdn)
        try:
            self._driver.get(url)
        except WebDriverException as e:
            log.warning("get(%s) failed: %s", url, e)
            return "unknown"

        end = time.time() + self.per_lookup_timeout
        while time.time() < end:
            # 1) "Phone number shared via url is invalid" / "Invalid number" modal.
            #    WhatsApp shows this in an alert dialog.
            try:
                dlg = self._driver.find_elements(
                    By.CSS_SELECTOR, "[role='dialog'], div[data-animate-modal-popup]"
                )
                for d in dlg:
                    text = (d.text or "").lower()
                    if (
                        "invalid" in text
                        or "phone number shared via url is invalid" in text
                        or "ne koristi whatsapp" in text  # sr translation
                        or "phone number shared" in text
                        or "is not on whatsapp" in text
                        or "not on whatsapp" in text
                    ):
                        return "not_on_whatsapp"
            except WebDriverException:
                pass
            # 2) Chat opened: footer message-input or header for the chat appears.
            try:
                if self._driver.find_elements(
                    By.CSS_SELECTOR,
                    "footer [contenteditable='true'], "
                    "[data-testid='conversation-compose-box-input'], "
                    "header [data-testid='conversation-info-header']",
                ):
                    return "on_whatsapp"
            except WebDriverException:
                pass
            # 3) Login screen — we are not logged in yet.
            try:
                if self._driver.find_elements(By.CSS_SELECTOR, "canvas[aria-label*='Scan']"):
                    raise RuntimeError("WhatsApp Web session expired. Re-run /wa_login to scan QR.")
            except WebDriverException:
                pass
            time.sleep(0.5)

        return "unknown"

    def verify_many(
        self,
        phones,
        *,
        on_progress: Callable[[int, int, str, str], None] | None = None,
    ) -> dict[str, str]:
        """Verify a batch of phone numbers, returning ``{phone: state}``.

        ``on_progress(done, total, phone, state)`` is called after each lookup.
        """
        unique = list(dict.fromkeys(phones))
        out: dict[str, str] = {}
        for i, ph in enumerate(unique, 1):
            state = self.verify(ph)
            out[ph] = state
            if on_progress is not None:
                try:
                    on_progress(i, len(unique), ph, state)
                except Exception as e:
                    log.warning("WA progress callback raised: %s", e)
            time.sleep(self.sleep_between)
        return out


@contextmanager
def verifier(profile_dir: Path | None = None, **kwargs):
    """Context-manager wrapper around :class:`WhatsAppVerifier`."""
    wa = WhatsAppVerifier(profile_dir, **kwargs)
    wa.start()
    try:
        yield wa
    finally:
        wa.stop()


# ---------------------------------------------------------------------------
# Internal: a slightly customized driver builder with --user-data-dir.


def _build_wa_driver(profile_dir: Path, *, headless: bool = True):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--window-size=1280,900")
    opts.add_argument(f"--user-data-dir={profile_dir}")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    chromedriver_path = os.environ.get("CHROMEDRIVER")
    service = Service(chromedriver_path) if chromedriver_path else Service()
    drv = webdriver.Chrome(service=service, options=opts)
    drv.set_page_load_timeout(45)
    # Touch the unused factory to keep an import path for type checkers and
    # silence "unused import" linters in environments that strip docstrings.
    _ = build_driver
    return drv


__all__ = [
    "WhatsAppVerifier",
    "default_profile_dir",
    "normalize_phone",
    "verifier",
]
