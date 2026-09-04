import pytest

import tendercore.config as cfg


@pytest.fixture(autouse=True)
def _clean_cache():
    cfg.reset()
    yield
    cfg.reset()


def test_defaults_without_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TENDER_CONFIG", str(tmp_path / "nope.toml"))
    data = cfg.load(force=True)
    assert data["thresholds"]["min_delivery_days"] == 30


def test_override_from_file(tmp_path, monkeypatch):
    p = tmp_path / "settings.toml"
    p.write_text("[thresholds]\nmin_delivery_days = 45\n", encoding="utf-8")
    monkeypatch.setenv("TENDER_CONFIG", str(p))
    assert cfg.load(force=True)["thresholds"]["min_delivery_days"] == 45


def test_get_helper_and_merge(tmp_path, monkeypatch):
    p = tmp_path / "settings.toml"
    p.write_text("[thresholds]\nmin_delivery_days = 45\n", encoding="utf-8")
    monkeypatch.setenv("TENDER_CONFIG", str(p))
    cfg.load(force=True)
    assert cfg.get("thresholds", "min_delivery_days") == 45
    assert cfg.get("thresholds", "no_such_key", default=7) == 7


def test_broken_config_falls_back_to_defaults(tmp_path, monkeypatch):
    p = tmp_path / "settings.toml"
    p.write_text("это не toml [[[", encoding="utf-8")
    monkeypatch.setenv("TENDER_CONFIG", str(p))
    data = cfg.load(force=True)
    assert data["thresholds"]["min_delivery_days"] == 30


def test_validate_term_respects_config(tmp_path, monkeypatch):
    from tendercore.analysis.postcheck import validate_delivery_term
    p = tmp_path / "settings.toml"
    monkeypatch.setenv("TENDER_CONFIG", str(p))
    p.write_text("[thresholds]\nmin_delivery_days = 10\n", encoding="utf-8")
    cfg.reset()
    assert validate_delivery_term("Срок поставки: 15 календарных дней")[1] is None
    p.write_text("[thresholds]\nmin_delivery_days = 20\n", encoding="utf-8")
    cfg.reset()
    assert validate_delivery_term("Срок поставки: 15 календарных дней")[1] is not None
