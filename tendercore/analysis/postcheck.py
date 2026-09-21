"""Python-валидации ответа LLM — страховки от галлюцинаций (без сети)."""
from __future__ import annotations
import math
import re
from typing import Optional, Tuple

MIN_DELIVERY_DAYS = 30
HARD_MAX_ITEMS = 50

_MISSING = ('информация отсутствует', 'не указан', 'не определён',
            'не установлен', 'не указано', 'уточняется')

_CYR_MODEL_RE = re.compile(r'\b([А-ЯЁ]{2,6})[-\s]?(\d[\w\-]*)\b')
_CYR_MODEL_EXCLUDE = {'ООО', 'АО', 'ЗАО', 'ПАО', 'ГУП', 'МУП', 'ФГБУ', 'ФГБУН',
                      'МСП', 'СМП', 'НМЦ', 'НМЦК', 'ТЗ', 'ЕД', 'ШТ', 'ГОСТ', 'ТК', 'РД'}

_MATERIAL_RE = re.compile(
    r'(топлив|керосин|масл\w|материал|сырь|комплектующ|смазк|бензин|дизель)',
    re.IGNORECASE)


def validate_delivery_term(response: str,
                           min_days: int = None
                           ) -> Tuple[Optional[int], Optional[str]]:
    # этап 2.1: порог из config/settings.toml
    from tendercore.config import get as _cfg_get
    if min_days is None:
        min_days = int(_cfg_get('thresholds', 'min_delivery_days',
                                  default=30) or 30)
    """Стоп-фактор #2: срок поставки < min_days календарных."""
    match = re.search(r'Срок поставки:\s*([^\n]+)', response, re.IGNORECASE)
    if not match:
        return None, None
    term = match.group(1).strip()
    if any(x in term.lower() for x in _MISSING):
        return None, None
    if re.search(r'\d{1,2}\.\d{2}\.\d{4}', term):
        return None, None
    if re.search(r'\b(январ|феврал|март|апрел|май|июн|июл|август|сентябр|октябр|ноябр|декабр)',
                 term, re.IGNORECASE):
        return None, None

    days = None
    m = re.search(r'(\d+)\s*рабоч', term, re.IGNORECASE)
    if m:
        days = math.ceil(int(m.group(1)) * 1.4)   # рабочие → календарные
    else:
        m = re.search(r'(\d+)\s*(?:календарных?\s*дней?|дней?)', term, re.IGNORECASE)
        if not m:
            m = re.search(r'(\d+)', term)
        if m:
            days = int(m.group(1))
    if days is None:
        return None, None
    if days < min_days:
        return days, (f"срок поставки {days} календарных дней — "
                      f"менее {min_days} календарных дней (стоп-фактор #2)")
    return days, None


def find_cyrillic_models(text: str) -> list:
    """Стоп-фактор #12/#16: российские обозначения моделей (ЖРО-1, ДЭ-226)."""
    out = []
    for m in _CYR_MODEL_RE.finditer(text):
        if m.group(1) not in _CYR_MODEL_EXCLUDE and m.group(0) not in out:
            out.append(m.group(0))
    return out


def find_real_gost(response: str) -> Optional[str]:
    """Страховка #13: ГОСТ на сам товар (не на топливо/материалы) → уточнение."""
    crit = re.search(r'-\s*Критичные требования ТЗ\s*-\s*(.*?)(?=-\s|\Z)',
                     response, re.DOTALL | re.IGNORECASE)
    if not crit:
        return None
    hits = re.findall(r'[^\n]*ГОСТ[^\n]*', crit.group(1), re.IGNORECASE)
    real = [g for g in hits if not _MATERIAL_RE.search(g)]
    return real[0].strip() if real else None


def check_volume(response: str, hard_max: int = HARD_MAX_ITEMS) -> Optional[str]:
    """Потолок объёма (D5)."""
    m = re.search(r'Количество позиций:\s*(\d+)', response, re.IGNORECASE)
    if m and int(m.group(1)) > hard_max:
        return (f"объём закупки {m.group(1)} позиций — "
                f"превышает потолок {hard_max} (D5)")
    return None


def pp1875_to_clarify(response: str, china_flag: bool, decision: str) -> bool:
    """ПП-1875 + China=Нет + УЧАСТВУЕМ → меняем на 'требуется уточнение'."""
    return (decision == 'participate' and not china_flag
            and bool(re.search(r'пп.?1875|постановлени\w{0,10}\s*№?\s*1875',
                               response, re.IGNORECASE)))


def check_generic(has_model: bool, brands: set, trusted: bool) -> Optional[str]:
    """Стоп-фактор #18: дженерик-тендер."""
    if not has_model and not brands and not trusted:
        return ("отсутствие конкретных модели/бренда — дженерик-тендер, "
                "оборудование по характеристикам не подбираем (стоп-фактор #18)")
    return None

def _spec_section(response):
    m = re.search(r'---\s*Что нужно поставить\s*---\s*\n(.*?)(?=\n---|\Z)',
                  response, re.DOTALL | re.I)
    return m.group(1).strip() if m else None

def run_post_validations(response, decision, china_flag=False,
                         nac_regime=False, critical_errors=None):
    """Полный набор пост-проверок (паритет с монолитом). Возвращает decision-str."""
    from tendercore.llm import analyze_response_completeness, extract_rejection_reason
    from tendercore.analysis.brand import mine_spec_table, is_brand_trusted
    d = decision
    if d == "not_participate":
        reason = extract_rejection_reason(response)
        if re.search(r'(отсутствует\s+срок|срок\s+не\s+указан|не\s+указан\s+срок)', reason, re.I):
            m = re.search(r'Срок поставки:\s*([^\n]+)', response, re.I)
            if m and m.group(1).strip().lower() not in (
                    'информация отсутствует в документации', 'не удалось определить', ''):
                d = "clarify"
    if d == "not_participate":
        return d
    if validate_delivery_term(response)[1] is not None:
        return "not_participate"
    if re.search(r'казначейское\s+сопровождение', response, re.I):
        return "not_participate"
    if critical_errors:
        return "error"
    if nac_regime and not china_flag and d == "participate":
        d = "clarify"
    if pp1875_to_clarify(response, china_flag, d):
        d = "clarify"
    if d in ("participate", "clarify"):
        spec = _spec_section(response)
        if spec is not None:
            if re.search(r'информация отсутствует в документации|нет структурированной '
                         r'спецификации|спецификация отсутствует', spec, re.I) and '|' not in spec:
                return "not_participate"
            if (re.search(r'\bнасос\w*\b', spec, re.IGNORECASE)
                    and not re.search(r'запчаст|запасн\w*\s+част|комплектующ|ремкомплект',
                                      spec, re.IGNORECASE)):
                return "not_participate"
    if 'Срок поставки' in analyze_response_completeness(response) and d == 'participate':
        return "not_participate"
    if d in ("participate", "clarify"):
        mined = mine_spec_table(response)
        if mined['cyr_models']:
            return "not_participate"
        bm = re.search(r'---\s*Производитель / бренд / страна\s*---\s*\n([^\n\-]+)', response, re.I)
        bt = bm.group(1).strip() if bm else ""
        trusted = is_brand_trusted(bt, response) if bt and 'информация отсутствует' not in bt.lower() else False
        if not mined['has_model'] and not mined['brands'] and not trusted:
            return "not_participate"
    if d == "participate" and find_real_gost(response):
        d = "clarify"
    if check_volume(response):
        return "not_participate"
    return d
