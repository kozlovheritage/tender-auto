from tendercore.eis.client import EisClient, EisNetworkError, EisStopError
from tendercore.eis.runtime import exclusive_eis_run
from tendercore.auctions import auction_eligibility as _ta_auction_eligibility
from tendercore.auctions import auction_search_url as _ta_auction_search_url
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os as _os_cemtorg
_p_act = _os_cemtorg.path.join(_os_cemtorg.path.dirname(_os_cemtorg.path.abspath(__file__)), "config", "active_profile.txt")
CEMTORG_PROFILE = _os_cemtorg.environ.get("PROFILE", "").lower() == "cemtorg" or (_os_cemtorg.path.exists(_p_act) and open(_p_act, encoding="utf-8").read().strip().lower() == "cemtorg")
CEMTORG_TERMS = [
    "пескобетон", "сухие смеси", "штукатурка", "шпатлевка", "плиточный клей",
    "клей монтажный", "цемент", "песок", "щебень", "керамзит", "гипс",
    "грунтовка", "гидроизоляция", "стяжка", "наливной пол", "бумажные мешки",
    "микрокальцит",
]
# --- SSL-фикс (ТСПУ) inline ---
import os as _os_ssl
try:
    import certifi as _certifi_mod
    _os_ssl.environ["SSL_CERT_FILE"] = _certifi_mod.where()
    _os_ssl.environ["REQUESTS_CA_BUNDLE"] = _certifi_mod.where()
except Exception:
    pass
try:
    import urllib3 as _urllib3_ssl
    _urllib3_ssl.disable_warnings()
    import requests as _requests_ssl
    _me = _requests_ssl.Session.merge_environment_settings
    def _me_patch(self, url, proxies, stream, verify, cert):
        st = _me(self, url, proxies, stream, verify, cert)
        st["verify"] = False
        return st
    _requests_ssl.Session.merge_environment_settings = _me_patch
    _rq = _requests_ssl.Session.request
    def _rq_patch(self, *a, **k):
        k["verify"] = False
        return _rq(self, *a, **k)
    _requests_ssl.Session.request = _rq_patch
except Exception:
    pass
# --- конец SSL-фикса ---
try:
    import sys as _sys_lb
    _sys_lb.stdout.reconfigure(line_buffering=True)
    _sys_lb.stderr.reconfigure(line_buffering=True)
except Exception:
    pass
import sys
import os
if getattr(sys, 'frozen', False):
    try:
        import certifi
        os.environ['SSL_CERT_FILE'] = certifi.where()
        os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
        import requests
        requests.defaults.DEFAULT_CA_BUNDLE_PATH = certifi.where()
    except Exception:
        pass
import sys as _sys
for _s in ('stdout', 'stderr'):
    _st = getattr(_sys, _s)
    try:
        if not _st.isatty():
            _st.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import re, sys, time, datetime, argparse
STOP_WORDS_V15 = [
    "выполнение работ", "оказание услуг", "ремонт", "монтаж", "пусконалад",
    "строитель", "отделочн", "обслуживание", "эксплуатация", "аренда", "лизинг",
    "картофель", "мясо", "молоко", "хлеб", "круп", "овощи", "фрукты",
    "консервы", "колбас", "молочн", "сахар", "чай", "кофе", "питание",
    "продукты", "продовольстви", "рацион",
    "бумага", "канцеляр", "ручк", "карандаш", "папк", "блокнот", "скрепк",
    "сковород", "кастрюл", "посуд", "мебель", "стул", "стол", "шкаф",
    "кресло", "диван", "кровать", "матрас", "штор", "ковер", "ковёр",
    "уборка", "клининг", "вывоз мусора", "вывоз отходов", "дезинфекц",
    "охрана", "видеонаблюдение", "сигнализаци", "пожарн",
    "страхов", "аудит", "консалтинг", "обучение", "повышение квалификации",
]
def _v15_title_ok(title):
    tl = (title or "").lower()
    for w in STOP_WORDS_V15:
        if w in tl:
            return False
    return True
