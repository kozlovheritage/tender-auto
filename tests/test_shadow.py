import json


def test_shadow_wrapping_preserves_old_behavior(tmp_path, monkeypatch):
    import shadow_wiring
    monkeypatch.setattr(shadow_wiring, "_DIFF", tmp_path / "diff.jsonl")

    def old_pre(s):
        return None

    g = {"check_stopfactors_preprocess": old_pre}
    shadow_wiring.apply(g)
    assert g["check_stopfactors_preprocess"] is not old_pre
    assert g["check_stopfactors_preprocess"]("Поставка насосов") is None


def test_shadow_logs_diff(tmp_path, monkeypatch):
    import shadow_wiring
    diff_path = tmp_path / "diff.jsonl"
    monkeypatch.setattr(shadow_wiring, "_DIFF", diff_path)

    def old_pre(s):
        return "старый стоп-фактор"   # старая логика бракует

    g = {"check_stopfactors_preprocess": old_pre}
    shadow_wiring.apply(g)
    # tendercore не бракует «Поставка станков» → расхождение
    assert g["check_stopfactors_preprocess"]("Поставка станков") == "старый стоп-фактор"

    lines = diff_path.read_text(encoding="utf-8").strip().splitlines()
    assert any('"point": "precheck"' in ln for ln in lines)
    rec = json.loads(lines[0])
    assert rec["old"].startswith("старый стоп-фактор")