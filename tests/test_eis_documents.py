"""Offline regressions against installed functions. No monolith/GUI imports."""
from __future__ import annotations

import ast
import contextlib
import datetime
import io
import json
import os
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_STORED

import requests
from test_eis_reliability import (
    OfflineCase, Response, URL, FILE, ROOT, selected_function,
)
from tendercore.eis.client import EisNetworkError, EisStopError
from tendercore.eis.download import download_file, extract_download_url_from_html
from tendercore.eis.protocol import (
    document_links, file_url, wrapper_link, diagnostic_url, diagnostic,
    html_kind, looks_html,
)
from tendercore.eis.runtime import EisRuntime

PDF = b"%PDF-1.7\n" + b"x" * 512 + b"\n%%EOF\n"
WRAPPER = "https://zakupki.gov.ru/44/filestore/public/1.0/download/fz44/file.html?uid=ABC"


def startup(source, namespace):
    tree = ast.parse(source)
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    def assignment(n, name):
        return isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)
    start = next(i for i, n in enumerate(main.body) if assignment(n, "_excel_mtime"))
    end = next(i for i, n in enumerate(main.body) if assignment(n, "results"))
    body = main.body[start:end] + ast.parse(
        "return _resume_set, _retry_pending, _cp_data\n_db_conn = None\n").body
    node = ast.FunctionDef(
        name="restore", args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[],
                                          kw_defaults=[], defaults=[]),
        body=body, decorator_list=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                 "actual_resume_startup", "exec"), namespace)
    return namespace["restore"]()


class LinkTests(unittest.TestCase):
    def test_relative_published_path_not_rewritten_to_guessed_endpoint(self):
        link = "//zakupki.gov.ru/44/filestore/public/1.0/download/fz44/file.html?uid=ABC"
        rows = document_links('<a href="' + link + '">ТЗ.pdf</a>', URL)
        self.assertEqual(rows[0][0], WRAPPER)
        self.assertEqual(file_url("file.html?uid=ABC", FILE), FILE)

    def test_navigation_external_and_partial_uid_are_not_files(self):
        html = (
            '<a href="/epz/main/public/uid.html?uid=ABC">Меню</a>'
            '<a href="https://evil.test/filestore/download/file.html?uid=ABC">Download</a>'
            '<a href="' + FILE + '&amp;uid=OTHER">Повторный параметр</a>'
            '<a href="' + FILE + '">ТЗ.pdf</a>')
        self.assertEqual(len(document_links(html, URL)), 1)

    def test_skip_and_deduplicate_only_documents(self):
        html = '<a href="' + FILE + '">Реестр контрактов</a><a href="' + FILE + '">ТЗ</a><a href="' + FILE + '">ТЗ 2</a>'
        rows = document_links(html, URL, ("реестр контрактов",))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], "ТЗ")

    def test_wrapper_does_not_follow_login_or_unrelated_document(self):
        html = ('<form action="/login"></form><a href="' + WRAPPER.replace("ABC", "OTHER") + '">Download</a>')
        self.assertIsNone(wrapper_link(html, "ABC", FILE))
        self.assertIsNone(extract_download_url_from_html(html, "ABC", FILE))

    def test_wrapper_only_published_same_document_link(self):
        self.assertEqual(wrapper_link('<a href="' + WRAPPER + '">Download</a>', "ABC", FILE), WRAPPER)
        self.assertIsNone(wrapper_link('<meta http-equiv="refresh" content="0; url=https://evil.test/a">', "ABC", FILE))

    def test_header_case_bom_comment_and_xhtml(self):
        self.assertTrue(looks_html(b"\xef\xbb\xbf <!-- note --><html>page", "unknown"))
        self.assertTrue(looks_html(b'<?xml version="1.0"?><html>page', "unknown"))
        self.assertFalse(looks_html(PDF, "text/html"))

    def test_classification_has_no_raw_title_or_body(self):
        for body, expected in (
            ("<html><body>Доступ к сайту временно ограничен</body></html>", "access-check"),
            ('<html><form><input name="captcha"></form></html>', "access-check"),
            ("<title>Service unavailable</title>", "service-unavailable"),
            ('<input type="password">', "login"),
            ("<title>Page not found</title>", "not-found"),
        ):
            self.assertEqual(html_kind(body), expected)

    def test_notice_about_technical_work_is_not_an_outage(self):
        html = ('<html><title>ЕИС: информация о закупке</title>'
                '<body>Выполнение технических работ по договору</body></html>')
        self.assertEqual(html_kind(html), "html")

    def test_diagnostic_redacts_secrets_and_arbitrary_paths(self):
        url = "https://zakupki.gov.ru/secret-path/file.html?uid=SECRET&token=PASSWORD"
        response = Response(headers={"Content-Type": "text/html; private=HEADER_SECRET",
                                     "Set-Cookie": "COOKIE_SECRET", "Content-Length": "513"})
        with contextlib.redirect_stdout(io.StringIO()) as output:
            diagnostic(url, response, size=513, requests=2, attempt=1, category="html")
        text = output.getvalue()
        for value in ("secret-path", "SECRET", "PASSWORD", "COOKIE_SECRET", "HEADER_SECRET", "uid="):
            self.assertNotIn(value, text)
        for value in ("HTTP=200", "bytes=513", "declared=513", "attempt=1", "requests=2", "kind=html"):
            self.assertIn(value, text)
        self.assertEqual(diagnostic_url("https://user:secret@evil.test/a"), "[outside-eis]")


