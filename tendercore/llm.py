"""tendercore.llm — вызов LLM и разбор ответа. Headless: только logging.

Портировано из tender_auto.py: call_deepseek, classify/clean/postprocess,
полнота ответа. Чистые функции тестируемы офлайн.
"""
from __future__ import annotations
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests

from tendercore.log import get_logger

log = get_logger("llm")

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "qwen/qwen3-235b-a22b-2507"


@dataclass
class LLMConfig:
    deepseek_key: str = ""
    openrouter_key: str = ""
    http_referer: str = "https://vitro-logistic.ru"
    x_title: str = "Vitro Tender Tool"
    temperature: float = 0.2


def call_llm(prompt: str, cfg: LLMConfig) -> Optional[str]:
    """Единая точка вызова: DeepSeek (основной) → OpenRouter (резерв)."""
    if cfg.deepseek_key:
        url, model, timeout = DEEPSEEK_URL, "deepseek-chat", 90
        headers = {"Authorization": f"Bearer {cfg.deepseek_key}",
                   "Content-Type": "application/json"}
    elif cfg.openrouter_key:
        url, model, timeout = OPENROUTER_URL, OPENROUTER_MODEL, 120
        headers = {"Authorization": f"Bearer {cfg.openrouter_key}",
                   "Content-Type": "application/json",
                   "HTTP-Referer": cfg.http_referer, "X-Title": cfg.x_title}
    else:
        log.warning("LLM: ключи не заданы (DEEPSEEK/OPENROUTER) — вызов пропущен")
        return None

    payload = {"model": model,
               "messages": [{"role": "user", "content": prompt}],
               "temperature": cfg.temperature}
    for attempt in range(5):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            if resp.status_code == 401:
                log.error("LLM: 401 (неверный ключ) — повторы бессмысленны")
                return None
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                log.warning(f"LLM: 429 (rate limit) — ждём {wait} с")
                time.sleep(wait)
            else:
                log.warning(f"LLM: HTTP {resp.status_code}, попытка {attempt + 1}")
                time.sleep(5)
        except requests.exceptions.SSLError as e:
            wait = 15 * (attempt + 1)
            log.warning(f"LLM: SSL-ошибка: {e} — ждём {wait} с")
            time.sleep(wait)
        except Exception as e:
            wait = 5 * (2 ** attempt)
            log.warning(f"LLM: исключение: {e} — ждём {wait} с")
            time.sleep(wait)
    return None


# ========================= РАЗБОР ОТВЕТА =========================
_SELF_CONTRADICTION_PHRASES = (
    'не является стоп-фактором', 'стоп-фактор не применяется',
    'стоп-фактор не срабатывает', 'решение пересмотрено',
    'стоп фактор не применяется',
)
_STOPFACTOR_TRIGGERED_PHRASES = (
    'стоп-фактор срабатывает', 'стоп фактор срабатывает',
    'применяется стоп-фактор', 'стоп-фактор применяется',
    'стоп фактор применяется', 'срабатывает стоп-фактор',
    'срабатывает стоп фактор',
)
_STOPFACTOR_TRIGGERED_RE = re.compile(
    r'стоп[\s\-]?фактор\s*(?:#\s*\d+\s*)?(?:срабатывает|применяется)|'
    r'(?:срабатывает|применяется)\s*стоп[\s\-]?фактор',
    re.IGNORECASE)


def _has_self_contradiction(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in _SELF_CONTRADICTION_PHRASES)


def _has_stopfactor_triggered(text: str) -> bool:
    lower = text.lower()
    if any(p in lower for p in _STOPFACTOR_TRIGGERED_PHRASES):
        return True
    return bool(_STOPFACTOR_TRIGGERED_RE.search(text))


def classify_response(response: str) -> str:
    """Определяет решение: participate / clarify / not_participate."""
    lines = response.split('\n')
    for line in lines:
        stripped = line.strip()
        if not stripped.lower().startswith('решение:'):
            continue
        decision_part = line.split(':', 1)[1].strip().lower()
        if 'не участвуем' in decision_part:
            short_label = decision_part[:300]
            if _has_self_contradiction(short_label) and not _has_stopfactor_triggered(response):
                return 'clarify'
            return 'not_participate'
        elif 'участвуем' in decision_part:
            if _has_stopfactor_triggered(response):
                return 'not_participate'
            return 'participate'
        elif 'требуется уточнение' in decision_part:
            if _has_stopfactor_triggered(response):
                return 'not_participate'
            return 'clarify'
        break
    first_lines = '\n'.join(response.split('\n')[:10]).lower()
    if 'не участвуем' in first_lines:
        short = first_lines[:400]
        if _has_self_contradiction(short) and not _has_stopfactor_triggered(response):
            return 'clarify'
        return 'not_participate'
    elif 'участвуем' in first_lines:
        return 'participate'
    elif 'требуется уточнение' in first_lines:
        return 'clarify'
    return 'clarify'