STOP_WORDS_V16 = [
    "жилое помещение", "жилых помещений", "квартир", "купля-продажа",
    "недвижим", "переселени", "сирот",
    "лекарств", "медикамент", "медицинск", "медиздели", "вакцин",
    "иммуноглобулин", "реагент", "дефибриллятор", "стент",
    "катетер", "шовн", "рентгенконтраст", "пептидов",
    "бензин", "дизельн", "уголь", "битум", "мазут", "смазочн",
    "гсм", "топлив", "нефтепродукт", "дрова", "керосин",
    "лада", "lada", "легковой автомобиль", "автомобил", "sadko",
    "автобус", "мотоцикл",
    "рыба", "яйцо", "ягод", "полуфабрикат", "вода питьевая",
    "подарк", "сироп",
    "подписк", "программное обеспечение", "субд", "мфу", "принтер",
    "кадастров", "межеван", "стоматолог",
    "благоустройство", "ограждени", "освещени", "площадк",
    "огнетушител",
]
_OKPD2_RE = re.compile(r'ОКПД[2]?\s*\.?\s*([0-9]{2})', re.IGNORECASE)
_OKPD2_BLACK = {
    '01','02','03','05','06','07','08','09','10','11','12','19','20','21',
    '24','41','42','43','45','46','47','49','50','51','52','53','55','56',
    '58','59','60','61','62','63','64','65','66','68','69','70','71','72',
    '73','74','75','77','78','79','80','81','82','84','85','86','87','88',
    '90','91','92','93','94','95','96','97','98','99',
}
def _v16_ok(title):
    tl = (title or "").lower()
    for w in STOP_WORDS_V16:
        if w in tl:
            return False
    m = _OKPD2_RE.search(title or "")
    if m and m.group(1) in _OKPD2_BLACK:
        return False
    return True
STOP_STEMS_V17 = [
    "рыб", "сыр", "овощ", "фрукт", "мяс", "молок", "питани", "продуктов",
    "продовольств", "бакале", "кондитер", "мармелад", "сироп", "ягод",
    "яйц", "капуст", "говяд", "свинин", "курин", "полуфабрикат", "снэк",
    "топлив", "бензин", "дизел", "уголь", "угля", "углей", "битум", "мазут",
    "смазочн", "масл", "гсм", "пропан", "бутан", "природного газа",
    "медицинск", "лекарств", "препарат", "медиздели", "имплант", "стимулятор",
    "рентген", "флюоро", "анестези", "наркозн", "катетер", "инфузион",
    "дефибриллятор", "стоматолог", "зуботехнич", "тест-систем", "антител",
    "возбудител", "иммуно", "вакцин", "хирург", "эндоваскуляр", "каталок", "больнич",
    "услуг", "работ", "аренд", "обслуживани", "эксплуатаци", "сопровождени",
    "консерваци", "транспортиров", "перевозк", "уборк", "клининг", "охран",
    "разработк", "проектиров", "изыскани", "монтаж", "строитель", "реконструкц",
    "благоустройств", "кадастров", "межеван", "страхов", "аудит", "консалтинг", "обучени",
    "автомобил", "легков", "автобус", "автотранспорт", "спецтехник", "спецтранспорт", "мотоцикл",
    "посадк", "саженц", "лесн", "дрова", "пиломатериал", "древесин",
    "памятник", "похорон", "ритуал", "могил",
    "жилого помещения", "жилых помещений", "квартир", "купля-продажа",
    "недвижим", "переселени", "сирот", "земельн",
    "программн", "подписк", "лицензи", "субд", "рекламн", "логотип",
    "костюм", "одежд", "экипировк", "обуви", "перчат", "тканей", "спортивн",
    "бумаг", "канцеляр", "этикетк", "удобрени", "окна", "пвх",
    "водонагревател", "песок", "щебн", "песчано",
]
def _v17_ok(title):
    tl = (title or "").lower()
    return not any(s in tl for s in STOP_STEMS_V17)
from pathlib import Path
import sys as _sysf
if getattr(_sysf, "frozen", False):
    _FROZEN_BASE = Path(_sysf.executable).resolve().parent
    if not (_FROZEN_BASE / "config").exists() and (_FROZEN_BASE.parent / "config").exists():
        _FROZEN_BASE = _FROZEN_BASE.parent
