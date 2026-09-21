"""Валидация очереди RFQ: blank-сентинелы, обязательные поля.

Повторяет логику монолита (_field_is_blank / REQUIRED_TENDER_FIELDS),
чтобы в рассылку не уходили записи с прочерками вместо цены/срока/спецификации.
"""
from __future__ import annotations
import json
from pathlib import Path

BLANK_SENTINELS = {
    "", "—", "-", "–", "−",
    "не указан", "не указана", "не указано",
    "информация отсутствует", "информация отсутствует в документации",
    "нет данных", "нет",
}

REQUIRED_FIELDS = (
    "tender_number", "tender_subject", "tender_deadline",
    "tender_price", "tender_url",
)


def is_blank(value) -> bool:
    if value is None:
        return True
    s = str(value).strip()
    if s.lower() in BLANK_SENTINELS:
        return True
    try:  # цена «0» / «0,00» — тоже сентинел
        if float(s.replace(" ", "").replace(",", ".")) == 0:
            return True
    except (ValueError, TypeError):
        pass
    return False


def validate_entry(entry: dict) -> list:
    """Список проблем записи очереди (пустой список — запись валидна)."""
    problems = []
    for field in REQUIRED_FIELDS:
        if is_blank(entry.get(field)):
            problems.append(f"поле '{field}' пустое или содержит сентинел")
    items = entry.get("items_table")
    if not isinstance(items, list) or not any(
        isinstance(it, dict)
        and (str(it.get("item", "")).strip() or str(it.get("part_number", "")).strip())
        for it in items
    ):
        problems.append("'items_table' отсутствует или не содержит позиций")
    return problems


def validate_queue(payload: dict):
    """Возвращает (валидные, невалидные) записи."""
    valid, invalid = [], []
    for entry in payload.get("tenders", []):
        (valid if not validate_entry(entry) else invalid).append(entry)
    return valid, invalid


def load_queue(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_queue(path, payload: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)