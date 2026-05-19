"""Shared HTTP client with sane defaults for Serbian sites."""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.8,ru;q=0.7",
}


class HTTP:
    def __init__(
        self,
        timeout: float = 15.0,
        retries: int = 2,
        backoff: float = 1.0,
        min_delay: float = 0.4,
        max_delay: float = 1.2,
    ) -> None:
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.min_delay = min_delay
        self.max_delay = max_delay

    def get(self, url: str, **kwargs: Any) -> requests.Response | None:
        for attempt in range(self.retries + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout, **kwargs)
                if resp.status_code in (429, 503):
                    log.warning("HTTP %s on %s (attempt %s)", resp.status_code, url, attempt + 1)
                    time.sleep(self.backoff * (attempt + 1) * 2)
                    continue
                if resp.status_code >= 400:
                    log.debug("HTTP %s on %s", resp.status_code, url)
                self._delay()
                return resp
            except requests.RequestException as e:
                log.debug("Request error on %s: %s", url, e)
                time.sleep(self.backoff * (attempt + 1))
        return None

    def _delay(self) -> None:
        time.sleep(random.uniform(self.min_delay, self.max_delay))
