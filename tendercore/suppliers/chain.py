"""tendercore.suppliers.chain — чистая логика цепочки поставщиков.

Сеть (LangSearch/Serper/LLM/скрапинг) инжектируется извне; здесь —
очистка предмета, парсинг выдачи, страны, имена, CF-декодер, RFQ-отбор.
"""
from __future__ import annotations
import re
from collections import defaultdict
from urllib.parse import urlparse

from tendercore.log import get_logger

log = get_logger("suppliers")

B2B_PLATFORMS = {
    "alibaba.com", "made-in-china.com", "globalsources.com", "aliexpress.com",
    "1688.com", "dhgate.com", "ec21.com", "tradekey.com", "indiamart.com",
    "tradeindia.com", "europages.com", "kompass.com", "thomasnet.com",
    "go4worldbusiness.com", "exportersindia.com", "ecplaza.net",
}

_JUNK_DOMAINS = {
    "wikipedia.org", "reddit.com", "quora.com", "amazon.com", "ebay.com",
    "youtube.com", "facebook.com", "linkedin.com", "thomasnet.com",
    "indiamart.com", "made-in-china.com", "europages.com", "kompass.com",
    "volza.com", "panjiva.com", "importgenius.com", "zoominfo.com",
}

_JUNK_TITLE_KEYWORDS = [
    "wikipedia", "reddit", "quora", " directory", "catalog",
    "top 10 supplier", "top 5 supplier", "top supplier", "best supplier",
    "leading supplier", "leading manufacturer", "market research",
    "market report", "market size", "list of importers",
]

_TLD_TO_COUNTRY = {
    ".de": "Германия", ".it": "Италия", ".fr": "Франция", ".cn": "Китай",
    ".jp": "Япония", ".kr": "Корея", ".ch": "Швейцария", ".at": "Австрия",
    ".se": "Швеция", ".nl": "Нидерланды", ".be": "Бельгия", ".es": "Испания",
    ".pl": "Польша", ".cz": "Чехия", ".tr": "Турция", ".tw": "Тайвань",
    ".in": "Индия", ".co.uk": "Великобритания", ".uk": "Великобритания",
    ".fi": "Финляндия", ".dk": "Дания",
}

TECH_TERMS_RU_EN = {
    "токарный станок": "lathe machine", "фрезерный станок": "milling machine",
    "сварочный аппарат": "welding machine", "центрифуга": "centrifuge",
    "автоклаве": "autoclave", "микроскоп": "microscope", "насос": "pump",
    "компрессор": "compressor", "редуктор": "gearbox", "трансформатор": "transformer",
    "теплообменник": "heat exchanger", "погрузчик": "forklift", "кран": "crane",
    "оборудование": "equipment", "установка": "unit", "система": "system",
    "запасные части": "spare parts", "запчасти": "spare parts",
    "расходные материалы": "consumables", "реагенты": "reagents",
}

_SUBJECT_NOISE_RE = re.compile(
    r'\b(?:поставка|закупка|приобретение|приобретения|для нужд|нужд|для нужды'
    r'|право заключения договора на|в количестве|количестве|количество'
    r'|объём|объем|услуги по|работы по|поставки)\b'
    r'|\b\d+\s*(?:шт|ед|штук|единиц|компл|комплект|пар|л|кг|м|мл)[а-я.]*\b'
    r'|\b(?:гбуз|гбоу|фгбу|фгуп|фгбоу|муп|мбу|мбоу|оао|зао|ооо|пао|ау|гау|мау)\b',
    re.IGNORECASE,
)

_CF_EMAIL_RE = re.compile(r'data-cfemail="([0-9a-fA-F]+)"')
_BAD_EMAIL_PATTERNS = [
    "noreply", "no-reply", "donotreply", "example.com", "yourdomain",
    "domain.com", "test@", "user@", "admin@", "webmaster@", "postmaster@",
]
_CIS_TLD_RE = re.compile(r'\.(ru|by|kz|ua|uz|am|kg|tj|tm|az|ge|md)$', re.IGNORECASE)
_RFQ_PREFERRED = ("sales", "sale", "export", "commercial", "quotation", "quote",
                  "rfq", "procurement", "purchasing", "orders", "order", "business",
                  "inquiry", "enquiry", "contact", "info", "office")
_RFQ_HIGH = {"sales", "sale", "export", "commercial", "quotation", "quote",
             "rfq", "procurement", "purchasing", "orders", "order"}
