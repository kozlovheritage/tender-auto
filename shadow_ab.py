#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Теневой A/B: сверка решений tendercore против монолита по сохранённым логам."""
import re, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from tendercore.llm import (classify_response, clean_response_preamble,
                            postprocess_response, extract_china_flag)
from tendercore.analysis import postcheck

LOGS = ROOT / "output" / "logs"
LABELS = {"participate": "Участвуем", "clarify": "Уточнение",
          "not_participate": "Отказ", "error": "Ошибка"}


def read_response(log_path):
    text = log_path.read_text(encoding="utf-8")
    m = re.search(r'ОТВЕТ:\n(.*)', text, re.DOTALL)
    return m.group(1) if m else text


def tendercore_decision(response):
    response = clean_response_preamble(response)
    response = postprocess_response(response, "")   # идемпотентно для готового ответа
    decision = classify_response(response)
    china = extract_china_flag(response)
    return postcheck.run_post_validations(response, decision, china_flag=china)


def monolith_decisions():
    db = ROOT / "data" / "decisions.db"
    out = {}
    if db.exists():
        conn = sqlite3.connect(str(db))
        for reg, dec in conn.execute("SELECT tender_number, decision FROM decisions"):
            out[reg] = dec
        conn.close()
    return out


def main():
    mono = monolith_decisions()
    total = match = 0
    div = []
    for log_file in sorted(LOGS.glob("*_log.txt")):
        reg = log_file.name.replace("_log.txt", "")
        mo = mono.get(reg)
        if mo in (None, "error"):
            continue                      # монолит не дошёл до LLM — не сравниваем
        tc = tendercore_decision(read_response(log_file))
        total += 1
        if tc == mo:
            match += 1
        else:
            div.append((reg, mo, tc))
    print(f"Сравнено: {total}  |  Совпало: {match}")
    if total:
        print(f"Паритет:  {100.0 * match / total:.1f}%")
    for reg, mo, tc in div:
        print(f"  ⚠️ {reg}: монолит={LABELS.get(mo, mo)}  tendercore={LABELS.get(tc, tc)}")
    if not div:
        print("\n✅ Расхождений нет — паритет полный.")
    else:
        print("\nРасхождения выше — разобрать вручную (часть может быть ОСОЗНАННЫМ улучшением).")


if __name__ == "__main__":
    main()