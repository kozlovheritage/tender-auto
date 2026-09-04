"""tendercore.extract.hints — подсказки из текста (НМЦК, срок, позиции, адрес)."""
from __future__ import annotations
import math
import re


def extract_hints_from_text(text: str) -> str:
    """Возвращает строку подсказок для вставки в промпт."""
    hints = []
    # НМЦК
    for pattern in (
        r'(?:НМЦК|НМЦД|начальная\s*(?:максимальная)?\s*цена|цена\s*контракта|стоимость\s*договора)[:\s]*([\d\s]+(?:[.,]\d+)?)\s*(?:руб|₽|RUB)',
        r'(\d{1,3}(?:[\s]\d{3})*(?:[.,]\d{2})?)\s*(?:руб|₽|RUB)',
    ):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            hints.append(f"Подсказка из файлов: возможная НМЦК = "
                         f"{m.group(1).strip().replace(' ', '')} руб.")
            break
    # Количество позиций
    for pattern in (r'(?:количество\s+позиций|всего\s+позиций|перечень\s+товаров)[:\s]*(\d+)',
                    r'(\d+)\s*позици[ейю]'):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            hints.append(f"Подсказка из файлов: количество позиций = {m.group(1)}.")
            break
    # Срок поставки (рабочие → календарные)
    term_patterns = [
        (r'(?:срок\s*поставки|срок\s*доставки|период\s*поставки)[:\s]*(\d+)\s*(рабочих?\s*дней?|календарных?\s*дней?|дней?|месяцев?)', True),
        (r'(?:доставка\s*в\s*течение|в\s*течение\s*)(\d+)\s*(рабочих?\s*дней?|календарных?\s*дней?|дней?)', True),
        (r'(\d+)\s*(рабочих?\s*дней?)\s*с\s*(?:момента|даты)\s*(?:заключения|подписания)', True),
        (r'(?:поставить\s*до\s*|не\s*позднее\s*)(\d{2}\.\d{2}\.\d{4})', False),
    ]
    for pattern, has_unit in term_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            if 'течение' in pattern and re.search(
                    r'оплат|расч[её]т|приемк|подписан',
                    text[max(0, m.start() - 40):m.start()], re.IGNORECASE):
                continue
            val = m.group(1).strip()
            if has_unit and m.lastindex >= 2:
                unit = (m.group(2) or '').strip().lower()
                num = int(re.match(r'\d+', val).group())
                if 'рабоч' in unit:
                    cal = math.ceil(num * 1.4)
                    hints.append(f"Подсказка из файлов: возможный срок поставки: "
                                 f"{cal} (переведено из {num} рабочих дней).")
                else:
                    hints.append(f"Подсказка из файлов: возможный срок поставки: {num}.")
            else:
                hints.append(f"Подсказка из файлов: возможный срок поставки: {val}.")
            break
    # Адрес поставки
    for pattern in (
        r'(?:адрес\s*поставки|место\s*доставки|поставка\s*по\s*адресу)[:\s]*([А-ЯЁ][а-яё\s,\.\d]+(?:г\.|обл\.|край|респ\.)[А-ЯЁа-яё\s,\.\d]+)',
    ):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            hints.append(f"Подсказка из файлов: возможный адрес поставки: "
                         f"{m.group(1).strip()}.")
            break
    return "\n".join(hints) if hints else ""