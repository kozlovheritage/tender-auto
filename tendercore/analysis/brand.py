"""tendercore.analysis.brand — B1-B4 майнинг бренда.

Заменяет монолитные функции:
  - extract_brand_from_subject_and_filenames
  - _extract_brand_from_docx
  - KNOWN_BRANDS + brands_extra.txt

Правила:
  B1: бренд из таблицы позиций (высокая надёжность)
  B2: бренд из темы закупки Excel
  B3: бренд из имён файлов (с осторожностью)
  B4: бренд из текста документов (низкая надёжность)

Стоп-лист небрендов: III, IV, Часть_I, zip, rar, 7z, Total, Insert, Iguana,
модели типа SR-2500 (без контекста OEM), расширения файлов.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Optional


# ── Стоп-лист: это НЕ бренды ──
NON_BRAND_STOPWORDS = {
    # Римские/арабские номера частей документации
    "iii", "iv", "i", "ii", "v", "vi", "vii", "viii", "ix", "x",
    "часть", "part", "section", "том", "volume",
    
    # Расширения файлов (часто майнятся из имён)
    "zip", "rar", "7z", "tar", "gz", "doc", "docx", "xls", "xlsx",
    "pdf", "rtf", "odt", "ppt", "pptx",
    
    # Случайные слова из документации
    "total", "insert", "iguana", "call", "primer", "um", "pvs",
    
    # Модели без OEM-контекста (требуют ручной проверки)
    "sr-2500", "sr-2000", "sr-1500",  # снегоочистители (модель, не бренд)
    "eap225", "eap245",  # TP-Link (модель, бренд = TP-Link)
    "d16", "d22",  # алюминий (сплав, не бренд)
}

# ── Доверенные бренды (из brands_extra.txt + KNOWN_BRANDS) ──
TRUSTED_BRANDS = {
    # OEM-производители (высокая уверенность)
    "mitsubishi", "daikin", "panasonic", "toshiba", "fujitsu",
    "siemens", "abb", "schneider", "honeywell", "danfoss",
    "bosch", "philips", "osram", "ge", "emerson",
    "toyota", "honda", "nissan", "mitsuboshi", "gates",
    "tp-link", "d-link", "huawei", "cisco", "h3c",
    "gigabyte", "asus", "msi", "lenovo", "dell", "hp",
    "gree", "midea", "haier", "hisense", "aux",
    "sanyo", "electrolux", "carrier", "trane", "york",
    
    # Специализированные OEM
    "stihl", "husqvarna", "makita", "dewalt", "hilti",
    "caterpillar", "komatsu", "hitachi", "volvo", "jcb",
}

# ── Функции B1-B4 ──

def is_brand_trusted(brand: str) -> bool:
    """True если бренд в списке доверенных (OEM-производитель)."""
    if not brand:
        return False
    brand_lower = brand.lower().strip()
    return brand_lower in TRUSTED_BRANDS


def is_non_brand(brand: str) -> bool:
    """True если это НЕ бренд (стоп-лист: III, zip, Total, модели без OEM)."""
    if not brand:
        return True
    brand_lower = brand.lower().strip()
    
    # Проверка стоп-листа
    if brand_lower in NON_BRAND_STOPWORDS:
        return True
    
    # Проверка римских цифр в начале (Часть_I, Part_II)
    if re.match(r'^(часть|part|section)\s*[_\-]?\s*[ivx0-9]+$', brand_lower):
        return True
    
    return False


def _is_valid_brand_value(val: str) -> bool:
    """True если значение похоже на бренд (не заголовок, не число, не стоп-слово)."""
    if not val or is_non_brand(val):
        return False
    if val.isdigit():
        return False
    if re.search(r'кол-?во|количеств|наименован|цена|примечан|ед\.|штук', val, re.IGNORECASE):
        return False
    if not re.search(r'[A-Za-zА-Яа-яЁё]{2,}', val):
        return False
    return True


def extract_brand_b1_from_table(table_text: str) -> Optional[str]:
    """B1: извлечение бренда из таблицы позиций (высокая надёжность).

    Поддерживает два формата:
      1. Ключ-значение: «Производитель: Mitsubishi Electric»
      2. Таблица с заголовком: колонка «Производитель» → значение из строки данных
    """
    if not table_text:
        return None

    # Формат 1: ключ-значение (разделитель : или -)
    kv_patterns = [
        r'производител[ьия]\s*[:\-]\s*([^|\n]+)',
        r'бренд\s*[:\-]\s*([^|\n]+)',
        r'oem\s*[:\-]\s*([^|\n]+)',
    ]
    for pattern in kv_patterns:
        match = re.search(pattern, table_text, re.IGNORECASE)
        if match:
            brand = match.group(1).strip()
            if _is_valid_brand_value(brand):
                return brand

    # Формат 2: таблица с заголовком (колонка «Производитель»/«Бренд»)
    lines = [ln for ln in table_text.splitlines() if ln.strip()]
    header_idx = col_idx = None
    for i, line in enumerate(lines):
        cells = [c.strip() for c in re.split(r'[|;\t]', line)]
        for j, cell in enumerate(cells):
            if re.search(r'производител|бренд', cell, re.IGNORECASE):
                header_idx, col_idx = i, j
                break
        if header_idx is not None:
            break

    if header_idx is not None and col_idx is not None:
        for line in lines[header_idx + 1:]:
            cells = [c.strip() for c in re.split(r'[|;\t]', line)]
            if col_idx < len(cells):
                val = cells[col_idx].strip()
                if _is_valid_brand_value(val):
                    return val

    return None


def extract_brand_b2_from_subject(subject: str) -> Optional[str]:
    """B2: извлечение бренда из темы закупки Excel."""
    if not subject:
        return None
    
    # Паттерны: «поставка оборудования Daikin», «закупка TP-Link»
    patterns = [
        r'поставка\s+(?:\w+\s+)*([A-Z][A-Za-z0-9\-]+)',
        r'закупка\s+(?:\w+\s+)*([A-Z][A-Za-z0-9\-]+)',
        r'приобретение\s+(?:\w+\s+)*([A-Z][A-Za-z0-9\-]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, subject, re.IGNORECASE)
        if match:
            brand = match.group(1).strip()
            if not is_non_brand(brand):
                return brand
    
    return None


def extract_brand_b3_from_filenames(filenames: list[str]) -> Optional[str]:
    """B3: извлечение бренда из имён файлов (с осторожностью).
    
    Запрещено майнить из:
      - Расширений (.zip, .rar, .docx)
      - Номеров частей (Часть_III, Part_II)
    """
    if not filenames:
        return None
    
    for filename in filenames:
        # Убираем расширение
        name_no_ext = Path(filename).stem
        
        # Пропускаем имена типа «Часть_III», «Part_II»
        if re.match(r'^(часть|part|section)\s*[_\-]?\s*[ivx0-9]+', name_no_ext, re.I):
            continue
        
        # Пропускаем расширения (если имя файла = расширение)
        if name_no_ext.lower() in NON_BRAND_STOPWORDS:
            continue
        
        # Ищем бренд в имени файла (после разделителя _ или в конце)
        match = re.search(r'[_\-]([A-Z][A-Za-z0-9\-]{2,})', name_no_ext)
        if match:
            brand = match.group(1)
            if not is_non_brand(brand):
                return brand
    
    return None


def extract_brand_b4_from_text(text: str) -> Optional[str]:
    """B4: извлечение бренда из текста документов (низкая надёжность).
    
    Используется только если B1-B3 не сработали.
    """
    if not text:
        return None
    
    # Паттерн: «Производитель: XXX» в начале строки
    match = re.search(r'^\s*производител[ьия]\s*[:\-]\s*([A-ZА-ЯЁ][A-ZА-ЯЁa-zа-яё\s\-]+)',
                      text, re.IGNORECASE | re.MULTILINE)
    if match:
        brand = match.group(1).strip()
        if not is_non_brand(brand):
            return brand
    
    return None


def extract_brand(subject: str, filenames: list[str], table_text: str, doc_text: str) -> tuple[Optional[str], str]:
    """Главная функция: извлекает бренд по приоритету B1→B2→B3→B4.
    
    Возвращает (brand, source), где source = 'b1'/'b2'/'b3'/'b4'/None.
    """
    # B1: таблица (высокая надёжность)
    brand = extract_brand_b1_from_table(table_text)
    if brand:
        return brand, "b1"
    
    # B2: тема закупки
    brand = extract_brand_b2_from_subject(subject)
    if brand:
        return brand, "b2"
    
    # B3: имена файлов
    brand = extract_brand_b3_from_filenames(filenames)
    if brand:
        return brand, "b3"
    
    # B4: текст документов (низкая надёжность)
    brand = extract_brand_b4_from_text(doc_text)
    if brand:
        return brand, "b4"
    
    return None, None

# ── паритет: майнинг таблицы «Что нужно поставить» и доверие к бренду ──
import os as _os_b
_NON_BRAND_TOKENS = {
    'usb','hdmi','displayport','vga','dvi','ethernet','wi-fi','wifi','bluetooth',
    'gost','iso','iec','din','ansi','astm','ce','ul','rohs','atex','ip',
    'mm','cm','km','kg','mg','ml','bar','psi','cfm','lpm','rpm','hz','khz',
    'mhz','ghz','kw','mw','kva','hp','btu','dpi','a3','a4','a5','windows',
    'linux','oem','odm','sku','upc','ean','plc','hmi','scada','dcs','cnc',
}

# ── Паритет с монолитом (этап 2A): недостающие токены и блэклист брендов ──
_NON_BRAND_TOKENS |= {
    'a0', 'a1', 'a2', 'a6', 'android', 'b4', 'b5', 'cad', 'cam', 'canopen',
    'devicenet', 'dos', 'erp', 'ethercat', 'http', 'https', 'ios', 'legal',
    'letter', 'macos', 'modbus', 'nfc', 'profibus', 'profinet', 'rfid',
    'rs232', 'rs485', 'unix', 'utf',
}

BRAND_BLACKLIST = {
    'B2B', 'OEM', 'АВ', 'АВР', 'АГРЕГАТ', 'АНАЛОГ', 'АНАЛОГИ', 'АО', 'АПУ',
    'АРТИКУЛ', 'АСУ', 'АЧР', 'БКО', 'БЛОК', 'БУ', 'ВЛ', 'ВРУ', 'ВСН', 'ГОСТ',
    'ГТС', 'ГУП', 'ДГУ', 'ДЕТАЛЬ', 'ДОКУМЕНТАЦИЯ', 'ДОПОЛНИТЕЛЬНЫЙ', 'ДЦ',
    'ЕАЭ', 'ЕАЭС', 'ЕДИНИЦА', 'ЕС', 'ЗАКУПКА', 'ЗАМЕНА', 'ЗАО', 'ЗАПАСНАЯ',
    'ЗАПЧАСТЬ', 'ЗИП', 'ИЗДЕЛИЕ', 'ИП', 'КАТАЛОЖНЫЙ', 'КЗ', 'КИА', 'КИП',
    'КЛ', 'КОМПЛЕКТ', 'КРУ', 'КТП', 'КТПН', 'КУ', 'ЛДСП', 'ЛКМ', 'МАТЕРИАЛ',
    'МДФ', 'МЕХАНИЧЕСКИЙ', 'МОДЕЛЬ', 'МС', 'МТР', 'МУП', 'НАИМЕНОВАНИЕ',
    'НАО', 'НДС', 'НМЦ', 'НМЦД', 'НМЦК', 'НОРМАТИВНЫЙ', 'ОАО', 'ОБОЗНАЧЕНИЕ',
    'ОБОРУДОВАНИЕ', 'ОБРАЗЕЦ', 'ОЕМ', 'ООО', 'ОПИСАНИЕ', 'ОПН', 'ОСНОВНОЙ',
    'ОСТ', 'ПАО', 'ПБ', 'ПВХ', 'ПЛК', 'ПОЗИЦИЯ', 'ПОСТАВКА', 'ПРОДУКТ',
    'ПРОДУКЦИЯ', 'ПТФЭ', 'ПЭТ', 'РАБОЧИЙ', 'РБ', 'РД', 'РЗА', 'РПН', 'РУ',
    'РФ', 'СЕРИЙНЫЙ', 'СЕРТИФИКАТ', 'СИЗ', 'СИСТЕМА', 'СЛЕДУЮЩИЙ', 'СМП',
    'СНГ', 'СНИП', 'СНиП', 'СП', 'СПЕЦИФИКАЦИЯ', 'СТАНДАРТ', 'ТЕХНИЧЕСКИЙ',
    'ТЗ', 'ТИПОВОЙ', 'ТМЦ', 'ТОВАР', 'ТП', 'ТРЕБОВАНИЕ', 'ТСН', 'ТУ', 'ТЭО',
    'ТЭЦ', 'УЗЕЛ', 'УЗО', 'ФАС', 'ФГАУ', 'ФГБОУ', 'ФГБУ', 'ФГКУ', 'ФГУП',
    'ФЗ', 'ЦТП', 'ЧАСТЬ', 'ЧПУ', 'ЭКВИВАЛЕНТ', 'ЭЛЕКТРИЧЕСКИЙ', 'ЭМС',
}

_CYR_MODEL_EXCLUDE = {'ГОСТ', 'ТР', 'СП', 'ТУ', 'ОСТ', 'СНИП', 'НП', 'ФЗ', 'ПП', 'РД', 'ОКПД', 'ОКП', 'КП', 'ТН', 'ВЭД', 'МТР', 'ТМЦ', 'ЗИП', 'ЕАЭС'}
_KNOWN_BRANDS_BASE = {
    'grundfos','ksb','wilo','ebara','skf','fag','nsk','timken','gates','siemens',
    'abb','schneider','mitsubishi','omron','fanuc','danfoss','honeywell','emerson',
    'parker','festo','smc','yokogawa','wika','burkert','vega','daikin','carrier',
    'trane','york','cisco','huawei','dell','hpe','lenovo','samsung','hydac','atos',
}
def _known_brands():
    s = set(_KNOWN_BRANDS_BASE)
    p = _os_b.path.join(_os_b.path.dirname(__file__), "..", "..", "brands_extra.txt")
    p = _os_b.path.normpath(p)
    if _os_b.path.exists(p):
        with open(p, encoding="utf-8") as f:
            s |= {ln.strip().lower() for ln in f if ln.strip()}
    return s

def _md_table(text):
    lines = [l.rstrip() for l in text.split('\n')]
    tl = [l for l in lines if '|' in l]
    if not tl: return None
    rows = []
    for line in tl:
        if re.match(r'^\s*\|[-:\s|]+\|\s*$', line): continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if any(cells): rows.append(cells)
    return rows if len(rows) >= 2 else None

def mine_spec_table(response):
    empty = {'brands': set(), 'has_model': False, 'cyr_models': []}
    m = re.search(r'---\s*Что нужно поставить\s*---\s*\n(.*?)(?=\n---|\Z)',
                  response, re.DOTALL | re.I)
    if not m: return empty
    rows = _md_table(m.group(1))
    if not rows or len(rows) < 2: return empty
    headers = [h.lower() for h in rows[0]]
    name_i = next((i for i,h in enumerate(headers) if 'наимен' in h or 'item' in h), 1)
    part_i = next((i for i,h in enumerate(headers) if 'артикул' in h or 'каталож' in h), -1)
    blank = {'','—','-','–','−'}
    brands, cyr, has_model = set(), [], False
    for row in rows[1:]:
        name = row[name_i] if name_i < len(row) else ''
        part = row[part_i] if 0 <= part_i < len(row) else ''
        if part.strip() not in blank: has_model = True
        for tok in re.findall(r'\b[A-Za-z][A-Za-z0-9\-]{2,}\b', f"{name} {part}"):
            if tok.lower() not in _NON_BRAND_TOKENS and tok.upper() not in BRAND_BLACKLIST:
                brands.add(tok); has_model = True
        for mm in re.finditer(r'\b([А-ЯЁ]{2,6})[-\s]?(\d[\w\-]*)\b', name):
            if mm.group(1) not in _CYR_MODEL_EXCLUDE:
                cyr.append(mm.group(0)); has_model = True
    return {'brands': brands, 'has_model': has_model, 'cyr_models': cyr}

def is_brand_trusted(brand, response="", pre_brand=""):
    if not brand or not brand.strip(): return False
    bl = brand.strip().lower()
    if bl in _NON_BRAND_TOKENS or bl.upper() in BRAND_BLACKLIST or 'информация отсутствует' in bl: return False
    if pre_brand and pre_brand.strip().lower() == bl: return True
    mined = mine_spec_table(response)
    if any(x.lower() == bl or bl in x.lower() for x in mined['brands']): return True
    kb = _known_brands()
    try:
        kb |= {str(x).lower() for x in TRUSTED_BRANDS}
    except NameError:
        pass
    if bl in kb or any(k in bl for k in kb if len(k) >= 4): return True
    return False
