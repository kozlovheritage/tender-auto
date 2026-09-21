import json

from tendercore.cli import main


def _write_queue(tmp_path, tenders):
    p = tmp_path / "q.json"
    p.write_text(json.dumps({"tenders": tenders}, ensure_ascii=False), encoding="utf-8")
    return p


def test_cli_valid(tmp_path):
    p = _write_queue(tmp_path, [{
        "tender_number": "1", "tender_subject": "S", "tender_deadline": "01.01.2026",
        "tender_price": "100", "tender_url": "https://x",
        "items_table": [{"item": "Товар", "part_number": "A1"}],
    }])
    assert main(["validate-rfq", "--queue", str(p)]) == 0


def test_cli_invalid(tmp_path):
    p = _write_queue(tmp_path, [{"tender_number": "2"}])
    assert main(["validate-rfq", "--queue", str(p)]) == 1