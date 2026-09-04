import re
import sys
from tendercore.analysis.precheck import check_title as tc_check

# Копируем логику труб из монолита (tender_auto.py) для offline-теста
def monolith_check(subject):
    if not subject: return None
    sl = subject.lower()
    PIPE_PATTERNS = [
        r'\bтруб[аы]\s+стальн\w*\s+электросварн',
        r'\bэлектросварн\w+\s+труб',
        r'\bтруб[аы]\s+(?:вгп|водогазопровод)',
        r'\bводогазопровод\w+\s+труб',
        r'\bтруб[аы]\s+(?:профильн|квадратн\s+сеч|прямоугольн\s+сеч)',
        r'\bпрофильн\w+\s+труб',
        r'\bтруб[аы]\s+(?:пнд|пэ\b|полиэтилен)',
        r'\bполиэтиленов\w+\s+труб',  # <-- ТОТ САМЫЙ ПАТТЕРН
    ]
    for pat in PIPE_PATTERNS:
        if re.search(pat, sl):
            return f"трубопроводная продукция ({re.search(pat, sl).group()}) — стоп-фактор #15"
    return None

# Тестовая выборка (можно брать любые строки из выгрузки Excel)
subjects = [
    "Поставка полиэтиленовых труб",
    "Приобретение электросварной трубы",
    "Поставка труб ПНД",
    "Поставка полипропиленовых труб",
    "Поставка стальных труб",
]

print(f"{'Subject':<40} | {'Monolith':<30} | {'TenderCore':<30} | {'Status'}")
print("-" * 115)
for s in subjects:
    m_res = monolith_check(s)
    tc_res = tc_check(s)
    match = "✅ OK" if bool(m_res) == bool(tc_res) else "❌ DESYNC"
    print(f"{s:<40} | {str(m_res):<30} | {str(tc_res):<30} | {match}")