# алиас для совместимости с именами монолита
classify_deepseek_response = classify_response


def extract_rejection_reason(response: str) -> str:
    for line in response.split('\n'):
        if line.strip().startswith('Решение:') and 'не участвуем' in line:
            m = re.search(r'Причина:\s*(.+)', line, re.IGNORECASE)
            if m:
                return m.group(1).strip()
            parts = line.split('не участвуем', 1)
            if len(parts) > 1:
                reason = parts[1].strip().lstrip('.,;: ')
                if reason:
                    return reason
    return "не указана"


def extract_china_flag(response: str) -> bool:
    m = re.search(r'Доступность закупки в Китае:\s*(Да|Нет)', response, re.IGNORECASE)
    if m:
        return m.group(1).lower() == 'да'
    if re.search(r'(китай|china)', response, re.IGNORECASE):
        if not re.search(r'(запрет|только российское|не допускаются)', response, re.IGNORECASE):
            return True
    return False


def clean_response_preamble(response: str) -> str:
    """Убирает <think> и дубли «Решение:», оставляет последний структурный отчёт."""
    response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
    all_lines = response.split('\n')
    decision_indices = [i for i, l in enumerate(all_lines)
                        if l.strip().lower().startswith('решение:')]
    if len(decision_indices) > 1:
        keep_idx = decision_indices[-1]
        all_lines = [l for i, l in enumerate(all_lines)
                     if not l.strip().lower().startswith('решение:') or i == keep_idx]
        response = '\n'.join(all_lines)
    matches = list(re.finditer(r'---\s*Основная информация\s*---', response))
    if matches:
        start = matches[-1].start()
        preceding = [l for l in response[:start].splitlines() if l.strip()]
        decision_prefix = ""
        for line in reversed(preceding[-5:]):
            if line.strip().lower().startswith('решение:'):
                decision_prefix = line.strip() + "\n"
                break
        response = decision_prefix + response[start:]
        return response
    section_match = re.search(r'---\s+\S', response)
    if section_match:
        response = response[section_match.start():]
    return response


def postprocess_response(response: str, combined_hints: str) -> str:
    """Замены фраз, автоподстановка срока, исправление НДС 22%→20%."""
    response = re.sub(r'не удалось определить', 'информация отсутствует в документации',
                      response, flags=re.IGNORECASE)
    response = re.sub(r'(Срок приемки:\s*)(информация отсутствует в документации)',
                      r'\g<1>1 рабочий день', response, flags=re.IGNORECASE)
    if "возможный срок поставки:" in combined_hints:
        m = re.search(r'возможный срок поставки:\s*(\d+)', combined_hints)
        if m:
            days = m.group(1)
            if re.search(r'Срок поставки:\s*информация отсутствует в документации',
                         response, re.IGNORECASE):
                response = re.sub(r'(Срок поставки:\s*)информация отсутствует в документации',
                                  r'\g<1>' + str(days) + ' дней', response, flags=re.IGNORECASE)
                log.info(f"Принудительно установлен срок поставки: {days} дней")

    def _fix_nds_rate(m):
        return re.sub(r'\b22\s*%', '20%', m.group(0))

    response = re.sub(r'^НДС:[^\n]*$', _fix_nds_rate, response,
                      flags=re.IGNORECASE | re.MULTILINE)
    return response


def analyze_response_completeness(response_text: str) -> list:
    """Возвращает список отсутствующих обязательных полей раздела «Основная информация»."""
    required = ["Заказчик", "Срок поставки", "Адрес поставки", "НМЦК/НМЦД"]
    missing = []
    empty = {'информация отсутствует в документации', 'не удалось определить', '—', '', 'не указано'}
    parts = re.split(r'\n---\s*(.*?)\s*---\n', response_text, flags=re.DOTALL)
    for i in range(1, len(parts) - 1, 2):
        if parts[i].strip() != "Основная информация":
            continue
        field_values = {}
        for line in parts[i + 1].split('\n'):
            if ':' in line:
                key, val = line.split(':', 1)
                field_values[key.strip()] = val.strip().lower()
        for field in required:
            if field not in field_values:
                missing.append(field)
            elif field_values[field] in empty:
                missing.append(field)
        break
    return missing