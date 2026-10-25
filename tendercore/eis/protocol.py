"""Safe EIS response classification. Never log query values, headers or bodies."""
from __future__ import annotations

from datetime import datetime, timezone
import re
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from tendercore.eis.runtime import EisNetworkError, FileLock, _load, _save


def file_url(href, base, uid=None):
    """Resolve a published filestore URL, never invent an endpoint from a UID."""
    try:
        parsed = urlsplit(urljoin(base, str(href)))
        host = (parsed.hostname or "").lower()
        if (parsed.scheme not in ("https", "http") or parsed.username or parsed.password
                or parsed.port not in (None, 80, 443)
                or not (host == "zakupki.gov.ru" or host.endswith(".zakupki.gov.ru"))):
            return None
        if "/filestore/" not in parsed.path.lower() or "/download/" not in parsed.path.lower():
            return None
        values = parse_qs(parsed.query).get("uid", [])
        if len(values) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", values[0]):
            return None
        if uid and values[0].lower() != str(uid).lower():
            return None
        return urlunsplit(("https", host, parsed.path, parsed.query, ""))
    except ValueError:
        return None


def document_links(html, page_url, skip=()):
    result = {}
    for anchor in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        url = file_url(anchor["href"], page_url)
        if not url:
            continue
        text = anchor.get_text(" ", strip=True)
        if any(word in text.lower() for word in skip):
            continue
        uid = parse_qs(urlsplit(url).query)["uid"][0]
        result.setdefault(uid.lower(), (url, uid, text, page_url))
    return list(result.values())


def wrapper_link(html, uid, page_url):
    """Only explicit same-document links; no login forms or unrelated UID."""
    soup = BeautifulSoup(html, "html.parser")
    choices = [a["href"] for a in soup.find_all("a", href=True)]
    for meta in soup.find_all("meta"):
        if str(meta.get("http-equiv", "")).lower() == "refresh":
            match = re.search(r"url\s*=\s*['\"]?([^'\";]+)", meta.get("content", ""), re.I)
            if match:
                choices.append(match.group(1).strip())
    for href in choices:
        url = file_url(href, page_url, uid)
        if url and url != page_url:
            return url
    return None


def html_kind(html):
    """Return a fixed category, not page text or a potentially sensitive title."""
    soup = BeautifulSoup(str(html)[:1024 * 1024], "html.parser")
    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    text = soup.get_text(" ", strip=True).lower()
    if (re.search(r"access\s*denied|доступ.{0,25}(?:ограничен|запрещ)|captcha|капча|"
                  r"проверка\s+безопасности", title)
            or re.search(r"(?:доступ к (?:сайту|ресурсу)|ваш ip).{0,50}(?:ограничен|заблокирован)", text)
            or soup.select_one('[name="captcha"], [id*="captcha"], .g-recaptcha, .h-captcha')):
        return "access-check"
    unavailable = (r"service\s+unavailable|temporarily\s+unavailable|"
                   r"(?:сервис|сайт|ресурс).{0,25}(?:недоступен|недоступн)|ошибка\s+50[0234]")
    if (re.search(unavailable + r"|технически[ех]\s+работ", title)
            or (len(text) < 3000 and re.search(unavailable, text))):
        return "service-unavailable"
    if re.search(r"страница не найдена|page not found|404 not found", title):
        return "not-found"
    if (soup.select_one('input[type="password"]')
            and (len(text) < 1000 or re.search(r"login|sign in|авторизац|^вход", title))):
        return "login"
    return "html"


def diagnostic_url(url):
    try:
        parsed = urlsplit(str(url))
        host = (parsed.hostname or "").lower()
        if not (host == "zakupki.gov.ru" or host.endswith(".zakupki.gov.ru")):
            return "[outside-eis]"
        # No arbitrary path segment, hostname prefix or query value is published.
        allowed = {"epz", "order", "notice", "44fz", "44", "223", "filestore",
                   "public", "1.0", "download", "priz", "fz44", "fz223",
                   "file.html", "documents.html", "common-info.html", "ea20", "ea15",
                   "notice223", "notice44", "printForm", "view.html"}
        path = "/".join(p if p in allowed else "[hidden]" for p in parsed.path.split("/") if p)
        return "https://zakupki.gov.ru/" + path + ("?[hidden]" if parsed.query else "")
    except ValueError:
        return "[invalid-url]"


