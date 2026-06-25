"""Experiment ledger: storage, query, validation."""
import pytest

from trader.research.ledger import Experiment, Ledger


def test_add_and_retrieve(tmp_path):
    led = Ledger(tmp_path / "l.db")
    led.add(Experiment("test idea", "shipped", area="momentum", proposed_by="claude"))
    df = led.all()
    assert len(df) == 1
    assert df.iloc[0]["idea"] == "test idea"
    assert df.iloc[0]["date"]  # auto-stamped


def test_invalid_decision_raises():
    with pytest.raises(ValueError):
        Experiment("bad", "definitely-maybe")


def test_search_matches_fields(tmp_path):
    led = Ledger(tmp_path / "l.db")
    led.add(Experiment("weekly MR", "flag", result="turnover ate the signal"))
    led.add(Experiment("rank buffer", "shipped", reason="cheap win"))
    assert len(led.search("turnover")) == 1
    assert len(led.search("cheap")) == 1
    assert len(led.search("nonexistent")) == 0


def test_markdown_render(tmp_path):
    led = Ledger(tmp_path / "l.db")
    led.add(Experiment("multi-asset trend", "prototype", proposed_by="chatgpt+claude"))
    md = led.to_markdown()
    assert "multi-asset trend" in md
    assert "prototype" in md
    assert led.count() == 1
