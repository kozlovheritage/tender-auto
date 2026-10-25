"""Single EIS transport, shared by sampling, discovery and streamed downloads."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

from tendercore.log import get_logger
from tendercore.eis.runtime import (
    EisNetworkError, EisStopError, get_runtime, retry_after_seconds,
)

log = get_logger("eis")
DEFAULT_TIMEOUT = (10, 60)
RETRY_STATUSES = (500, 502, 503, 504)


def _close(response):
    close = getattr(response, "close", None)
    if close:
        close()


def _safe_url(url):
    try:
        parsed = urlsplit(str(url))
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as exc:
        raise EisNetworkError("Некорректная ссылка ЕИС") from exc
    if parsed.username or parsed.password or not (host == "zakupki.gov.ru" or host.endswith(".zakupki.gov.ru")):
        raise EisNetworkError("Ссылка вне домена ЕИС: автоматический переход запрещён")
    if parsed.scheme not in ("http", "https") or port not in (None, 80, 443):
        raise EisNetworkError("Неподдерживаемая схема или порт ссылки ЕИС")
    return urlunsplit(("https", host, parsed.path, parsed.query, ""))


def _challenge(html):
    match = re.search(r"<title[^>]*>(.*?)</title>", str(html), re.I | re.S)
    return bool(match and re.search(
        r"access\s+denied|доступ\s+ограничен|доступ\s+запрещ[её]н|"
        r"проверка\s+безопасности|captcha|капча",
        match.group(1), re.I,
    ))


class EisClient:
    def __init__(self, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                 verify=True, backoff_base=1.0, *, runtime=None, state_dir=None):
        self._s = requests.Session()
        self._s.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.5",
        })
        self._verify = verify
        self._ssl_fallback_done = False
        self._backoff = max(0.0, float(backoff_base))
        self.runtime = runtime if runtime is not None else get_runtime(state_dir)

    @property
    def headers(self):
        return self._s.headers

    @property
    def proxies(self):
        return self._s.proxies

    @proxies.setter
    def proxies(self, value):
        self._s.proxies = value

    @property
    def verify(self):
        return self._verify

    @verify.setter
    def verify(self, value):
        self._verify = value

    def close(self):
        self._s.close()

    def get(self, url, retries=3, timeout=DEFAULT_TIMEOUT, stream=False, max_requests=5, **kwargs):
        from tendercore.eis.protocol import diagnostic, html_kind, phase
        current = _safe_url(url)
        attempts = max(1, min(int(retries), 3))
        budget = max(1, min(int(max_requests), 5))
        follow = kwargs.pop("allow_redirects", True)
        kwargs.setdefault("verify", self._verify)
        redirects = 0
        attempt = 0
        sent = 0
        last_error = None
        while sent < budget:
            attempt += 1
            sent += 1
            try:
                response = self.runtime.raw_get(
                    self._s.get, current, timeout=timeout, stream=stream,
                    allow_redirects=False, **kwargs)
            except EisNetworkError:
                raise
            except requests.exceptions.SSLError as exc:
                last_error = exc
                diagnostic(current, attempt=attempt, requests=sent, category="tls-error")
                # Preserve existing behavior; TLS policy is a separate migration.
                if not self._ssl_fallback_done and self._verify:
                    self._ssl_fallback_done = True
                    self._verify = False
                    kwargs["verify"] = False
                    phase("ЕИС: SSL-фолбэк отключил проверку сертификата (прежнее поведение)")
            except requests.exceptions.RequestException as exc:
                last_error = exc
                diagnostic(current, attempt=attempt, requests=sent, category="connection-error")
            else:
                response._eis_requests = sent
                response._eis_attempt = attempt
                response._eis_url = current
                status = int(response.status_code)
                headers = getattr(response, "headers", {}) or {}
                retry_after = retry_after_seconds(headers.get("Retry-After"), self.runtime.clock())
                if status != 200:
                    diagnostic(current, response, attempt=attempt, requests=sent, category="http")
                if status in (401, 429):
                    _close(response)
                    seconds = 1800 if status == 401 else 900
                    self.runtime.stop(f"HTTP {status}: ЕИС ограничила доступ", retry_after if retry_after is not None else seconds, status)
                if status == 403:
                    _close(response)
                    if retry_after is not None or "filestore" not in urlsplit(current).path.lower() or self.runtime.forbidden_streak >= 2:
                        self.runtime.stop("HTTP 403: ЕИС отказала в доступе", retry_after if retry_after is not None else 1800, 403)
                    raise EisNetworkError("HTTP 403: документ недоступен; повторы и запасные ссылки отменены")
                if status in RETRY_STATUSES:
                    _close(response)
                    wait = retry_after if retry_after is not None else 45.0 * (2 ** (attempt - 1)) * self._backoff
                    if attempt >= attempts or sent >= budget or wait > 120:
                        self.runtime.stop(f"ЕИС HTTP {status}: попытки исчерпаны", max(45.0, wait), status)
                    phase(f"ЕИС: HTTP {status}; повтор {attempt + 1}/{attempts} через {wait:.0f} с")
                    self.runtime.metrics["retries"] += 1
                    self.runtime.wait(wait)
                    continue
                if status in (301, 302, 303, 307, 308) and follow:
                    location = headers.get("Location")
                    _close(response)
                    if not location or redirects >= 4 or sent >= budget:
                        raise EisNetworkError("ЕИС: исчерпан лимит перенаправлений/запросов")
                    current = _safe_url(urljoin(current, location))
                    redirects += 1
                    attempt = 0
                    continue
                if status == 200 and not stream:
                    kind = html_kind(getattr(response, "text", ""))
                    if kind in ("access-check", "login", "service-unavailable"):
                        diagnostic(current, response, attempt=attempt, requests=sent,
                                   size=len(response.content), category=kind)
                        _close(response)
                        self.runtime.stop("ЕИС вернула страницу проверки доступа или недоступности", 900, 200)
                return response
            if attempt >= attempts or sent >= budget:
                break
            wait = self._backoff * 2 ** (attempt - 1)
            phase(f"ЕИС: ошибка соединения; повтор через {wait:.0f} с")
            self.runtime.metrics["retries"] += 1
            self.runtime.wait(wait)
        raise EisNetworkError("ЕИС: соединение не восстановлено; лимит попыток исчерпан") from last_error
