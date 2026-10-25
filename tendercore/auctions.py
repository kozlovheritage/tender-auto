"""Conservative, profile-scoped qualification of live price bidding.

44-FZ Art. 49(3)(1,7): prices are lowered during the auction and displayed
without bidder identities. 223-FZ mechanics cannot be inferred from a title.
"""
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import re

CONFIRMED_ELECTRONIC_AUCTIONS = frozenset(("ea20", "ea15", "ea44"))


def procedure_code(url):
    match = re.search(r"/notice/([a-z0-9]+)/", urlsplit(str(url)).path, re.I)
    return match.group(1).lower() if match else ""


def auction_search_url(url):
    """Narrow requests to 44-FZ; validate the actual method from each card.

    No guessed EIS method IDs: frontend parameters change between releases.
    The local verified-card filter is authoritative even if EIS ignores a flag.
    """
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if key not in ("fz44", "fz223", "fz94", "ppRf615")]
    query.append(("fz44", "on"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def auction_eligibility(row):
    """Return (eligible, reason). Unknown procedures fail closed, not by keyword."""
    url = str(row.get("url", ""))
    label = str(row.get("type", ""))
    if "/223/" in url or label.startswith("ФЗ 223"):
        return False, "223-ФЗ: видимость цен и повторные ставки не подтверждены"
    if not label.startswith("ФЗ 44"):
        return False, "Закон и способ закупки не определены"
    if procedure_code(url) in CONFIRMED_ELECTRONIC_AUCTIONS:
        return True, "44-ФЗ: электронный аукцион, ст. 49"
    return False, "Не подтверждён электронный аукцион по 44-ФЗ"
