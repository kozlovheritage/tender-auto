import re
from pathlib import Path

from tendercore.analysis.prompt import MASTER_PROMPT, build_prompt

MONO = Path(__file__).resolve().parents[1] / "tender_auto.py"


def test_master_prompt_parity_with_monolith():
    src = MONO.read_text(encoding="utf-8")
    m = re.search(r'MASTER_PROMPT = """(.*?)\n"""', src, re.DOTALL)
    assert m, "MASTER_PROMPT не найден в монолите"
    assert MASTER_PROMPT == m.group(1) + "\n"


def test_build_prompt_includes_doc_and_hints():
    p = build_prompt("ТЕКСТ ДОКУМЕНТА", "ПОДСКАЗКА Х")
    assert "ТЕКСТ ДОКУМЕНТА" in p
    assert "ПОДСКАЗКА Х" in p
    assert "Содержание документов" in p


def test_build_prompt_keeps_stop_factors():
    p = build_prompt("x")
    assert "СТОП-ФАКТОРЫ" in p
    assert "Решение:" in p