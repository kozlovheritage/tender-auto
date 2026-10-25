"""Offline regression tests. No credentials, monolith import or live requests."""
from __future__ import annotations

import ast
import argparse
import contextlib
import datetime
from dataclasses import dataclass, field
from enum import Enum
import io
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

import requests
from tendercore.eis.client import EisClient, EisNetworkError, EisStopError, _safe_url
from tendercore.eis.runtime import EisRuntime, FileLock, exclusive_eis_run, retry_after_seconds
from tendercore.eis.download import download_file


class Decision(str, Enum):
    PARTICIPATE = "participate"
    NOT_PARTICIPATE = "not_participate"
    NETWORK_ERROR = "network_error"
    ERROR = "error"
    CLARIFY = "clarify"


@dataclass
class TenderResult:
    reg_number: str
    deadline: str = ""
    subject: str = ""
    nmck: str = ""
    decision: Decision = Decision.ERROR
    missing_fields: list = field(default_factory=list)

ROOT = Path(__file__).resolve().parents[1]
URL = "https://zakupki.gov.ru/epz/order/notice/ea20/common-info.html?regNumber=123"
FILE = "https://zakupki.gov.ru/44fz/filestore/public/1.0/download/priz/file.html?uid=ABC"


class Response:
    def __init__(self, status=200, body=b"%PDF" + b"x" * 512 + b"\n%%EOF", headers=None):
        self.status_code = status
        self.headers = headers or {}
        self.body = body
        self.text = body.decode("utf-8", errors="replace")
        self.content = body
        self.closed = False

    def close(self):
        self.closed = True

    def iter_content(self, size):
        yield self.body


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.headers = {}
        self.calls = []
        self.proxies = {}

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        result = next(self.responses)
        if isinstance(result, BaseException):
            raise result
        return result

    def close(self):
        pass


