"""СРЕЗ 8: теневое подключение tendercore к монолиту.

Модуль подменяет функции монолита обёртками: сначала вызывается СТАРАЯ
функция (её результат возвращается всегда), затем параллельно считается
результат tendercore. Расхождения пишутся в data/shadow_diff.jsonl.
На поведение пайплайна НЕ влияет.
"""
import datetime
import json
from pathlib import Path

_DIFF = Path(__file__).parent / "data" / "shadow_diff.jsonl"


def _log(point, old, new, ctx=""):
    try:
        _DIFF.parent.mkdir(parents=True, exist_ok=True)
        with open(_DIFF, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "point": point,
                "old": str(old)[:300],
                "new": str(new)[:300],
                "ctx": str(ctx)[:200],
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass


def apply(g: dict):
    try:
        from tendercore.analysis import precheck as tc_pre
        from tendercore.analysis import postcheck as tc_post
        from tendercore.rfq import queue as tc_rfq
        from tendercore.report import docx_report as tc_report
    except Exception as e:
        print(f"⚠️ shadow: tendercore недоступен ({e})")
        return

    # 1) предобработка: стоп-факторы по названию
    old_pre = g.get("check_stopfactors_preprocess")
    if callable(old_pre):
        def wrapped_pre(subject, _old=old_pre):
            res_old = _old(subject)
            try:
                res_new = tc_pre.check_title(subject)
                if bool(res_old) != bool(res_new):
                    _log("precheck", res_old, res_new, subject)
            except Exception as e:
                _log("precheck_error", repr(e), "", subject)
            return res_old
        g["check_stopfactors_preprocess"] = wrapped_pre

    # 2) пост-проверка срока поставки
    old_term = g.get("python_validate_term")
    if callable(old_term):
        def wrapped_term(response, *a, _old=old_term, **kw):
            res_old = _old(response, *a, **kw)
            try:
                days, reason = tc_post.validate_delivery_term(response)
                old_flag = (bool(res_old[1])
                            if isinstance(res_old, tuple) and len(res_old) > 1
                            else bool(res_old))
                if old_flag != bool(reason):
                    _log("postcheck_term", str(res_old)[:200],
                         f"days={days} reason={reason}", "")
            except Exception as e:
                _log("postcheck_term_error", repr(e), "", "")
            return res_old
        g["python_validate_term"] = wrapped_term

    # 3) RFQ-очередь: валидация при загрузке
    old_lq = g.get("load_queue")
    if callable(old_lq):
        def wrapped_lq(_old=old_lq):
            q = _old()
            try:
                if isinstance(q, dict):
                    _, invalid = tc_rfq.validate_queue(q)
                    if invalid:
                        _log("rfq_invalid",
                             [e.get("tender_number") for e in invalid], "", "")
            except Exception as e:
                _log("rfq_error", repr(e), "", "")
            return q
        g["load_queue"] = wrapped_lq

    # 4) отчёт: контроль структуры секций ответа
    old_rep = g.get("create_tender_report")
    if callable(old_rep):
        def wrapped_rep(reg_number, deadline_str, response, suppliers_text,
                        output_dir, _old=old_rep):
            path = _old(reg_number, deadline_str, response,
                        suppliers_text, output_dir)
            try:
                secs = tc_report.parse_response_sections(response)
                if "Основная информация" not in secs:
                    _log("report_no_main_section",
                         list(secs.keys())[:8], "", reg_number)
            except Exception as e:
                _log("report_error", repr(e), "", reg_number)
            return path
        g["create_tender_report"] = wrapped_rep

    print("🔌 shadow wiring: tendercore в теневом режиме → data/shadow_diff.jsonl")