else:
    _FROZEN_BASE = Path(__file__).resolve().parent
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, unquote
import requests
from openpyxl import Workbook
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from html import unescape as _html_unescape
def _shift_dates(url, today, days_back):
    p = urlparse(url)
    q = parse_qs(p.query, keep_blank_values=True)
    dre = re.compile(r'^\d{1,2}\.\d{2}\.\d{4}$')
    new_from = (today - datetime.timedelta(days=days_back)).strftime("%d.%m.%Y")
    new_to = today.strftime("%d.%m.%Y")
    keys = [k for k, v in q.items()
            if v and dre.match(v[0]) and not re.search(r'close|deadline|submission', k, re.I)]
    for k in keys:
        kl = k.lower()
        if 'from' in kl:
            q[k] = [new_from]
        elif 'to' in kl:
            q[k] = [new_to]
    unnamed = [k for k in keys if 'from' not in k.lower() and 'to' not in k.lower()]
    if len(unnamed) == 2:
        vals = {k: datetime.datetime.strptime(q[k][0], "%d.%m.%Y") for k in unnamed}
        lo, hi = sorted(unnamed, key=lambda k: vals[k])
        q[lo], q[hi] = [new_from], [new_to]
    elif len(unnamed) == 1:
        q[unnamed[0]] = [new_from]
    return urlunparse(p._replace(query=urlencode(q, doseq=True)))
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
BASE_SEARCH = "https://zakupki.gov.ru/epz/order/extendedsearch/results.html"
CONFIG_PATH = _FROZEN_BASE / "sampler_config.txt"
OUT_DIR = _FROZEN_BASE
DEFAULTS = {
    "fz44": True,
    "fz223": True,
    "deadline_days_ahead": 16,
    "publish_days_back": 1,
    "auto_shift_dates": True,
    "max_pages": 20,
    "records_per_page": 100,
    "delay_sec": 1.5,
    "base_url": "",
    "cemtorg_pages_per_term": 5,
    "cemtorg_auction_only": True,
}
FZ44_PROC = {
    "ea20": "Электронный аукцион", "ea15": "Электронный аукцион",
    "ea44": "Электронный аукцион", "a44": "Электронный аукцион",
    "zk20": "Запрос котировок в электронной форме", "zk44": "Запрос котировок в электронной форме",
    "ok44": "Открытый конкурс", "ok504": "Открытый конкурс",
    "ep44": "Запрос предложений", "zp44": "Запрос предложений",
}
P223_PHRASES = [
    "Запрос котировок в электронной форме",
    "Запрос предложений в электронной форме",
    "Аукцион в электронной форме",
    "Конкурс в электронной форме",
]
MSP_SUFFIX = ", участниками которого могут быть только субъекты малого и среднего предпринимательства"
LINK_RE = re.compile(r'<a[^>]*href="([^"]*?[?&]regNumber=(\d+)[^"]*)"[^>]*>(.*?)</a>', re.S)
def _clean(t):
    t = re.sub(r'<[^>]+>', ' ', t)
    t = _html_unescape(t)
    return unquote(re.sub(r'\s+', ' ', t)).strip()
def _law_of(href, reg):
    if '/223/' in href or 'fz223' in href:
        return '223'
    if len(reg) == 19 and reg.startswith('0'):
        return '44'
    if len(reg) == 11:
        return '223'
    return '44' if '/epz/order/notice' in href else '223'
def _type_label(law, href, pre):
    if law == '44':
        m = re.search(r'/notice/([a-z0-9]+)(?:/view)?/', href)
        code = m.group(1) if m else ''
        return 'ФЗ 44: ' + FZ44_PROC.get(code, '') if code in FZ44_PROC else 'ФЗ 44'
    for ph in P223_PHRASES:
        if ph in pre:
            suf = MSP_SUFFIX if 'малого и среднего' in pre else ''
            return 'ФЗ 223: ' + ph + suf
    return 'ФЗ 223: Иной способ'
def parse_page(html):
    rows, seen = [], set()
    ms = list(LINK_RE.finditer(html))
    for i, m in enumerate(ms):
        href, reg, title_raw = m.groups()
        if reg in seen:
            continue
        seen.add(reg)
        pre  = _clean(html[max(0, m.start()-2500): m.start()])
        post = _clean(html[m.end(): m.end()+15000])
        law = _law_of(href, reg)
        t = re.search(r'Объект закупки\s*(.*?)\s*(?:Заказчик|Организация,\s*осуществляющая\s*размещение)', post)
        title = t.group(1).strip() if t else _clean(title_raw)
        price = None
        pm = re.search(r'Начальная цена\s*([\d][\d\s.,]*)\s*(?:₽|руб|&#8381;)', post)
        if pm:
            try: price = float(pm.group(1).replace(' ', '').replace(',', '.'))
            except ValueError: price = None
        deadline = None
        dm = re.search(r'[Оо]кончание подачи заявок\s*(\d{1,2}\.\d{2}\.\d{4}(?:\s+\d{1,2}:\d{2})?)', post)
        if dm:
            s = dm.group(1)
            for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
                try:
                    deadline = datetime.datetime.strptime(s[:16], fmt); break
                except ValueError: continue
        cm = re.search(r'(?:Заказчик|Организация,\s*осуществляющая\s*размещение)\s*(.*?)\s*Начальная цена', post)
        customer = cm.group(1).strip() if cm else ''
        url = ('https://zakupki.gov.ru' + unquote(href)) if href.startswith('/') else unquote(href)
        published = None
        pm_pub = re.search(r'Размещено\s*(\d{1,2}\.\d{2}\.\d{4})', post)
        if pm_pub:
            try:
                published = datetime.datetime.strptime(pm_pub.group(1), "%d.%m.%Y")
            except ValueError:
                pass
        rows.append({"url": url, "reg": reg, "title": title, "price": price,
                     "customer": customer, "deadline": deadline, "published": published,
                     "type": _type_label(law, href, pre)})
    return rows
