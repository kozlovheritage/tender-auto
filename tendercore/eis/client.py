"""HTTP-клиент ЕИС: таймауты, SSL-фолбэк, ретраи 502/503/429.

Заменяет monkey-patch v8 и разрозненные session.get по монолиту.
"""
from __future__ import annotations
import time

import requests

from tendercore.log import get_logger

log = get_logger("eis")

DEFAULT_TIMEOUT = (10, 60)          # (connect, read)
RETRY_STATUSES = (502, 503, 429)


class EisNetworkError(Exception):
    """Сетевая/HTTP-ошибка ЕИС: тендер не пишем в БД, повторится в след. прогон."""


class EisClient:
    def __init__(self, user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                         "AppleWebKit/537.36",
                 verify: bool = True, backoff_base: float = 1.0):
        self._s = requests.Session()
        self._s.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.5",
        })
        self._verify = verify
        self._ssl_fallback_done = False
        self._backoff = backoff_base

    def get(self, url: str, retries: int = 3, timeout=DEFAULT_TIMEOUT,
            stream: bool = False) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                resp = self._s.get(url, timeout=timeout, verify=self._verify,
                                   stream=stream)
            except requests.exceptions.SSLError as e:
                last_exc = e
                if not self._ssl_fallback_done:
                    self._ssl_fallback_done = True
                    self._verify = False
                    log.warning("⚠️ SSL-фолбэк (VPN/ТСПУ): verify отключена")
                    continue
                time.sleep(self._backoff * 2 ** attempt)
                continue
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as e:
                last_exc = e
                time.sleep(self._backoff * 2 ** attempt)
                continue
            if resp.status_code in RETRY_STATUSES:
                last_exc = EisNetworkError(f"HTTP {resp.status_code}: {url}")
                time.sleep(self._backoff * 2 ** attempt)
                continue
            return resp
        raise EisNetworkError(f"{url}: {last_exc}")