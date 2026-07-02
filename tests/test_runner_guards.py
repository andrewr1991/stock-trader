"""Live-runner safety guards."""
from trader.live.journal import Journal
from trader.live.runner import is_suspect_equity


def test_suspect_equity_flags_transient_collapse():
    # The real incident: $659.92 read against a ~$100k book.
    assert is_suspect_equity(659.92, 100_000.0) is True


def test_suspect_equity_allows_normal_moves():
    assert is_suspect_equity(95_000.0, 100_000.0) is False   # -5%
    assert is_suspect_equity(70_000.0, 100_000.0) is False   # -30%, severe but real-possible
    assert is_suspect_equity(49_000.0, 100_000.0) is True    # -51%, beyond plausible/day


def test_suspect_equity_no_prior_mark():
    assert is_suspect_equity(100_000.0, None) is False        # first run, nothing to compare


def test_suspect_equity_flags_phantom_spike():
    # Mirror of the real low-read incident: a phantom HIGH read would poison
    # the journal's all-time peak and brick the bot via the kill switch.
    assert is_suspect_equity(250_000.0, 100_000.0) is True    # +150% in a day = bad read
    assert is_suspect_equity(1_000_000.0, 100_000.0) is True  # 10x = definitely a bad read


def test_suspect_equity_allows_large_but_real_gains():
    assert is_suspect_equity(115_000.0, 100_000.0) is False   # +15%, huge but possible
    assert is_suspect_equity(195_000.0, 100_000.0) is False   # +95%, absurd but under the 2x bound


def test_last_equity_returns_most_recent(tmp_path):
    j = Journal(tmp_path / "j.db")
    assert j.last_equity() is None
    j.log_equity("2026-06-24", 100_000.0, 0.0)
    j.log_equity("2026-06-25", 101_000.0, 0.0)
    assert j.last_equity() == 101_000.0
