"""Фильтры мусорных email и hash-доменов. Калибровка по реальным логам."""
from __future__ import annotations
import re

EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')

JUNK_LOCAL_EXACT = {"hr", "pr", "jobs", "careers", "press", "media", "abuse",
                    "postmaster", "webmaster", "noreply", "no-reply",
                    "billing", "accounting"}

JUNK_DOMAINS = ("myshopline.com", "hh.ru", "avito.ru", "vk.com",
                "facebook.com", "instagram.com", "twitter.com", "x.com",
                "linkedin.com", "youtube.com", "gosuslugi.ru",
                "wikipedia.org", "example.com", "example.ru")

_HASH_LOCAL_RE = re.compile(r'^[0-9a-f]{16,}$')


def normalize_email(raw: str) -> str:
    if not raw:
        return ""
    # 1. Убираем внешние пробелы
    # 2. Убираем краевую пунктуацию (запятые, скобки и т.д.) ВМЕСТЕ с пробелами
    # 3. Нижний регистр
    return raw.strip().strip(" \t\n\r,;:'\"<>").lower()

def is_junk_email(email: str) -> bool:
    em = normalize_email(email)
    if not EMAIL_RE.fullmatch(em):
        return True
    local, _, domain = em.partition("@")
    if local in JUNK_LOCAL_EXACT:
        return True
    if local.startswith(("recruit", "noreply", "no-reply")):
        return True
    if _HASH_LOCAL_RE.match(local):          # ab5c03d7…@sentry-new.myshopline.com
        return True
    if any(domain == d or domain.endswith("." + d) for d in JUNK_DOMAINS):
        return True
    if domain.endswith((".gov", ".gov.ru")):
        return True
    return False