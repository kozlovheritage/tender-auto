import pytest
import requests

from tendercore.eis.client import EisClient, EisNetworkError
from tendercore.eis.guid import (NoticeNotFoundError, norm_reg, resolve_notice)

GUID = "959e9d97-4dc0-4ac1-a2d7-72ed18d39eec"


class Resp:
    def __init__(self, status=200, text=""):
        self.status_code = status
        self.text = text


class FakeSession:
    def __init__(self, effects):
        self.effects = list(effects)
        self.calls = 0

    def get(self, url, **kw):
        self.calls += 1
        e = self.effects.pop(0) if self.effects else Resp(404, "")
        if isinstance(e, Exception):
            raise e
        return e


class FakeClient:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url, retries=2, **kw):
        for key, resp in self.pages.items():
            if key in url:
                return resp
        return Resp(404, "")


# ── client ──

def test_ssl_fallback():
    c = EisClient(backoff_base=0)
    c._s = FakeSession([requests.exceptions.SSLError("boom"), Resp(200, "ok")])
    assert c.get("https://zakupki.gov.ru/").status_code == 200
    assert c._verify is False


def test_retry_503_then_ok():
    c = EisClient(backoff_base=0)
    c._s = FakeSession([Resp(503), Resp(503), Resp(200, "ok")])
    assert c.get("https://zakupki.gov.ru/").status_code == 200
    assert c._s.calls == 3


def test_503_exhausted_raises():
    c = EisClient(backoff_base=0)
    c._s = FakeSession([Resp(503), Resp(503)])
    with pytest.raises(EisNetworkError):
        c.get("https://zakupki.gov.ru/", retries=2)


# ── guid ─

def test_norm_reg_leading_zero():
    assert "02400500000326001376" in norm_reg("2400500000326001376")


def test_resolve_223_guid():
    page = (f'<a href="/223/purchase/x/common-info.html'
            f'?regNumber=32616309551&noticeGuid={GUID}">')
    fc = FakeClient({"223/purchase/public/purchase/info/common-info.html":
                     Resp(200, page)})
    info = resolve_notice(fc, "32616309551")
    assert info.law == "223"
    assert info.guid == GUID


def test_resolve_44_ea20():
    page = f"regNumber=0322100009226000082 guid {GUID}"
    fc = FakeClient({"ea20/common-info.html": Resp(200, page)})
    info = resolve_notice(fc, "0322100009226000082")
    assert info.notice_type == "ea20"
    assert info.guid_optional is True
    assert info.guid == GUID


def test_resolve_not_found():
    with pytest.raises(NoticeNotFoundError):
        resolve_notice(FakeClient({}), "0199999999999999999")