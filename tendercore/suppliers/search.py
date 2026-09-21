"""Поисковые запросы и разбор строк поставщиков (сетевые вызовы — в клиенте)."""
from __future__ import annotations
import re

from tendercore.analysis.brand import is_non_brand


def build_search_queries(brand: str, part_number: str = "") -> list:
    """Запросы для веб-поиска. Не-бренды («III», «zip») запросов не генерируют."""
    b = (brand or "").strip()
    if not b or not re.search(r"[A-Za-z]", b) or is_non_brand(b):
        return []
    queries = [(f"{b} manufacturer official site", "manufacturer"),
               (f"{b} authorized distributor reseller supplier", "distributor")]
    if part_number:
        queries.append((f"{b} {part_number} price buy", "distributor"))
    return queries


def parse_supplier_rows(text: str) -> list:
    """Строки LLM-вывода «Компания | Страна | сайт | email | роль»."""
    rows = []
    for line in (text or "").splitlines():
        line = line.strip().strip("-| ")
        if not line or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2 or not parts[0]:
            continue
        rows.append({
            "company": parts[0],
            "country": parts[1] if len(parts) > 1 else "",
            "site":    parts[2] if len(parts) > 2 else "",
            "email":   parts[3] if len(parts) > 3 else "",
            "role":    parts[4] if len(parts) > 4 else "",
        })
    return rows


def dedupe_suppliers(rows: list) -> list:
    seen, out = set(), []
    for r in rows:
        key = r["company"].lower()
        if key and key not in seen:
            seen.add(key)
            out.append(r)
    return out