"""tendercore.pipeline — оркестратор (новый движок).

Компонует протестированные модули tendercore; сетевой/LLM-клей инжектируется
через Deps (default_deps() — lazy-импорт из монолита для прода).
Headless: только logging, возвращает TenderResult.
"""
from __future__ import annotations
import datetime
import os
import re

from tendercore.log import get_logger
from tendercore.models import Decision, TenderResult
from tendercore.analysis import precheck, postcheck
from tendercore.analysis.prompt import build_prompt
from tendercore.llm import (classify_response, clean_response_preamble,
                            extract_china_flag, postprocess_response)
from tendercore.extract import hints as ex_hints
from tendercore.extract.pipeline import extract_texts_from_paths

log = get_logger("pipeline")


class Deps:
    """Инжектируемый клей: download / llm / search / report / brand_scan."""
    def __init__(self, download, llm, search, report, brand_scan=None):
        self.download = download
        self.llm = llm
        self.search = search
        self.report = report
        self.brand_scan = brand_scan


def default_deps():
    import tender_auto as m
    import requests

    def download(reg, row):
        session = requests.Session()
        session.verify = False
        session.headers.update({"User-Agent": m.USER_AGENT})
        tender_dir = os.path.join("temp_files", reg)
        os.makedirs(tender_dir, exist_ok=True)
        return m.download_tender_documents(reg, row, session, tender_dir)

    return Deps(
        download=download,
        llm=m.call_deepseek,
        search=lambda s, b, c: m.search_and_format_suppliers(s, b, china_available=c),
        report=lambda r, d, resp, sup: m.create_tender_report(
            r, d, resp, sup, os.path.join(m.OUTPUT_BASE, "temp_reports")),
    )


def parse_deadline(value) -> str:
    if value is None:
        return ""
    try:
        import pandas as pd
        if pd.isna(value):
            return ""
    except Exception:
        pass
    if isinstance(value, datetime.datetime):
        return value.strftime("%d.%m.%Y")
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(s[:10], fmt).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return ""


def _fmt_nmck(value) -> str:
    try:
        v = float(str(value).replace("\xa0", "").replace(" ", "").replace(",", "."))
        return f"{int(v):,}".replace(",", " ")
    except Exception:
        return str(value).strip() if value else "—"


def build_reliable_hints(row) -> str:
    out = "--- ДОСТОВЕРНЫЕ ДАННЫЕ ИЗ ВЫГРУЗКИ ---\n"
    nmck = row.get("Начальная цена")
    if nmck:
        out += f"НМЦК: {nmck} руб.\n"
    cust = row.get("Наименование заказа") or row.get("Заказчик")
    if cust:
        out += f"Заказчик: {cust}\n"
    subj = row.get("Название")
    if subj:
        out += f"Предмет закупки: {subj}\n"
    if row.get("Регион"):
        out += f"Регион поставки: {row['Регион']}\n"
    return out + "--- КОНЕЦ ДОСТОВЕРНЫХ ДАННЫХ ---\n"


def apply_post_checks(response, decision, china_flag=False, nac_regime=False,
                      critical_errors=None):
    d = decision.value if isinstance(decision, Decision) else decision
    return Decision(postcheck.run_post_validations(
        response, d, china_flag=china_flag, nac_regime=nac_regime,
        critical_errors=critical_errors))


def process_tender(row, deps: Deps) -> TenderResult:
    reg = str(row.get("Реестровый номер", "")).strip()
    deadline = parse_deadline(row.get("Дата окончания подачи заявок"))
    subject = str(row.get("Название", "") or "").strip() or "—"
    base = dict(reg_number=reg, deadline=deadline, subject=subject,
                nmck=_fmt_nmck(row.get("Начальная цена")))

    if not deadline:
        return TenderResult(decision=Decision.ERROR,
                            missing_fields=["дата подачи заявок"], **base)

    if subject != "—" and precheck.check_title(subject):
        log.info(f"⛔ precheck: {precheck.check_title(subject)}")
        return TenderResult(decision=Decision.NOT_PARTICIPATE, **base)

    paths, partner_card, nac_regime, network_failed = deps.download(reg, row)
    if partner_card:
        return TenderResult(decision=Decision.NOT_PARTICIPATE, **base)

    doc_text, critical, _ok, _err, _hints = extract_texts_from_paths(
        paths, brand_scanner=deps.brand_scan)
    if critical:
        return TenderResult(decision=Decision.ERROR, **base)
    if not doc_text.strip():
        d = Decision.NETWORK_ERROR if network_failed else Decision.NOT_PARTICIPATE
        return TenderResult(decision=d, **base)

    combined = build_reliable_hints(row)
    fh = ex_hints.extract_hints_from_text(doc_text)
    if fh:
        combined += "\n" + fh
    prompt = build_prompt(doc_text, combined)

    response = deps.llm(prompt)
    if not response:
        return TenderResult(decision=Decision.ERROR, **base)
    response = clean_response_preamble(response)
    response = postprocess_response(response, combined)
    decision = classify_response(response)

    china = extract_china_flag(response)
    decision = apply_post_checks(response, decision, china, nac_regime)

    suppliers_text = ""
    doc_path = None
    if decision in (Decision.PARTICIPATE, Decision.CLARIFY):
        suppliers_text = deps.search(subject, None, china) or ""
        doc_path = deps.report(reg, deadline, response, suppliers_text)

    return TenderResult(doc_path=doc_path, decision=decision, china_flag=china,
                        suppliers_found=bool(suppliers_text), **base)