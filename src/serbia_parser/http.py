"""Shared HTTP client with sane defaults for Serbian sites.

Implements per-host rate limiting so concurrent workers hitting different
hosts don't waste time waiting on each other — the global sleep that the
original version used became the dominant cost once the pipeline ran with
many parallel workers.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

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
        timeout: float = 12.0,
        retries: int = 1,
        backoff: float = 0.7,
        min_delay: float = 0.05,
        max_delay: float = 0.25,
        per_host_min_gap: float = 0.35,
    ) -> None:
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.per_host_min_gap = per_host_min_gap
        self._host_lock = threading.Lock()
        self._last_call: dict[str, float] = defaultdict(float)

    def get(self, url: str, **kwargs: Any) -> requests.Response | None:
        host = urlparse(url).netloc.lower()
        self._respect_host_gap(host)
        for attempt in range(self.retries + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout, **kwargs)
                if resp.status_code in (429, 503):
                    log.warning("HTTP %s on %s (attempt %s)", resp.status_code, url, attempt + 1)
                    time.sleep(self.backoff * (attempt + 1) * 2)
                    continue
                if resp.status_code >= 400:
                    log.debug("HTTP %s on %s", resp.status_code, url)
                self._jitter()
                return resp
            except requests.RequestException as e:
                log.debug("Request error on %s: %s", url, e)
                time.sleep(self.backoff * (attempt + 1))
        return None

    def _respect_host_gap(self, host: str) -> None:
        if not host or self.per_host_min_gap <= 0:
            return
        with self._host_lock:
            last = self._last_call.get(host, 0.0)
            wait = self.per_host_min_gap - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
            self._last_call[host] = time.monotonic()

    def _jitter(self) -> None:
        if self.max_delay <= 0:
            return
        time.sleep(random.uniform(self.min_delay, self.max_delay))
