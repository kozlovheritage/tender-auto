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


def extract_download_url_from_html(html_text, uid, page_url):
    from tendercore.eis.protocol import wrapper_link
    return wrapper_link(html_text, uid, page_url)


def download_file(url, uid, link_text, save_dir, session, retries=3,
                  referer=None, net_err=None, backoff_base=1.0):
    """One six-request budget for wrappers, redirects, retries and 404 fallback."""
    import contextlib
    import tempfile
    from urllib.parse import urlsplit, parse_qs
    from tendercore.eis.client import EisNetworkError, EisStopError
    from tendercore.eis.protocol import (
        file_url, wrapper_link, html_kind, looks_html, validate_payload,
        diagnostic, document_outcome, mime_type, phase,
    )

    os.makedirs(save_dir, exist_ok=True)
    runtime = getattr(session, "runtime", None)
    if runtime is None:
        raise EisNetworkError("ЕИС: незащищённая сессия загрузки запрещена")
    target = file_url(url, url, uid)
    if not target:
        diagnostic(url, size=0, category="invalid-document-url")
        raise EisNetworkError("ЕИС: ссылка не является прямой ссылкой filestore")
    uid = parse_qs(urlsplit(target).query)["uid"][0]
    # Never cross between 44-ФЗ and 223-ФЗ on a guessed UID.
    path = urlsplit(target).path
    family = "223" if path.startswith("/223/") else ("44" if path.startswith(("/44/", "/44fz/")) else None)
    candidates = [target] + [
        item.format(uid=uid) for item in UID_FALLBACK_TPL
        if family and (item.startswith("https://zakupki.gov.ru/223/")) == (family == "223")
    ]
    candidates = list(dict.fromkeys(candidates))
    attempted = set()
    sent = 0
    headers = {"Accept": "application/octet-stream,application/pdf,application/zip,*/*;q=0.8"}
    if referer:
        headers["Referer"] = referer
    for candidate in candidates:
        if candidate in attempted:
            continue
        target = candidate
        for hop in range(3):
            if target in attempted or sent >= 6:
                raise EisNetworkError("ЕИС: лимит ссылок/запросов документа исчерпан")
            attempted.add(target)
            response = None
            temp = None
            size = 0
            kind = "download-error"
            try:
                phase(f"ЕИС: загрузка документа; запрос {sent + 1} из 6", "info")
                response = session.get(target, stream=True, timeout=(10, 90), headers=headers,
                                       retries=min(retries, 3), max_requests=6 - sent)
                sent += getattr(response, "_eis_requests", 1)
                actual_url = getattr(response, "_eis_url", target)
                status = int(response.status_code)
                if status in (404, 410):
                    diagnostic(actual_url, response, requests=sent,
                               attempt=getattr(response, "_eis_attempt", 1), category="not-found")
                    break
                if status != 200:
                    raise EisNetworkError(f"ЕИС HTTP {status}: документ не получен")
                fd, temp = tempfile.mkstemp(prefix=".eis_", suffix=".part", dir=save_dir)
                with os.fdopen(fd, "wb") as output:
                    for chunk in response.iter_content(65536):
                        if not chunk:
                            continue
                        size += len(chunk)
                        if size > 100 * 1024 * 1024:
                            raise EisNetworkError("ЕИС: файл превысил безопасный лимит 100 МиБ")
                        output.write(chunk)
                with open(temp, "rb") as source:
                    prefix = source.read(8192)
                if looks_html(prefix, mime_type(response)):
                    with open(temp, encoding="utf-8-sig", errors="replace") as source:
                        html = source.read(1024 * 1024)
                    kind = html_kind(html)
                    diagnostic(actual_url, response, size=size, requests=sent,
                               attempt=getattr(response, "_eis_attempt", 1), category=kind)
                    if kind in ("access-check", "login", "service-unavailable"):
                        runtime.stop("ЕИС: вместо файла страница проверки доступа или недоступности", 900, 200)
                    link = wrapper_link(html, uid, actual_url)
                    if link and hop < 2 and link not in attempted:
                        target = link
                        continue
                    document_outcome(runtime, html=True)
                    raise EisNetworkError("ЕИС вернула HTML вместо документа; тендер оставлен на повтор")
                info = getattr(response, "headers", {}) or {}
                length = info.get("Content-Length")
                encoding = str(info.get("Content-Encoding", "")).lower()
                if length and str(length).isdigit() and encoding in ("", "identity") and size != int(length):
                    kind = "length-mismatch"
                    raise EisNetworkError("ЕИС: размер файла не совпал с объявленным; нужен повтор")
                filename = decode_content_disposition(info.get("Content-Disposition")) or link_text or "document.bin"
                filename = safe_filename(filename).strip(" .") or "document.bin"
                kind = "invalid-document"
                detected = validate_payload(temp, filename)
                base, extension = os.path.splitext(filename)
                if extension.lower() in ("", ".bin", ".tmp", ".html") or detected in (".pdf", ".docx", ".xlsx", ".zip"):
                    filename = (base or "document") + detected
                destination = os.path.join(save_dir, filename)
                base, extension = os.path.splitext(destination)
                index = 1
                while os.path.exists(destination):
                    destination = f"{base}_{index}{extension}"
                    index += 1
                os.replace(temp, destination)
                temp = None
                document_outcome(runtime)
                phase(f"Документ получен и проверен: {size} байт", "info")
                return destination
            except EisStopError:
                raise
            except EisNetworkError:
                if net_err is not None:
                    net_err.append(True)
                if response is not None and kind not in ("html", "not-found", "access-check", "login", "service-unavailable"):
                    diagnostic(getattr(response, "_eis_url", target), response, size=size, requests=sent,
                               attempt=getattr(response, "_eis_attempt", 1), category=kind)
                raise
            except (requests.exceptions.RequestException, OSError) as exc:
                if net_err is not None:
                    net_err.append(True)
                diagnostic(getattr(response, "_eis_url", target), response, size=size, requests=sent,
                           attempt=getattr(response, "_eis_attempt", 1), category="broken-stream-or-disk")
                raise EisNetworkError("ЕИС: запись или поток документа прерваны; нужен повтор") from exc
            finally:
                if response is not None:
                    response.close()
                if temp is not None:
                    with contextlib.suppress(FileNotFoundError):
                        os.unlink(temp)
    raise EisNetworkError("ЕИС: документ не найден по опубликованной и допустимым запасным ссылкам")