def mime_type(response):
    raw = str((getattr(response, "headers", {}) or {}).get("Content-Type", "")).split(";")[0].strip().lower()
    allowed = {"text/html", "application/xhtml+xml", "application/pdf",
               "application/octet-stream", "application/zip", "text/plain",
               "text/xml", "application/xml", "application/msword",
               "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    return raw if raw in allowed else ("other" if raw else "unknown")


def diagnostic(url, response=None, *, attempt=0, requests=0, size=None, category="network-error"):
    headers = (getattr(response, "headers", {}) or {})
    declared = str(headers.get("Content-Length", ""))
    declared = declared if re.fullmatch(r"\d{1,12}", declared) else "unknown"
    status = getattr(response, "status_code", None)
    line = (
        f"ЕИС: диагностика {datetime.now(timezone.utc).isoformat(timespec='seconds')}; "
        f"HTTP={int(status) if status is not None else 'none'}; type={mime_type(response)}; "
        f"bytes={size if size is not None else 'unread'}; declared={declared}; "
        f"attempt={attempt}; requests={requests}; kind={category}; url={diagnostic_url(url)}"
    )
    print(line, flush=True)


def phase(text, kind="warning"):
    try:
        from tendercore.progress import emit
    except ImportError:
        print(text, flush=True)
    else:
        emit(text, kind)


def document_outcome(runtime, html=False, status=200):
    """Persist across tenders and restarts, without treating notice HTML as a file."""
    if runtime is None:
        return
    with runtime.thread_lock, FileLock(runtime.state_dir / "eis_transport.lock") as handle:
        state = _load(handle)
        count = int(state.get("document_html_streak", 0)) + 1 if html else 0
        state.update(document_html_streak=count, last_document_at=runtime.clock())
        _save(handle, state)
    if count >= 3:
        runtime.stop("Три документа подряд вернулись как HTML; запросы приостановлены, нужен повтор позже", 900, status)


def looks_html(prefix, content_type):
    stripped = prefix.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    stripped = re.sub(br"^(?:<\?xml[^>]*>\s*|<!--.*?-->\s*)+", b"", stripped, flags=re.S)
    strong_binary = prefix.startswith((b"%PDF", b"PK", b"\xd0\xcf\x11\xe0", b"\x89PNG", b"\xff\xd8", b"Rar!", b"7z"))
    return bool(re.match(br"<(?:!doctype\s+html|html\b|head\b|body\b|form\b|script\b)", stripped)
                or (content_type in ("text/html", "application/xhtml+xml") and not strong_binary))


def validate_payload(path, filename):
    """Reject error payloads and interrupted binary containers before extraction."""
    import zipfile
    from pathlib import Path
    from xml.etree import ElementTree
    file = Path(path)
    with file.open("rb") as source:
        prefix = source.read(8192)
        source.seek(max(0, file.stat().st_size - 65536))
        tail = source.read()
    if prefix.startswith(b"%PDF"):
        if b"%%EOF" not in tail:
            raise EisNetworkError("ЕИС: PDF оборван (нет завершающей записи); нужен повтор")
        return ".pdf"
    if prefix.startswith(b"PK"):
        try:
            with zipfile.ZipFile(file) as archive:
                # Do not decompress untrusted containers here (zip bombs).
                infos = archive.infolist()
                if not infos or sum(i.file_size for i in infos) > 500 * 1024 * 1024:
                    raise EisNetworkError("ЕИС: архив пуст или превышает лимит распаковки")
                if len(infos) > 2000 or any(i.file_size > 200 * max(1, i.compress_size) for i in infos):
                    raise EisNetworkError("ЕИС: архив превышает безопасный лимит вложений/сжатия")
                if archive.testzip() is not None:
                    raise EisNetworkError("ЕИС: повреждённый архив; нужен повтор")
                names = set(archive.namelist())
                return (".docx" if "word/document.xml" in names else
                        ".xlsx" if "xl/workbook.xml" in names else
                        ".pptx" if "ppt/presentation.xml" in names else ".zip")
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
            raise EisNetworkError("ЕИС: архив оборван; нужен повтор") from exc
    for magic, extension in ((b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", ".doc"),
                             (b"{\\rtf", ".rtf"), (b"\x89PNG", ".png"),
                             (b"\xff\xd8", ".jpg"), (b"II*\0", ".tif"),
                             (b"MM\0*", ".tif"), (b"Rar!", ".rar"), (b"7z\xbc\xaf\x27\x1c", ".7z")):
        if prefix.startswith(magic):
            if file.stat().st_size < 200:
                raise EisNetworkError("ЕИС: неполный двоичный документ")
            return extension
    extension = Path(filename).suffix.lower()
    if extension == ".xml" and file.stat().st_size <= 10 * 1024 * 1024:
        try:
            root = ElementTree.parse(file).getroot()
            if root.tag.split("}")[-1].lower() in ("error", "errors", "html"):
                raise EisNetworkError("ЕИС: XML с ошибкой вместо документа")
            return ".xml"
        except ElementTree.ParseError as exc:
            raise EisNetworkError("ЕИС: повреждённый XML вместо документа") from exc
    if extension in (".txt", ".csv") and file.stat().st_size >= 200:
        if b"\0" not in prefix and not prefix.lstrip().startswith(b"<"):
            return extension
    raise EisNetworkError("ЕИС: неизвестный тип ответа вместо документа; анализ отменён")
