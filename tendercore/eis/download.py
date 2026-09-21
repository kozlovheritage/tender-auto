"""tendercore.eis.download — скачивание документов ЕИС. Headless: только logging."""
from __future__ import annotations
import os, re, time
import requests

from tendercore.log import get_logger

log = get_logger("eis.download")

SKIP_KEYWORDS = [
    "отчет о посещаемости", "report", "attendance", "посещаемость",
    "отчёт о посещаемости", "реестр контрактов", "реестр договоров",
    "register", "маркетинговые исследования",
]

UID_FALLBACK_TPL = [
    "https://zakupki.gov.ru/44fz/filestore/public/1.0/download/priz/file.html?uid={uid}",
    "https://zakupki.gov.ru/44/filestore/public/1.0/download/fz44/file.html?uid={uid}",
    "https://zakupki.gov.ru/223/filestore/public/1.0/download/fz223/file.html?uid={uid}",
]


def safe_filename(name: str, max_len: int = 120) -> str:
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = re.sub(r'\s+', '_', name)
    return name[:max_len] if len(name) > max_len else name


def decode_content_disposition(header_val):
    if not header_val:
        return None
    m = re.search(r"filename\*=UTF-8''([^;]+)", header_val, re.IGNORECASE)
    if m:
        from urllib.parse import unquote
        return unquote(m.group(1))
    m = re.search(r'filename\*=([^;]+)', header_val, re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        try:
            return raw.encode('latin-1').decode('windows-1251')
        except Exception:
            return raw
    m = re.search(r'filename="([^"]+)"', header_val, re.IGNORECASE)
    if m:
        fn = m.group(1)
        try:
            return fn.encode('latin-1').decode('windows-1251')
        except Exception:
            try:
                return fn.encode('latin-1').decode('utf-8')
            except Exception:
                return fn
    m = re.search(r"filename='([^']+)'", header_val, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'filename=([^;]+)', header_val, re.IGNORECASE)
    if m:
        fn = m.group(1).strip()
        if fn.startswith('"') and fn.endswith('"'):
            fn = fn[1:-1]
        elif fn.startswith("'") and fn.endswith("'"):
            fn = fn[1:-1]
        try:
            return fn.encode('latin-1').decode('windows-1251')
        except Exception:
            return fn
    return None


def detect_extension(filepath: str) -> str:
    import zipfile
    try:
        with open(filepath, 'rb') as f:
            header = f.read(8)
        if header[:4] == b'%PDF':
            return '.pdf'
        if header[:2] == b'PK':
            try:
                with zipfile.ZipFile(filepath, 'r') as zf:
                    names = set(zf.namelist())
                if 'word/document.xml' in names:
                    return '.docx'
                if 'xl/workbook.xml' in names:
                    return '.xlsx'
                if 'ppt/presentation.xml' in names:
                    return '.pptx'
                return '.zip'
            except Exception:
                return '.zip'
        if header[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
            return '.doc'
        if header[:5] in (b'{\rtf', b'{\\rtf'):
            return '.rtf'
        if header[:4] == b'\x89PNG':
            return '.png'
        if header[:2] in (b'\xff\xd8',):
            return '.jpg'
    except Exception:
        pass
    return ''


def extract_download_url_from_html(html_text: str, uid: str, page_url: str):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_text, 'html.parser')
    uid_lower = uid.lower()
    for a in soup.find_all('a', href=True):
        href = a['href']
        if uid_lower in href.lower() or any(
                k in href.lower() for k in ('download', 'filestore', '/file?', '/get?')):
            if href.startswith('http'):
                return href
            if href.startswith('/'):
                return 'https://zakupki.gov.ru' + href
    meta = soup.find('meta', attrs={'http-equiv': re.compile(r'refresh', re.I)})
    if meta:
        m = re.search(r'url=([^\s;]+)', meta.get('content', ''), re.I)
        if m:
            red = m.group(1).strip("'\"")
            return red if red.startswith('http') else 'https://zakupki.gov.ru' + red
    form = soup.find('form', action=True)
    if form:
        act = form['action']
        return act if act.startswith('http') else 'https://zakupki.gov.ru' + act
    return None


def download_file(url, uid, link_text, save_dir, session, retries=5,
                  referer=None, net_err=None, backoff_base=1.0):
    """Скачивает файл с retry; при 503 — длинные паузы; HTML-редиректы разруливаются."""
    temp_path = os.path.join(save_dir, f"temp_{uid}.tmp")
    headers = {"Referer": referer} if referer else {}
    for attempt in range(retries):
        try:
            resp = session.get(url, stream=True, timeout=90, headers=headers)
            if resp.status_code == 200:
                with open(temp_path, 'wb') as f:
                    for chunk in resp.iter_content(8192):
                        f.write(chunk)
                if os.path.getsize(temp_path) < 200:
                    os.remove(temp_path)
                    log.warning(f"попытка {attempt+1}: файл <200 байт — пропуск")
                    continue
                ctype = (resp.headers.get('Content-Type', '') or '')
                if 'text/html' in ctype or detect_extension(temp_path) == '.html':
                    html_text = open(temp_path, encoding='utf-8', errors='ignore').read()
                    os.remove(temp_path)
                    real_url = extract_download_url_from_html(html_text, uid, url)
                    target = real_url if real_url and real_url != url else \
                        re.sub(r'/file\.html', '/file', url)
                    if target and target != url:
                        r2 = session.get(target, stream=True, timeout=90, headers=headers)
                        if r2.status_code == 200 and \
                                'text/html' not in (r2.headers.get('Content-Type', '') or ''):
                            with open(temp_path, 'wb') as f:
                                for chunk in r2.iter_content(8192):
                                    f.write(chunk)
                            if os.path.getsize(temp_path) >= 200:
                                resp = r2
                            else:
                                os.remove(temp_path); continue
                        else:
                            continue
                    else:
                        continue
                filename = decode_content_disposition(
                    resp.headers.get('Content-Disposition')) or link_text or (uid + ".bin")
                final_name = safe_filename(filename)
                _, ext = os.path.splitext(final_name)
                if ext.lower() in ('', '.bin', '.tmp', '.html'):
                    det = detect_extension(temp_path)
                    if det and det != '.html':
                        final_name = os.path.splitext(final_name)[0] + det
                final_path = os.path.join(save_dir, final_name)
                base, ext2 = os.path.splitext(final_path)
                c = 1
                while os.path.exists(final_path):
                    final_path = f"{base}_{c}{ext2}"; c += 1
                os.rename(temp_path, final_path)
                return final_path
            elif resp.status_code == 503:
                wait = 45 * (attempt + 1) * backoff_base
                log.warning(f"HTTP 503 — ждём {wait:.0f} с")
                if net_err is not None:
                    net_err.append(True)
                time.sleep(wait)
                continue
            else:
                log.warning(f"HTTP {resp.status_code}")
        except requests.exceptions.SSLError:
            if getattr(session, 'verify', True):
                session.verify = False
                log.warning("SSL-ошибка — отключаю верификацию (VPN/ТСПУ)")
            continue
        except Exception as e:
            log.warning(f"попытка {attempt+1}: {e}")
            if attempt < retries - 1:
                time.sleep(backoff_base * 2 ** attempt)
    if uid:
        for tpl in UID_FALLBACK_TPL:
            try:
                r = session.get(tpl.format(uid=uid), stream=True, timeout=90)
                if r.status_code == 200:
                    with open(temp_path, 'wb') as f:
                        for chunk in r.iter_content(8192):
                            f.write(chunk)
                    if os.path.getsize(temp_path) < 200:
                        os.remove(temp_path); continue
                    det = detect_extension(temp_path)
                    fp = os.path.join(save_dir, safe_filename(uid + (det or ".bin")))
                    os.rename(temp_path, fp)
                    return fp
            except Exception:
                pass
            time.sleep(backoff_base * 2)
    return None