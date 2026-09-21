"""Определение типа извещения и noticeGuid (44-ФЗ и 223-ФЗ).

Стратегия (вместо «cannot unpack NoneType» из монолита):
  1. 223-ФЗ (11 цифр или ссылка /223/) → GUID со страницы извещения
  2. 44-ФЗ → перебор типов (ea20/zk20/...) + восстановление ведущего нуля
  3. Фолбэк: поиск ЕИС по номеру → тип из href
  4. Иначе NoticeNotFoundError (тендер уйдёт в ошибки, повторится завтра)
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional

from tendercore.log import get_logger

log = get_logger("eis.guid")

GUID_RE = re.compile(
    r'([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})')

TYPES_44 = ("ea20", "zk20", "ok20", "ep20", "kt20", "ap20", "ik20", "kn20")

BASE = "https://zakupki.gov.ru"


class NoticeNotFoundError(Exception):
    """Тип/GUID не определены ни перебором, ни поиском."""


@dataclass
class NoticeInfo:
    reg: str
    law: str                      # "44" | "223"
    notice_type: str              # ea20 / zk20 / notice223 / ...
    guid: Optional[str] = None
    guid_optional: bool = False   # ea20-SPA: документы без GUID


def norm_reg(reg: str) -> list:
    """Варианты номера: как есть + с восстановленным ведущим нулём."""
    r = reg.strip()
    variants = [r]
    if r.isdigit() and not r.startswith("0"):
        variants.append("0" + r)
    return variants


def _law_by_reg(reg: str) -> str:
    return "223" if reg.isdigit() and len(reg) == 11 else "44"


def _guid_from_223_page(client, reg: str) -> Optional[str]:
    url = (f"{BASE}/223/purchase/public/purchase/info/common-info.html"
           f"?regNumber={reg}")
    try:
        resp = client.get(url, retries=2)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    m = GUID_RE.search(resp.text)
    return m.group(1) if m else None


def _search_eis(client, reg: str) -> Optional[NoticeInfo]:
    url = (f"{BASE}/epz/order/extendedsearch/results.html"
           f"?searchString={reg}&morphology=off&sortBy=UPDATE_DATE")
    try:
        resp = client.get(url, retries=2)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    for href in re.findall(r'href="([^"]+)"', resp.text):
        if f"regNumber={reg}" not in href:
            continue
        if "/223/" in href:
            return NoticeInfo(reg, "223", "notice223",
                              guid=_guid_from_223_page(client, reg))
        mt = re.search(r'/notice/([a-z0-9]+)/', href)
        t = mt.group(1) if mt else "ea20"
        log.info(f"ЕИС-поиск: тип {t} найден через поиск")
        return NoticeInfo(reg, "44", t, guid_optional=(t == "ea20"))
    return None


def resolve_notice(client, reg: str, row_url: str = "") -> NoticeInfo:
    variants = norm_reg(reg)

    # 1) 223-ФЗ: из ссылки выгрузки или по длине номера
    if "/223/" in row_url or _law_by_reg(reg) == "223":
        info = NoticeInfo(reg, "223", "notice223")
        info.guid = _guid_from_223_page(client, reg)
        if info.guid:
            log.info(f"Тип извещения: notice223, GUID: {info.guid}")
        return info

    # 2) 44-ФЗ: перебор типов
    for t in TYPES_44:
        for r in variants:
            url = (f"{BASE}/epz/order/notice/{t}/common-info.html"
                   f"?regNumber={r}")
            try:
                resp = client.get(url, retries=2)
            except Exception:
                continue
            if resp.status_code == 200 and (f"regNumber={r}" in resp.text
                                            or f"№ {r}" in resp.text):
                m = GUID_RE.search(resp.text)
                info = NoticeInfo(r, "44", t, guid=m.group(1) if m else None,
                                  guid_optional=(t == "ea20"))
                log.info(f"Тип извещения: {t}"
                         + (f", GUID: {info.guid}" if info.guid
                            else " (SPA, GUID не требуется)"))
                return info

    # 3) Фолбэк: поиск ЕИС
    for r in variants:
        found = _search_eis(client, r)
        if found:
            return found

    raise NoticeNotFoundError(f"Не найден noticeGuid для {reg}")