def load_config():
    cfg = dict(DEFAULTS)
    if not CONFIG_PATH.exists():
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write("# ── Спецификация выборки ──\n")
            for k, v in DEFAULTS.items():
                f.write(f"{k}: {'да' if v is True else 'нет' if v is False else v}\n")
        print(f"📄 Создан конфиг: {CONFIG_PATH.name}")
    for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith('#') or ':' not in line: continue
        k, _, v = line.partition(':'); k, v = k.strip(), v.strip()
        if k not in DEFAULTS or not v: continue
        if DEFAULTS[k] is True or DEFAULTS[k] is False:
            cfg[k] = v.lower() in ("1", "да", "true", "on")
        elif isinstance(DEFAULTS[k], int):
            cfg[k] = int(v)
        else:
            cfg[k] = v
    return cfg
def get(session, url):
    return session.get(url, timeout=(10, 30))
def set_page(url, n, per_page):
    p = urlparse(url); q = parse_qs(p.query, keep_blank_values=True)
    q["pageNumber"] = [str(n)]
    q.setdefault("recordsPerPage", [str(per_page)])
    return urlunparse(p._replace(query=urlencode(q, doseq=True)))
def write_xlsx(rows, path):
    wb = Workbook(); ws = wb.active; ws.title = "Отчет"
    ws.append(["Ссылка на источник", "Реестровый номер", "Название", "Начальная цена",
               "Наименование заказчика", "Дата окончания подачи заявок", "Регион", "Тип тендера"])
    for r in rows:
        ws.append([r["url"], r["reg"], r["title"], r["price"], r["customer"],
                   r["deadline"], "", r["type"]])
    wb.save(path)