def selected_function(file, name, namespace):
    tree = ast.parse((ROOT / file).read_text(encoding="utf-8-sig"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    function.decorator_list = []
    exec(compile(ast.Module(body=[function], type_ignores=[]), file, "exec"), namespace)
    return namespace[name]


class OfflineCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1700000000.0
        self.waits = []
        self.runtime = EisRuntime(self.root / "data", interval=3, jitter=0, clock=lambda: self.now, sleep=self.sleep)
        forbidden = patch.object(socket.socket, "connect", side_effect=AssertionError("Live network is forbidden"))
        forbidden.start()
        self.addCleanup(forbidden.stop)
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds

    def client(self, responses, backoff=1):
        client = EisClient(runtime=self.runtime, backoff_base=backoff)
        client._s.close()
        client._s = FakeSession(responses)
        return client


class TransportTests(OfflineCase):
    def test_success(self):
        c = self.client([Response()])
        self.assertEqual(c.get(URL).status_code, 200)
        self.assertFalse(c._s.calls[0][1]["allow_redirects"])

    def test_two_clients_share_pacing(self):
        self.client([Response()]).get(URL)
        other = EisRuntime(self.root / "data", interval=3, jitter=0, clock=lambda: self.now, sleep=self.sleep)
        c = self.client([Response()])
        c.runtime = other
        c.get(URL)
        self.assertGreaterEqual(sum(self.waits), 3)

    def test_429_no_retry_and_cooldown_survives_new_client(self):
        c = self.client([Response(429, headers={"Retry-After": "120"})])
        with self.assertRaises(EisStopError):
            c.get(URL)
        self.assertEqual(len(c._s.calls), 1)
        other = self.client([Response()])
        with self.assertRaises(EisStopError):
            other.get(URL)
        self.assertEqual(other._s.calls, [])
        self.now += 121
        self.assertEqual(other.get(URL).status_code, 200)

    def test_403_page_stops_immediately(self):
        c = self.client([Response(403)])
        with self.assertRaises(EisStopError):
            c.get(URL)
        self.assertEqual(len(c._s.calls), 1)

    def test_403_document_is_local_then_consecutive_block_stops(self):
        c = self.client([Response(403), Response(403)])
        with self.assertRaises(EisNetworkError) as first:
            c.get(FILE)
        self.assertNotIsInstance(first.exception, EisStopError)
        with self.assertRaises(EisStopError):
            c.get(FILE)
        self.assertEqual(len(c._s.calls), 2)

    def test_notice_success_does_not_reset_filestore_blocks(self):
        c = self.client([Response(403), Response(), Response(403)])
        with self.assertRaises(EisNetworkError):
            c.get(FILE)
        c.get(URL)
        with self.assertRaises(EisStopError):
            c.get(FILE)

    def test_document_403_retry_after_is_respected(self):
        c = self.client([Response(403, headers={"Retry-After": "300"})])
        with self.assertRaises(EisStopError) as error:
            c.get(FILE)
        self.assertGreaterEqual(error.exception.retry_at, self.now + 300)

    def test_503_is_bounded_and_has_backoff(self):
        responses = [Response(503) for _ in range(3)]
        c = self.client(responses)
        with self.assertRaises(EisStopError):
            c.get(FILE)
        self.assertEqual(len(c._s.calls), 3)
        self.assertGreaterEqual(sum(self.waits), 135)
        self.assertTrue(all(r.closed for r in responses))

    def test_503_recovers(self):
        c = self.client([Response(503), Response()])
        self.assertEqual(c.get(URL).status_code, 200)
        self.assertEqual(len(c._s.calls), 2)

    def test_long_retry_after_pauses_without_waiting_in_gui(self):
        c = self.client([Response(503, headers={"Retry-After": "3600"})])
        with self.assertRaises(EisStopError) as error:
            c.get(URL)
        self.assertGreaterEqual(error.exception.retry_at, self.now + 3600)
        self.assertEqual(len(c._s.calls), 1)
        self.assertEqual(self.waits, [])

    def test_retry_after_http_date(self):
        stamp = datetime.datetime.fromtimestamp(self.now + 90, datetime.timezone.utc)
        header = stamp.strftime("%a, %d %b %Y %H:%M:%S GMT")
        c = self.client([Response(503, headers={"Retry-After": header}), Response()])
        c.get(URL)
        self.assertGreaterEqual(sum(self.waits), 90)
        self.assertEqual(retry_after_seconds("-1", self.now), 0)
        self.assertIsNone(retry_after_seconds("garbage", self.now))

    def test_timeout_is_not_business_result(self):
        c = self.client([requests.Timeout("test")] * 3)
        with self.assertRaises(EisNetworkError) as error:
            c.get(URL)
        self.assertNotIsInstance(error.exception, EisStopError)
        self.assertEqual(len(c._s.calls), 3)

    def test_redirects_are_paced(self):
        c = self.client([Response(302, headers={"Location": "/next"}), Response()])
        c.get(URL)
        self.assertEqual(len(c._s.calls), 2)
        self.assertGreaterEqual(sum(self.waits), 3)

    def test_external_redirect_is_rejected(self):
        c = self.client([Response(302, headers={"Location": "http://127.0.0.1/secret"})])
        with self.assertRaises(EisNetworkError):
            c.get(URL)
        self.assertEqual(len(c._s.calls), 1)

    def test_redirect_loop_is_bounded(self):
        c = self.client([Response(302, headers={"Location": "/loop"}) for _ in range(8)])
        with self.assertRaises(EisNetworkError):
            c.get(URL)
        self.assertEqual(len(c._s.calls), 5)

    def test_html_challenge_pauses(self):
        c = self.client([Response(body=b"<html><title>Access Denied</title></html>")])
        with self.assertRaises(EisStopError):
            c.get(URL)

    def test_regular_not_found_is_not_a_block(self):
        c = self.client([Response(404), Response()])
        self.assertEqual(c.get(URL).status_code, 404)
        self.assertEqual(c.get(URL).status_code, 200)

    def test_host_validation(self):
        for url in ("https://zakupki.gov.ru.evil.test/a", "https://zakupki.gov.ru@127.0.0.1/a", "file:///etc/passwd"):
            with self.assertRaises(EisNetworkError):
                _safe_url(url)

    def test_corrupt_state_does_not_bypass_limiter(self):
        self.runtime.state_dir.mkdir()
        (self.runtime.state_dir / "eis_transport.lock").write_bytes(b"\0broken")
        c = self.client([Response()])
        with self.assertRaises(EisNetworkError):
            c.get(URL)
        self.assertEqual(c._s.calls, [])

    def test_run_lock_released_after_error(self):
        from tendercore.eis import runtime as module
        with patch.object(module, "get_runtime", return_value=self.runtime):
            @exclusive_eis_run(lambda: self.runtime.state_dir)
            def run():
                raise EisStopError("test", self.now + 3)
            with self.assertRaises(SystemExit) as error:
                run()
            self.assertEqual(error.exception.code, 77)
            with FileLock(self.runtime.state_dir / "eis_run.lock", blocking=False):
                pass
        metrics = json.loads((self.runtime.state_dir / "eis_last_run.json").read_text())
        self.assertEqual(metrics["outcome"], "paused")

    def test_second_run_rejected(self):
        from tendercore.eis import runtime as module
        with FileLock(self.runtime.state_dir / "eis_run.lock", blocking=False):
            with patch.object(module, "get_runtime", return_value=self.runtime):
                @exclusive_eis_run(lambda: self.runtime.state_dir)
                def run():
                    self.fail("should not run")
                with self.assertRaises(SystemExit) as error:
                    run()
                self.assertEqual(error.exception.code, 75)


class DownloadTests(OfflineCase):
    def test_binary_saved_without_temp_files(self):
        c = self.client([Response()])
        path = download_file(FILE, "ABC", "document.pdf", str(self.root), c)
        self.assertTrue(Path(path).read_bytes().startswith(b"%PDF"))
        self.assertFalse(list(self.root.glob("*.part")))

    def test_download_429_does_not_try_fallback_urls(self):
        c = self.client([Response(429)])
        with self.assertRaises(EisStopError):
            download_file(FILE, "ABC", "document.pdf", str(self.root), c)
        self.assertEqual(len(c._s.calls), 1)
        self.assertFalse(list(self.root.glob("*.part")))

    def test_download_503_does_not_multiply_retries(self):
        c = self.client([Response(503)] * 3, backoff=0)
        with self.assertRaises(EisStopError):
            download_file(FILE, "ABC", "document.pdf", str(self.root), c)
        self.assertEqual(len(c._s.calls), 3)

    def test_404_can_use_uid_fallback(self):
        c = self.client([Response(404), Response()])
        path = download_file(FILE, "ABC", "document.pdf", str(self.root), c)
        self.assertTrue(Path(path).is_file())
        self.assertEqual(len(c._s.calls), 2)

    def test_html_never_saved_as_document(self):
        c = self.client([Response(body=b"<html>" + b"x" * 512 + b"</html>")])
        with self.assertRaises(EisNetworkError):
            download_file(FILE, "ABC", "document.pdf", str(self.root), c)
        self.assertFalse(list(self.root.glob("*.pdf")))
        self.assertFalse(list(self.root.glob("*.part")))
        self.assertEqual(len(c._s.calls), 1)

    def test_challenge_stream_pauses(self):
        c = self.client([Response(body=b"<html><title>Access Denied</title></html>")])
        with self.assertRaises(EisStopError):
            download_file(FILE, "ABC", "document.pdf", str(self.root), c)
        self.assertFalse(list(self.root.glob("*.part")))

    def test_stream_disconnect_cleans_partial_file(self):
        class Broken(Response):
            def iter_content(self, size):
                yield b"%PDF" + b"x" * 300
                raise requests.ConnectionError("broken")
        response = Broken()
        c = self.client([response])
        with self.assertRaises(EisNetworkError):
            download_file(FILE, "ABC", "document.pdf", str(self.root), c)
        self.assertTrue(response.closed)
        self.assertFalse(list(self.root.glob("*.part")))
        self.assertEqual(len(c._s.calls), 1)

    def test_short_file_is_incomplete(self):
        c = self.client([Response(body=b"short")])
        with self.assertRaises(EisNetworkError):
            download_file(FILE, "ABC", "document.pdf", str(self.root), c)
        self.assertFalse(list(self.root.glob("*.part")))

    def test_full_document_set_required(self):
        namespace = {
            "os": os, "re": re, "EisNetworkError": EisNetworkError, "MAX_FILES_PER_TENDER": 20,
            "fetch_notice_guid": lambda *a, **k: "__REG_ONLY__",
            "get_file_links_from_documents_page": lambda *a: [(FILE, "A", "a", URL), (FILE, "B", "b", URL)],
        }
        doc = self.root / "a.pdf"
        doc.write_bytes(b"%PDF" + b"x" * 500)
        calls = iter([str(doc), None])
        namespace["download_file"] = lambda *a, **k: next(calls)
        method = selected_function("tender_auto.py", "download_tender_documents", namespace)
        paths, _, _, incomplete = method("123", {}, None, str(self.root))
        self.assertEqual(paths, [str(doc)])
        self.assertTrue(incomplete)

    def test_missing_document_list_is_retryable(self):
        namespace = {
            "os": os, "re": re, "EisNetworkError": EisNetworkError, "MAX_FILES_PER_TENDER": 20,
            "fetch_notice_guid": lambda *a, **k: "__REG_ONLY__",
            "get_file_links_from_documents_page": lambda *a: [],
        }
        method = selected_function("tender_auto.py", "download_tender_documents", namespace)
        self.assertTrue(method("123", {}, None, str(self.root))[3])

    def test_document_cap_is_not_silently_treated_as_complete(self):
        namespace = {
            "os": os, "re": re, "EisNetworkError": EisNetworkError, "MAX_FILES_PER_TENDER": 1,
            "fetch_notice_guid": lambda *a, **k: "__REG_ONLY__",
            "get_file_links_from_documents_page": lambda *a: [(FILE, "A", "a", URL), (FILE, "B", "b", URL)],
        }
        document = self.root / "a.pdf"
        document.write_bytes(b"%PDF" + b"x" * 500)
        namespace["download_file"] = lambda *a, **k: str(document)
        method = selected_function("tender_auto.py", "download_tender_documents", namespace)
        self.assertTrue(method("123", {}, None, str(self.root))[3])

    def test_pipeline_must_not_analyze_partial_documents(self):
        namespace = {
            "Deps": object, "TenderResult": TenderResult, "Decision": Decision,
            "EisNetworkError": EisNetworkError, "EisStopError": EisStopError,
            "parse_deadline": lambda value: "01.12.2026", "_fmt_nmck": str,
            "precheck": SimpleNamespace(check_title=lambda value: None),
            "extract_texts_from_paths": lambda *a, **k: self.fail("Must not extract or call LLM"),
        }
        method = selected_function("tendercore/pipeline.py", "process_tender", namespace)
        result = method({"Реестровый номер": "123", "Название": "цемент"}, SimpleNamespace(download=lambda *a: (["partial.pdf"], False, False, True)))
        self.assertEqual(result.decision, Decision.NETWORK_ERROR)


class WorkflowTests(OfflineCase):
    def main_loop(self, decisions, old=None):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        self.addCleanup(connection.close)
        connection.execute("CREATE TABLE decisions (tender_number TEXT PRIMARY KEY, processed_date TEXT, decision TEXT, subject TEXT, nmck TEXT, china_flag INT, suppliers_found INT)")
        if old:
            connection.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?)", ("123", "old", old, "old subject", "0", 0, 0))
            connection.commit()
        rows = [("123", {"Реестровый номер": "123", "Название": "цемент", "Дата окончания подачи заявок": "01.12.2026"})]
        if len(decisions) > 1:
            rows.append(("456", {"Реестровый номер": "456", "Название": "песок", "Дата окончания подачи заявок": "01.12.2026"}))
        sequence = iter(decisions)
        def process(row, *args):
            value = next(sequence)
            if isinstance(value, BaseException):
                raise value
            return (row["Реестровый номер"], "01.12.2026", None, value, False, [], "цемент", "0", False)
        checkpoints = []
        context = {
            "_ta_progress": lambda *args, **kwargs: None,  # TA_FRIENDLY_PROGRESS
            "EisStopError": EisStopError, "_db_conn": SimpleNamespace(execute=connection.execute, commit=connection.commit, close=lambda: None),
            "df": SimpleNamespace(iterrows=lambda: iter(rows)), "tqdm": lambda value, **kwargs: value,
            "total": len(rows), "_resume_set": set(), "force_all": bool(old), "force_set": set(),
            "incomplete_tenders_global": [], "rfq_queue": [], "sender_config": {},
            "results": [], "network_error_list": [], "new_history_records": [], "skipped_count": 0,
            "_cp_processed": [], "_retry_pending": set(), "_cp_data": {"processed": []},
            "_today": "today", "_run_completed": False, "_eis_stopped": None,
            "process_tender": process, "_carry_orphan": lambda *args: None,
            "_save_checkpoint": lambda value: checkpoints.append(json.loads(json.dumps(value))),
            "parse_date_from_excel": lambda value: value,
        }
        tree = ast.parse((ROOT / "tender_auto.py").read_text(encoding="utf-8-sig"))
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        loop = next(n for n in main.body if isinstance(n, ast.Try) and any(isinstance(c, ast.For) for c in n.body))
        exec(compile(ast.Module(body=[loop], type_ignores=[]), "production_loop", "exec"), context)
        return context, checkpoints, connection

    def test_network_error_not_in_db_or_processed_checkpoint(self):
        result, checkpoints, db = self.main_loop(["network_error"])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0], 0)
        self.assertEqual(checkpoints[-1]["processed"], [])
        self.assertEqual(checkpoints[-1]["retry_pending"], ["123"])
        self.assertFalse(result["_run_completed"])

    def test_previous_decision_not_deleted_on_failed_forced_refresh(self):
        _, checkpoints, db = self.main_loop(["network_error"], old="participate")
        self.assertEqual(db.execute("SELECT decision FROM decisions").fetchone()[0], "participate")
        self.assertEqual(checkpoints[-1]["retry_pending"], ["123"])

    def test_block_after_success_saves_only_completed_tender(self):
        result, checkpoints, db = self.main_loop(["participate", EisStopError("test", self.now + 900, 429)])
        self.assertEqual(checkpoints[-1]["processed"], ["123"])
        self.assertEqual(checkpoints[-1]["retry_pending"], ["456"])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0], 1)
        self.assertEqual(result["results"][-1][3], "network_error")
        self.assertFalse(result["_run_completed"])

    def test_completed_success_is_committed(self):
        result, checkpoints, db = self.main_loop(["participate"])
        self.assertTrue(result["_run_completed"])
        self.assertEqual(checkpoints[-1]["processed"], ["123"])
        self.assertEqual(checkpoints[-1]["retry_pending"], [])
        self.assertEqual(db.execute("SELECT decision FROM decisions").fetchone()[0], "participate")

    def test_legacy_checkpoint_skips_only_db_confirmed_results(self):
        _, _, db = self.main_loop(["participate"])
        namespace = {"_cp": {"processed": ["123", "456", "789"]}, "_retry_pending": {"789"}, "_db_conn": db, "_resume_conn": db}  # TA_RESUME_TEST_SCOPE
        tree = ast.parse((ROOT / "tender_auto.py").read_text(encoding="utf-8-sig"))
        statement = next(node for node in ast.walk(tree) if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_resume_set" for t in node.targets) and isinstance(node.value, ast.SetComp))
        exec(compile(ast.Module(body=[statement], type_ignores=[]), "resume_filter", "exec"), namespace)
        self.assertEqual(namespace["_resume_set"], {"123"})

    def test_all_production_eis_sessions_use_guarded_client(self):
        for file, names in (("tender_auto.py", {"process_tender"}), ("sampler.py", {"main"}), ("tendercore/pipeline.py", {"default_deps"})):
            tree = ast.parse((ROOT / file).read_text(encoding="utf-8-sig"))
            for function in tree.body:
                if isinstance(function, ast.FunctionDef) and function.name in names:
                    calls = [n for n in ast.walk(function) if isinstance(n, ast.Call)]
                    self.assertTrue(any(isinstance(n.func, ast.Name) and n.func.id == "EisClient" for n in calls), file)
                    self.assertFalse(any(isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == "requests" and n.func.attr == "Session" for n in calls), file)

    def sampler(self, responses):
        saved = []
        sequence = iter(responses)
        def get(*args):
            response = next(sequence)
            if isinstance(response, BaseException):
                raise response
            return response
        session = SimpleNamespace(headers={}, close=lambda: None, runtime=SimpleNamespace(interval=3))
        future = datetime.datetime.now() + datetime.timedelta(days=30)
        namespace = {
            "argparse": argparse, "datetime": datetime, "urlencode": urlencode,
            "EisClient": lambda **kwargs: session, "EisNetworkError": EisNetworkError, "EisStopError": EisStopError,
            "USER_AGENT": "test", "_FROZEN_BASE": self.root, "OUT_DIR": self.root,
            "load_config": lambda: {"cemtorg_auction_only": False, "publish_days_back": 30, "fz44": True, "fz223": True, "cemtorg_pages_per_term": 3, "records_per_page": 10, "delay_sec": 3},
            "CEMTORG_PROFILE": True, "CEMTORG_TERMS": ["цемент"], "BASE_SEARCH": URL,
            "get": get, "set_page": lambda url, *args: url,
            "parse_page": lambda text: [{"reg": "123", "title": "цемент", "price": 100, "deadline": future, "type": "ФЗ 44", "published": future}],
            "write_xlsx": lambda rows, path: saved.append((list(rows), Path(path))),
        }
        main = selected_function("sampler.py", "main", namespace)
        with patch("sys.argv", ["sampler.py"]):
            with self.assertRaises(EisStopError):
                main()
        return saved

    def test_sampler_saves_partial_rows_under_explicit_partial_filename(self):
        saved = self.sampler([Response(), EisStopError("test", self.now + 900, 429)])
        self.assertEqual(len(saved), 1)
        self.assertEqual(len(saved[0][0]), 1)
        self.assertTrue(saved[0][1].name.endswith("_неполная.xlsx"))

    def test_sampler_non_200_cannot_look_like_completed_search(self):
        self.assertEqual(self.sampler([Response(404)]), [])


if __name__ == "__main__":
    unittest.main()