_RFQ_REJECTED = ("cybersecurity", "security", "training", "academy", "career",
                 "jobs", "hr", "humanresources", "legal", "privacy", "abuse",
                 "noreply", "no-reply", "webmaster", "postmaster", "support",
                 "service", "technical", "tech")


def clean_subject_for_search(subject: str) -> str:
    """Убирает слова-паразиты и переводит известные термины на английский."""
    text = _SUBJECT_NOISE_RE.sub('', subject)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    words = text.split()
    out, i = [], 0
    while i < len(words):
        if i + 1 < len(words):
            bigram = (words[i] + ' ' + words[i + 1]).lower()
            if bigram in TECH_TERMS_RU_EN:
                if TECH_TERMS_RU_EN[bigram]:
                    out.append(TECH_TERMS_RU_EN[bigram])
                i += 2
                continue
        wl = words[i].lower()
        if wl in TECH_TERMS_RU_EN:
            if TECH_TERMS_RU_EN[wl]:
                out.append(TECH_TERMS_RU_EN[wl])
        else:
            out.append(words[i])
        i += 1
    result = ' '.join(out).strip()
    return result if result else text


def get_host(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def is_b2b_domain(url: str) -> bool:
    host = get_host(url)
    return any(host == p or host.endswith("." + p) for p in B2B_PLATFORMS)


def is_junk_result(title: str, url: str) -> bool:
    host = get_host(url)
    if any(host == j or host.endswith("." + j) for j in _JUNK_DOMAINS):
        return True
    tl = (title or "").lower()
    return any(k in tl for k in _JUNK_TITLE_KEYWORDS)


def extract_company_name(title: str, url: str) -> str:
    name = re.split(r'\s*[|·]\s*', title)[0].strip()
    name = re.sub(
        r'\s*[-–—]\s*(Official\s*(Website|Site|Page|Store)?|Homepage|'
        r'Contact\s*(Us|Info)?|About(\s*Us)?|Home|Support|Products?|'
        r'Manufacturer|Distributor|Supplier|Global|Group|Company|Corp\.?).*$',
        '', name, flags=re.IGNORECASE).strip()
    name = re.sub(
        r'\s+(Official\s*(?:Website|Site|Page|Store|Homepage)?|Homepage|'
        r'Contact\s*(?:Us|Info)?|About\s*(?:Us)?|\.com|\.net|\.org|Ltd\.?|'
        r'Inc\.?|Corp\.?)$', '', name, flags=re.IGNORECASE).strip()
    name = re.sub(r'^(Contact|About|Support|Home)\s*[-–—:]\s*', '',
                  name, flags=re.IGNORECASE).strip()
    if len(name) > 70:
        name = name[:70].rsplit(' ', 1)[0].rstrip(',-') + '…'
    return name or title[:50]


def get_country_from_url(url: str):
    host = get_host(url)
    for tld, country in _TLD_TO_COUNTRY.items():
        if host.endswith(tld):
            return country
    return None


def get_short_description(snippet: str) -> str:
    if not snippet:
        return ""
    first = re.split(r'(?<=[.!?])\s+', snippet.strip())[0]
    first = re.sub(r'^\d{1,2}\s+\w+\s+\d{4}\s*[—\-·]\s*', '', first).strip()
    if len(first) > 150:
        first = first[:150].rsplit(' ', 1)[0] + '…'
    return first


def parse_results_to_suppliers(all_results):
    seen, suppliers = set(), []
    for _section, results in all_results:
        for r in results:
            url = r.get('url', r.get('link', ''))
            title = r.get('title', '')
            if not url or not title:
                continue
            if is_junk_result(title, url) or is_b2b_domain(url):
                continue
            host = get_host(url)
            if not host or host in seen:
                continue
            seen.add(host)
            suppliers.append({
                'name': extract_company_name(title, url),
                'url': url, 'host': host,
                'country': get_country_from_url(url),
                'desc': get_short_description(r.get('snippet', '')),
            })
    return suppliers


def format_suppliers_for_docx(suppliers, valid_emails) -> str:
    lines = []
    if suppliers:
        lines.append("Поставщики (автоматический поиск, требует проверки):")
        lines.append("")
        for i, s in enumerate(suppliers[:12], 1):
            parts = [s['name']]
            if s['country']:
                parts.append(s['country'])
            if s.get('host'):
                parts.append(s['host'])
            lines.append(f"{i}. {' — '.join(parts)}")
    else:
        lines.append("Поставщики: автоматический поиск не дал релевантных результатов.")
        lines.append("(Требуется ручной поиск поставщиков.)")
    if valid_emails:
        lines.append("")
        lines.append("Контакты для запроса:")
        for email in sorted(valid_emails)[:15]:
            lines.append(f"• {email}")
    return "\n".join(lines)


def decode_cfemail(encoded: str):
    try:
        key = int(encoded[:2], 16)
        return ''.join(chr(int(encoded[i:i + 2], 16) ^ key)
                       for i in range(2, len(encoded), 2))
    except Exception:
        return None


def clean_raw_email(raw: str):
    if not raw:
        return None
    cleaned = re.sub(r'^(%[0-9A-Fa-f]{2})+', '', raw)
    if cleaned.lower().startswith('u003e'):
        cleaned = cleaned[5:]
    cleaned = cleaned.lstrip('><').strip()
    if re.match(r'^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$', cleaned):
        return cleaned
    return None


def _is_cis_email(email: str) -> bool:
    try:
        return bool(_CIS_TLD_RE.search(email.split('@', 1)[1]))
    except (IndexError, AttributeError):
        return False


def select_rfq_emails(emails, max_per_domain=2):
    candidates, rejected, seen = [], [], set()
    for raw in emails or []:
        email = str(raw).strip().lower()
        if not email or email in seen or "@" not in email:
            continue
        seen.add(email)
        if any(bad in email for bad in _BAD_EMAIL_PATTERNS) or _is_cis_email(email):
            rejected.append((email, "служебный/неподходящий домен"))
            continue
        local, _, domain = email.partition("@")
        if not domain:
            rejected.append((email, "некорректный email"))
            continue
        if any(part in local for part in _RFQ_REJECTED):
            rejected.append((email, "технический или служебный контакт"))
            continue
        score = 0
        for part in _RFQ_PREFERRED:
            if part in local:
                score = max(score, 100 if part in _RFQ_HIGH else 60)
        if score == 0:
            rejected.append((email, "не найден коммерческий признак"))
            continue
        candidates.append((score, email, domain))
    selected, by_domain = [], defaultdict(list)
    for score, email, domain in candidates:
        by_domain[domain].append((score, email))
    for domain, dom_c in by_domain.items():
        dom_c.sort(key=lambda it: (-it[0], it[1]))
        selected.extend(e for _, e in dom_c[:max_per_domain])
        rejected.extend((e, "дополнительный адрес того же домена")
                        for _, e in dom_c[max_per_domain:])
    return selected, rejected


def inject_emails_into_suppliers_text(suppliers_text: str, emails) -> str:
    if not emails or not suppliers_text:
        return suppliers_text
    lines = suppliers_text.split('\n')
    sup_re = re.compile(r'^Поставщик\s+(\d+)\s+[—–\-]\s+(.+?)(?:\s*\([^)]*\))?\s*$')
    has_email_re = re.compile(r'^E-mail для поставщика\s+(\d+)', re.IGNORECASE)
    sup_map, has_email = {}, set()
    for line in lines:
        m = sup_re.match(line.strip())
        if m:
            sup_map[int(m.group(1))] = m.group(2).strip().lower()
        m2 = has_email_re.match(line.strip())
        if m2:
            has_email.add(int(m2.group(1)))
    if not sup_map:
        return suppliers_text
    assign = {}
    for email in sorted(emails):
        try:
            domain_root = email.split('@')[1].rsplit('.', 1)[0].lower()
        except Exception:
            continue
        for num, name_lower in sorted(sup_map.items()):
            if num in has_email or num in assign:
                continue
            tokens = re.findall(r'[a-z]{4,}', name_lower)
            if domain_root in name_lower or any(t in domain_root for t in tokens):
                assign[num] = email
                break
    if not assign:
        return suppliers_text
    new_lines = [f"E-mail для поставщика {n} — {e}" for n, e in sorted(assign.items())]
    last_idx = -1
    for i, line in enumerate(lines):
        if re.match(r'^E-mail', line.strip(), re.IGNORECASE):
            last_idx = i
    insert_at = last_idx + 1 if last_idx >= 0 else len(lines)
    for j, el in enumerate(new_lines):
        lines.insert(insert_at + j, el)
    return '\n'.join(lines)