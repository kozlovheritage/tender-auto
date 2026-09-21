import os

from tendercore.eis.download import (
    decode_content_disposition, detect_extension, download_file,
    extract_download_url_from_html, safe_filename,
)


class FakeResp:
    def __init__(self, status=200, content=b"", headers=None):
        self.status_code = status
        self._content = content
        self.headers = headers or {}

    def iter_content(self, n):
        for i in range(0, len(self._content), n):
            yield self._content[i:i + n]


class FakeSession:
    def __init__(self, resp):
        self.resp = resp
        self.verify = True

    def get(self, url, **kw):
        return self.resp


def test_safe_filename():
    assert safe_filename('ТЗ/документ:версия*1?.docx') == 'ТЗ_документ_версия_1_.docx'
    assert len(safe_filename('x' * 200)) == 120


def test_decode_cd_utf8():
    assert decode_content_disposition("filename*=UTF-8''%D0%A2%D0%97.docx") == "ТЗ.docx"


def test_decode_cd_win1251():
    raw = "ТЗ.docx".encode('windows-1251').decode('latin-1')
    assert decode_content_disposition(f'filename="{raw}"') == "ТЗ.docx"


def test_detect_extension(tmp_path):
    p = tmp_path / "f.bin"; p.write_bytes(b"%PDF-1.4 ...")
    assert detect_extension(str(p)) == ".pdf"
    p2 = tmp_path / "d.bin"; p2.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    assert detect_extension(str(p2)) == ".doc"


def test_extract_download_url():
    html = '<a href="/223/filestore/x?uid=ABC">скачать</a>'
    assert extract_download_url_from_html(html, "ABC", "u") == \
        "https://zakupki.gov.ru/223/filestore/x?uid=ABC"


def test_download_file_saves(tmp_path):
    body = b"x" * 300
    resp = FakeResp(200, body, {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": 'filename="test_doc.docx"',
    })
    path = download_file("https://x/file", "uid1", None, str(tmp_path), FakeSession(resp))
    assert path and os.path.exists(path) and os.path.basename(path) == "test_doc.docx"


def test_download_file_min_size(tmp_path):
    resp = FakeResp(200, b"small", {"Content-Type": "application/octet-stream"})
    assert download_file("https://x/file", "uid2", None, str(tmp_path),
                         FakeSession(resp), retries=1) is None