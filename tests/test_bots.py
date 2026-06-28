"""Bot registry: independence and correct data scope per bot."""
import pytest

from trader.bots import BOT_NAMES, get_bot


def test_all_bots_resolve():
    for name in BOT_NAMES:
        assert get_bot(name).name == name


def test_unknown_bot_raises():
    with pytest.raises(ValueError):
        get_bot("nope")


def test_bots_are_independent():
    bots = [get_bot(n) for n in BOT_NAMES]
    journals = {str(b.journal_db) for b in bots}
    params = {str(b.params_file) for b in bots}
    assert len(journals) == len(bots)   # no shared journal
    assert len(params) == len(bots)     # no shared params file


def test_equity_bots_trade_equities():
    for name in ("champion", "challenger"):
        tickers = get_bot(name).data_tickers
        assert "AAPL" in tickers and "SPY" in tickers


def test_multiasset_trades_etfs_not_single_stocks():
    t = get_bot("multiasset").data_tickers
    assert {"SPY", "EFA", "TLT", "GLD", "BIL"}.issubset(set(t))
    assert "AAPL" not in t  # it's an asset-class sleeve, not stock picking
