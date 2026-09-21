# tendercore-config v2.1
"""Загрузчик конфигурации (этап 2.1).

Порядок поиска:
  1. переменная окружения TENDER_CONFIG (точный путь к файлу)
  2. <текущая папка>/config/settings.toml
  3. <корень проекта>/config/settings.toml (относительно пакета)

Файла нет / битый — молча работаем на дефолтах (= текущее поведение кода).
"""
from __future__ import annotations
import os
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None

DEFAULTS = {
    "thresholds": {
        "min_delivery_days": 30,
    },
    "extraction": {
        "max_text_total": 200000,
        "max_text_per_file": 40000,
    },
}

_cache = None


def _find_config_path():
    env = os.environ.get("TENDER_CONFIG", "").strip()
    if env:
        p = Path(env)
        return p if p.is_file() else None
    for cand in (
        Path.cwd() / "config" / "settings.toml",
        Path(__file__).resolve().parent.parent / "config" / "settings.toml",
    ):
        if cand.is_file():
            return cand
    return None


def _deep_merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load(force=False):
    global _cache
    if _cache is not None and not force:
        return _cache
    path = _find_config_path()
    if path is None or tomllib is None:
        _cache = DEFAULTS
        return _cache
    try:
        with open(path, "rb") as f:
            user_cfg = tomllib.load(f)
        _cache = _deep_merge(DEFAULTS, user_cfg)
    except Exception as e:
        print(f"⚠️ Конфиг {path}: ошибка чтения ({e}) — работаю на дефолтах")
        _cache = DEFAULTS
    return _cache


def get(*keys, default=None):
    """get('thresholds', 'min_delivery_days') -> значение из конфига."""
    cur = load()
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def reset():
    """Сброс кэша (тесты / горячая перезагрузка конфига)."""
    global _cache
    _cache = None


def config_path():
    """Активный файл конфига (для диагностики)."""
    return _find_config_path()
