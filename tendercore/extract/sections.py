"""tendercore.extract.sections — умная выборка релевантных разделов для LLM."""
from __future__ import annotations

from tendercore.extract.text import MAX_TEXT_PER_FILE

_SECTION_CONTEXT_CHARS = 1500

_SECTION_KEYWORDS = [
    'срок поставки', 'срок исполнения', 'срок выполнения', 'сроки поставки',
    'сроки исполнения', 'поставить в течение', 'поставка в течение',
    'срок приёмки', 'срок приемки', 'срок оплаты', 'порядок оплаты',
    'адрес поставки', 'адрес доставки', 'место поставки', 'место доставки',
    'казначейское сопровождение',
    'официальный дилер', 'авторизованный дилер', 'аккредитованный дилер',
    'карта партнёра', 'карта партнера', 'partner card', 'дилерское соглашение',
    'страна происхождения', 'российское производство', 'реестр российской',
    'запрет иностранных', 'национальный режим', 'ограничение допуска',
    'спецификация', 'техническое задание', 'перечень товаров', 'ведомость',
    'начальная максимальная цена', 'нмцк', 'нмцд',
    'ндс', 'налог на добавленную стоимость',
    'гарантийный срок', 'гарантия качества',
    'обеспечение заявки', 'обеспечение контракта',
    'производитель', 'изготовитель', 'торговая марка', 'товарный знак',
    'бренд', 'brand', 'made by', 'manufacturer', 'производства',
]


def extract_relevant_sections(full_text: str, first_chars: int = 15000,
                              cap: int = MAX_TEXT_PER_FILE) -> str:
    """Начало документа + релевантные фрагменты по ключевым словам."""
    if len(full_text) <= first_chars:
        return full_text
    parts = [full_text[:first_chars]]
    total = first_chars
    covered = set()
    remainder = full_text[first_chars:]
    offset = first_chars
    rl = remainder.lower()
    for kw in _SECTION_KEYWORDS:
        if total >= cap:
            break
        pos = rl.find(kw.lower())
        if pos == -1:
            continue
        fs = max(0, pos - _SECTION_CONTEXT_CHARS)
        fe = min(len(remainder), pos + len(kw) + _SECTION_CONTEXT_CHARS)
        bucket = (offset + fs) // 500
        if bucket in covered:
            continue
        covered.add(bucket)
        frag = (f"\n[...раздел из позиции ~{(offset + pos) // 1000}к символов...]\n"
                + remainder[fs:fe])
        parts.append(frag)
        total += len(frag)
    return "\n".join(parts)