@exclusive_eis_run(lambda: _FROZEN_BASE / 'data')
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--pages", type=int)
    a = ap.parse_args()
    cfg = load_config()
    session = EisClient(state_dir=_FROZEN_BASE / "data")
    session.runtime.interval = max(3.0, float(cfg.get("delay_sec", 3.0)))
    session.headers.update({"User-Agent": USER_AGENT})
    today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    window_from = today - datetime.timedelta(days=cfg["publish_days_back"])
    print(f"📅 Окно дат: {window_from:%d.%m.%Y} – {today:%d.%m.%Y}")
    if CEMTORG_PROFILE:
        print("Аукционы: " + ("только подтверждённые электронные аукционы 44-ФЗ; "
              "223-ФЗ и неизвестные процедуры не включаются автоматически."
              if cfg["cemtorg_auction_only"] else "фильтр отключён в sampler_config.txt."))
    all_rows, seen = [], set()

    def _accept(r, published_filter):
        if r["reg"] in seen:
            return False
        seen.add(r["reg"])
        if r["price"] is not None and not (cfg.get("price_min", 0) <= r["price"] <= cfg.get("price_max", 999999999999)):
            return False
        if r["deadline"] and r["deadline"] < today:
            return False
        if r["type"].startswith("ФЗ 44") and not cfg["fz44"]:
            return False
        if r["type"].startswith("ФЗ 223") and not cfg["fz223"]:
            return False
        if CEMTORG_PROFILE and cfg["cemtorg_auction_only"] and not _ta_auction_eligibility(r)[0]:
            return False
        if published_filter and r.get("published") and r["published"] < window_from:
            return False
        return True

    def _scan(url, pages, published_filter):
        fresh_all = 0
        for page in range(1, pages + 1):
            print(f"📄 Страница {page}/{pages}")
            try:
                resp = get(session, set_page(url, page, cfg["records_per_page"]))
            except EisNetworkError:
                raise
            except Exception as e:
                raise EisNetworkError("ЕИС: страница выборки не получена") from e
            if resp.status_code != 200:
                raise EisNetworkError(f"ЕИС: страница выборки HTTP {resp.status_code}")
            fresh = 0
            duplicates = 0
            filtered = 0
            procedure_filtered = 0
            page_rows = list(parse_page(resp.text))
            for r in page_rows:
                duplicate = r["reg"] in seen
                if not _accept(r, published_filter):
                    duplicates += int(duplicate)
                    filtered += int(not duplicate)
                    if (not duplicate and CEMTORG_PROFILE and cfg["cemtorg_auction_only"]
                            and not _ta_auction_eligibility(r)[0]):
                        procedure_filtered += 1
                    continue
                all_rows.append(r); fresh += 1
            print(f"  новых строк: {fresh} (всего {len(all_rows)})")
            if CEMTORG_PROFILE:
                print(f"  Строк ЕИС: {len(page_rows)}; повторов: {duplicates}; "
                      f"отсеяно фильтрами: {filtered}, из них способ закупки: {procedure_filtered}.")
            fresh_all += fresh
            if fresh == 0 and not CEMTORG_PROFILE:
                break
        return fresh_all

    _eis_stopped = None
    try:
        if not CEMTORG_PROFILE:
            # ── Витро: прежний общий поток ──
            start_url = a.url or cfg["base_url"] or (BASE_SEARCH + "?" + urlencode({
                "searchString": "", "morphology": "on", "sortBy": "UPDATE_DATE",
                **({"fz44": "on"} if cfg["fz44"] else {}), **({"fz223": "on"} if cfg["fz223"] else {})}))
            max_pages = a.pages or cfg["max_pages"]
            if cfg["auto_shift_dates"] and not a.url:
                start_url = _shift_dates(start_url, today, cfg["publish_days_back"])
            _scan(start_url, max_pages, False)
        else:
            # ── Цемторг: прицельные запросы по группам каталога ──
            pages_per_term = a.pages or cfg["cemtorg_pages_per_term"]
            for term_index, term in enumerate(CEMTORG_TERMS, 1):
                print(f"🔎 Ключевое слово {term_index}/{len(CEMTORG_TERMS)}: "
                      f"«{term}»; страниц: {pages_per_term}")
                url = BASE_SEARCH + "?" + urlencode({
                    "searchString": term, "morphology": "on", "sortBy": "UPDATE_DATE",
                    **({"fz44": "on"} if cfg["fz44"] else {}), **({"fz223": "on"} if cfg["fz223"] else {})})
                if cfg["cemtorg_auction_only"]:
                    url = _ta_auction_search_url(url)
                before = len(all_rows)
                _scan(url, pages_per_term, True)
                print(f"🔎 запрос «{term}»: +{len(all_rows) - before} новых (всего {len(all_rows)})")

    except EisNetworkError as exc:
        _eis_stopped = exc
        print(f"ЕИС: выборка неполная — {exc}")
    finally:
        session.close()

    if not all_rows:
        if _eis_stopped is not None:
            if isinstance(_eis_stopped, EisStopError):
                raise _eis_stopped
            raise EisStopError(str(_eis_stopped))
        print("❌ Ничего не найдено.")
        return
    if not CEMTORG_PROFILE:
        _before_v15 = len(all_rows)
        all_rows = [r for r in all_rows if _v15_title_ok(r.get('title', ''))]
        print('🗑️ v15: отсеяно по стоп-словам:', _before_v15 - len(all_rows))
        _before_v16 = len(all_rows)
        all_rows = [r for r in all_rows if _v16_ok(r.get('title', ''))]
        print('🗑️ v16: отсеяно по расширенным стоп-словам и ОКПД2:', _before_v16 - len(all_rows))
        _before_v17 = len(all_rows)
        all_rows = [r for r in all_rows if _v17_ok(r.get('title', ''))]
        print('🗑️ v17: отсеяно по основам слов:', _before_v17 - len(all_rows))
    else:
        print('ℹ️ Цемторг: каталоговые запросы; фильтр способа закупки применён на каждой странице, без раннего выхода')
    out = OUT_DIR / f"выгрузка_{datetime.datetime.now():%d.%m.%Y}{'_неполная' if _eis_stopped else ''}.xlsx"
    write_xlsx(all_rows, out)
    print(f"{'⚠️ НЕПОЛНАЯ ВЫБОРКА' if _eis_stopped else '✅ ВЫБОРКА'}: {len(all_rows)} тендеров → {out.name}")
    for r in all_rows[:5]:
        dl = r["deadline"].strftime("%d.%m.%Y %H:%M") if r["deadline"] else "—"
        print(f"   {r['reg']} | {r['price']} | {dl} | {r['type']} | {r['title'][:50]}")
    if _eis_stopped is None:
        print("Следующий этап: python tender_auto.py")
    if _eis_stopped is not None:
        if isinstance(_eis_stopped, EisStopError):
            raise _eis_stopped
        raise EisStopError(str(_eis_stopped))
if __name__ == "__main__":
    main()
# TA_CEMTORG_WEEK_V1
