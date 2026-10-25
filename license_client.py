#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Клиентская лицензия: офлайн-проверка подписанного ключа + срок + HWID.
Ключи генерирует автор (keygen.py). Проверка работает без сервера —
продажи возможны сразу; сервер (этап 3) автоматизирует выдачу позже.
"""
import base64, datetime, hashlib, hmac, json, platform, uuid
from pathlib import Path

import sys as _sysf
if getattr(_sysf, "frozen", False):
    BASE = Path(_sysf.executable).resolve().parent
else:
    BASE = Path(__file__).resolve().parent
LIC_DIR = BASE / "license"
KEY_PATH = LIC_DIR / "key.txt"
SECRET = __import__("os").environ.get("TENDER_AUTO_LICENSE_SECRET", "").encode("utf-8")


def get_hwid():
    raw = f"{uuid.getnode()}|{platform.machine()}|{platform.node()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _sign(payload: dict) -> str:
    if len(SECRET) < 32:
        raise ValueError("Set your own TENDER_AUTO_LICENSE_SECRET (at least 32 characters)")
    body = json.dumps(payload, sort_keys=True).encode()
    sig = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(json.dumps(
        {"b": base64.urlsafe_b64encode(body).decode(), "s": sig}).encode()).decode()


def _unsign(token: str):
    if len(SECRET) < 32:
        return None
    try:
        outer = json.loads(base64.urlsafe_b64decode(token))
        body = base64.urlsafe_b64decode(outer["b"])
        if not hmac.compare_digest(
                hmac.new(SECRET, body, hashlib.sha256).hexdigest(), outer["s"]):
            return None
        return json.loads(body)
    except Exception:
        return None


def load_key():
    try:
        return (LIC_DIR / "key.txt").read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def save_key(key: str):
    LIC_DIR.mkdir(parents=True, exist_ok=True)
    (LIC_DIR / "key.txt").write_text(key.strip(), encoding="utf-8")


def validate(enabled=True):
    """Возвращает (ok, message, info)."""
    if not enabled:
        return True, "демо-режим (лицензия выключена)", {"plan": "demo"}
    if len(SECRET) < 32:
        return False, "не настроен TENDER_AUTO_LICENSE_SECRET для собственной сборки", {}
    key = load_key()
    if not key:
        return False, "нет лицензионного ключа", {}
    info = _unsign(key)
    if not info:
        return False, "ключ повреждён или поддельный", {}
    bound = info.get("hwid") or ""
    if bound and bound != get_hwid():
        return False, "ключ привязан к другому компьютеру", info
    try:
        exp = datetime.date.fromisoformat(info["expiry"])
    except Exception:
        return False, "в ключе нет срока действия", info
    if exp < datetime.date.today():
        return False, f"подписка истекла {exp:%d.%m.%Y}", info
    return True, f"активна до {exp:%d.%m.%Y} · тариф {info.get('plan', '?')}", info