"""Скрапинг email: декодирование сущностей, SSRF-защита, MX-валидация."""
from __future__ import annotations
import html as _html
import ipaddress
import re
from urllib.parse import urlparse

from tendercore.suppliers.filters import EMAIL_RE, is_junk_email, normalize_email

try:
    import dns.resolver
    _DNS = True
except ImportError:
    _DNS = False


def is_safe_url(url: str) -> bool:
    """SSRF-гейт: только http(s), без private/loopback/localhost."""
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").lower()
    if not host or host in ("localhost", "localhost.localdomain"):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        pass
    return not host.endswith((".local", ".internal"))


def extract_emails_from_text(text: str, limit: int = 20) -> list:
    """Email из страницы: unescape сущностей + фильтр мусора."""
    if not text:
        return []
    decoded = _html.unescape(text)
    found, seen = [], set()
    for m in EMAIL_RE.finditer(decoded):
        em = normalize_email(m.group(0))
        if em in seen or is_junk_email(em):
            continue
        seen.add(em)
        found.append(em)
        if len(found) >= limit:
            break
    return found


def has_mx(domain: str) -> bool:
    """True если у домена есть MX. Без dnspython/сети — не падает."""
    if not _DNS:
        return True
    try:
        return bool(dns.resolver.resolve(domain, "MX"))
    except Exception:
        return False