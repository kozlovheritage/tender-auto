import importlib

import pytest

import tendercore.config as cfg


@pytest.fixture(autouse=True)
def _clean_cache():
    cfg.reset()
    yield
    cfg.reset()


def test_extraction_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("TENDER_CONFIG", str(tmp_path / "nope.toml"))
    data = cfg.load(force=True)
    assert data["extraction"]["max_text_total"] == 200000
    assert data["extraction"]["max_text_per_file"] == 40000


def test_extraction_override(tmp_path, monkeypatch):
    p = tmp_path / "settings.toml"
    p.write_text("[extraction]\nmax_text_total = 300000\nmax_text_per_file = 60000\n",
                 encoding="utf-8")
    monkeypatch.setenv("TENDER_CONFIG", str(p))
    cfg.reset()
    assert cfg.get("extraction", "max_text_total") == 300000
    assert cfg.get("extraction", "max_text_per_file") == 60000


def test_text_module_reads_config(tmp_path, monkeypatch):
    import tendercore.extract.text as t
    p = tmp_path / "settings.toml"
    p.write_text("[extraction]\nmax_text_total = 300000\nmax_text_per_file = 12345\n",
                 encoding="utf-8")
    monkeypatch.setenv("TENDER_CONFIG", str(p))
    cfg.reset()
    importlib.reload(t)
    try:
        assert t.MAX_TEXT_TOTAL == 300000
        assert t.MAX_TEXT_PER_FILE == 12345
    finally:
        monkeypatch.delenv("TENDER_CONFIG", raising=False)
        cfg.reset()
        importlib.reload(t)
