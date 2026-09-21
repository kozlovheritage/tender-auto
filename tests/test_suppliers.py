from tendercore.suppliers.filters import is_junk_email, normalize_email
from tendercore.suppliers.scrape import extract_emails_from_text, is_safe_url, has_mx
from tendercore.suppliers.search import (build_search_queries,
                                         parse_supplier_rows, dedupe_suppliers)


def test_junk_emails_from_log():
    assert is_junk_email("careers@targetcomponents.co.uk")
    assert is_junk_email("hr@company.com")
    assert is_junk_email("ab5c03d7011e42d7b3914c7bd779547b@sentry-new.myshopline.com")
    assert not is_junk_email("sales@uptimeusa.com")
    assert not is_junk_email("info@lightsunion.com")
    assert not is_junk_email("export@luglight.pl")


def test_normalize():
    assert normalize_email(" Sales@Site.COM ,") == "sales@site.com"


def test_extract_emails_decodes_entities():
    html = '<a href="mailto:&#115;&#97;les@site.com">mail</a> and hr@junk.com'
    emails = extract_emails_from_text(html)
    assert "sales@site.com" in emails
    assert all(not e.startswith("hr@") for e in emails)


def test_ssrf_gate():
    assert is_safe_url("https://supplier.com/contacts")
    assert not is_safe_url("http://127.0.0.1/x")
    assert not is_safe_url("http://192.168.1.10/x")
    assert not is_safe_url("ftp://supplier.com/x")
    assert not is_safe_url("https://localhost/x")


def test_has_mx_smoke():
    assert has_mx("gmail.com") in (True, False)   # не падает без сети


def test_queries_skip_non_brand():
    q = build_search_queries("Grundfos", "CR32-02")
    assert q and q[0][1] == "manufacturer"
    assert build_search_queries("III") == []       # кейс из лога 31.08
    assert build_search_queries("zip") == []


def test_parse_and_dedupe():
    text = """
    | ООО Ромашка | Россия | romashka.ru | sales@romashka.ru | Дистрибьютор |
    | ООО Ромашка | Россия | romashka.ru | sales@romashka.ru | Дистрибьютор |
    | GmbH Rose | Германия | rose.de | export@rose.de | OEM |
    """
    rows = dedupe_suppliers(parse_supplier_rows(text))
    assert len(rows) == 2
    assert rows[1]["company"] == "GmbH Rose"