class DocumentTests(OfflineCase):
    def save(self, client, filename="document.pdf"):
        return download_file(FILE, "ABC", filename, str(self.root), client)

    def test_valid_pdf(self):
        client = self.client([Response(body=PDF)])
        self.assertEqual(Path(self.save(client)).read_bytes(), PDF)

    def test_html_never_saved_and_no_fallback_storm(self):
        client = self.client([Response(body=b"<!-- x --><html><body>portal</body></html>")])
        with self.assertRaises(EisNetworkError):
            self.save(client)
        self.assertEqual(len(client._s.calls), 1)
        self.assertFalse(list(self.root.glob("*.part")))
        self.assertFalse(list(self.root.glob("*.pdf")))

    def test_three_html_documents_pause_and_restart_obeys_pause(self):
        client = self.client([Response(body=b"<html>portal</html>")] * 3)
        for _ in range(2):
            with self.assertRaises(EisNetworkError) as error:
                self.save(client)
            self.assertNotIsInstance(error.exception, EisStopError)
        with self.assertRaises(EisStopError):
            self.save(client)
        other = self.client([Response(body=PDF)])
        with self.assertRaises(EisStopError):
            self.save(other)
        self.assertEqual(other._s.calls, [])
        self.assertEqual(len(client._s.calls), 3)

    def test_success_resets_html_streak(self):
        client = self.client([Response(body=b"<html>portal</html>"), Response(body=PDF),
                              Response(body=b"<html>portal</html>"), Response(body=b"<html>portal</html>")])
        with self.assertRaises(EisNetworkError):
            self.save(client)
        self.save(client)
        for _ in range(2):
            with self.assertRaises(EisNetworkError) as error:
                self.save(client)
            self.assertNotIsInstance(error.exception, EisStopError)

    def test_200_service_error_and_body_captcha_stop_without_fallback(self):
        for body in (b"<html><title>Service Unavailable</title></html>",
                     b'<html><input name="captcha"></html>'):
            with self.subTest(body=body):
                client = self.client([Response(body=body)])
                with self.assertRaises(EisStopError):
                    self.save(client)
                self.assertLessEqual(len(client._s.calls), 1)
                self.now += 1000

    def test_wrapper_then_pdf(self):
        wrapper = Response(body=('<html><a href="' + WRAPPER + '">Download</a></html>').encode())
        client = self.client([wrapper, Response(body=PDF)])
        path = self.save(client)
        self.assertEqual(Path(path).read_bytes(), PDF)
        self.assertEqual(len(client._s.calls), 2)
        self.assertTrue(wrapper.closed)

    def test_404_only_tries_same_law(self):
        client = self.client([Response(404), Response(body=PDF)])
        self.save(client)
        self.assertEqual(len(client._s.calls), 2)
        self.assertTrue(all("/223/" not in url for url, _ in client._s.calls))

    def test_redirect_retry_and_wrapper_share_six_requests(self):
        client = self.client([
            Response(302, headers={"Location": WRAPPER}),
            Response(503), Response(503), Response(body=b'<html><a href="' + FILE.encode() + b'">d</a></html>'),
        ], backoff=0)
        with self.assertRaises(EisNetworkError):
            self.save(client)
        self.assertLessEqual(len(client._s.calls), 6)

    def test_403_and_429_never_try_alternative_addresses(self):
        for status in (403, 429):
            client = self.client([Response(status)])
            with self.assertRaises(EisNetworkError):
                self.save(client)
            self.assertEqual(len(client._s.calls), 1)
            self.now += 2000

    def test_length_mismatch_and_broken_pdf_do_not_reach_extraction(self):
        for body, headers in ((PDF, {"Content-Length": "9000"}), (PDF[:-10], {})):
            client = self.client([Response(body=body, headers=headers)])
            with self.assertRaises(EisNetworkError):
                self.save(client)
            self.assertFalse(list(self.root.glob("*.pdf")))
            self.assertFalse(list(self.root.glob("*.part")))

    def test_auto_decompressed_response_length_is_not_false_failure(self):
        client = self.client([Response(body=PDF, headers={"Content-Length": "50", "Content-Encoding": "gzip"})])
        self.assertTrue(Path(self.save(client)).is_file())

    def test_archive_container_and_corrupt_archive(self):
        data = io.BytesIO()
        with ZipFile(data, "w", compression=ZIP_STORED) as archive:
            archive.writestr("word/document.xml", "<doc>" + "content" * 60 + "</doc>")
        client = self.client([Response(body=data.getvalue())])
        self.assertEqual(Path(self.save(client, "specification.docx")).suffix, ".docx")
        broken = bytearray(data.getvalue())
        offset = broken.index(b"content")
        broken[offset] = ord("X")
        client = self.client([Response(body=bytes(broken))])
        with self.assertRaises(EisNetworkError):
            self.save(client)

    def test_xml_error_and_unknown_payload_are_not_documents(self):
        for body, name in ((b"<Error><Code>AccessDenied</Code></Error>", "file.xml"),
                           (b"error " * 200, "file.pdf")):
            client = self.client([Response(body=body)])
            with self.assertRaises(EisNetworkError):
                self.save(client, name)

    def test_stream_error_has_safe_diagnostic_and_cleans_partial(self):
        class Broken(Response):
            def iter_content(self, chunk_size):
                yield PDF[:100]
                raise requests.ConnectionError("sensitive-transport-detail")
        client = self.client([Broken()])
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(EisNetworkError):
                self.save(client)
        self.assertIn("bytes=100", output.getvalue())
        self.assertNotIn("sensitive-transport-detail", output.getvalue())
        self.assertFalse(list(self.root.glob("*.part")))

    def test_transport_error_diagnostics_include_attempts_without_headers(self):
        client = self.client([Response(503)] * 3, backoff=0)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(EisStopError):
                self.save(client)
        self.assertIn("HTTP=503", output.getvalue())
        self.assertIn("attempt=3", output.getvalue())
        state = json.loads((self.runtime.state_dir / "eis_transport.lock").read_bytes()[1:])
        self.assertEqual(state["stopped_at"], self.now)

    def test_real_discovery_function_preserves_published_url_and_closes_response(self):
        response = Response(body=('<a href="' + WRAPPER + '">ТЗ</a>').encode())
        client = self.client([response])
        namespace = dict(_fz_kind=lambda _: "44", _notice_base_path_cache={"123": "/epz/order/notice/ea20"},
                         _notice_type_cache={}, _eis_get=lambda s, u, **kw: s.get(u, **kw),
                         SKIP_KEYWORDS=[], EisNetworkError=EisNetworkError, requests=requests)
        method = selected_function("tender_auto.py", "get_file_links_from_documents_page", namespace)
        self.assertEqual(method("123", "__REG_ONLY__", client)[0][0], WRAPPER)
        self.assertTrue(response.closed)

    def test_empty_real_discovery_is_retryable(self):
        client = self.client([Response(body=b"<html>portal</html>")])
        namespace = dict(_fz_kind=lambda _: "44", _notice_base_path_cache={"123": "/epz/order/notice/ea20"},
                         _notice_type_cache={}, _eis_get=lambda s, u, **kw: s.get(u, **kw),
                         SKIP_KEYWORDS=[], EisNetworkError=EisNetworkError, requests=requests)
        method = selected_function("tender_auto.py", "get_file_links_from_documents_page", namespace)
        with self.assertRaises(EisNetworkError):
            method("123", "__REG_ONLY__", client)

    def test_resume_real_startup_preserves_nine_confirmed_and_23_pending(self):
        data = self.root / "db"
        data.mkdir()
        processed = [str(100 + i) for i in range(9)]
        pending = [str(200 + i) for i in range(23)]
        # A sqlite connection context commits/rolls back, but does not close.
        # Windows cannot remove the temporary database while it is open.
        with contextlib.closing(sqlite3.connect(data / "decisions.db")) as db:
            with db:
                db.execute("CREATE TABLE decisions (tender_number TEXT PRIMARY KEY, decision TEXT)")
                db.executemany("INSERT INTO decisions VALUES (?, 'not_participate')", [(reg,) for reg in processed])
        with self.assertRaises(sqlite3.ProgrammingError):
            db.execute("SELECT 1")
        db_before = (data / "decisions.db").read_bytes()
        excel = self.root / "fixture.xlsx"
        excel.write_bytes(b"fixture")
        checkpoint = dict(excel_file=str(excel), excel_mtime=excel.stat().st_mtime,
                          processed=processed + ["999"], retry_pending=pending, total=326)
        saved = []
        namespace = dict(EXCEL_FILE=str(excel), os=os, DATA_DIR=data, sqlite3=sqlite3,
                         _load_checkpoint=lambda: checkpoint, _save_checkpoint=lambda cp: saved.append(cp),
                         _delete_checkpoint=lambda: self.fail("Must not delete checkpoint"),
                         sys=SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: False)),
                         datetime=datetime, total=326)
        confirmed, retry, cp = startup((ROOT / "tender_auto.py").read_text(encoding="utf-8-sig"), namespace)
        self.assertEqual(confirmed, set(processed))
        self.assertEqual(retry, set(pending))
        self.assertEqual(set(cp["processed"]), set(processed))
        self.assertEqual(cp["retry_pending"], sorted(pending))
        self.assertEqual((data / "decisions.db").read_bytes(), db_before)


if __name__ == "__main__":
    unittest.main()
