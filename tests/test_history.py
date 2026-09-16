"""历史层测试：一天一行、日期口径、缓存指纹。"""

from datetime import date

import pandas as pd

from src import history


def test_snapshot_day_returns_plain_date(metrics_table, prices):
    """必须返回纯 date。

    带时分秒的话拼进文件名会变成 "2026-09-14 00:00:00.md"，Windows 直接拒绝——
    这是真实踩过的坑。
    """
    day = history.snapshot_day(metrics_table, date(2026, 9, 20))
    assert isinstance(day, date)
    assert not isinstance(day, pd.Timestamp)
    assert day == prices["SP500"].index[-1].date()


def test_append_snapshot_uses_data_date_not_run_date(metrics_table, verdicts, prices):
    """行要记在交易日上，不是"今天"（报告文件名错位那个 bug 的回归测试）。"""
    history.append_snapshot(metrics_table, verdicts, today=date(2026, 9, 20))
    frame = history.load_history()
    assert frame.index[0].date() == prices["SP500"].index[-1].date()


def test_append_snapshot_keeps_one_row_per_day(metrics_table, verdicts):
    """同一个交易日跑两次，只能留一行。"""
    history.append_snapshot(metrics_table, verdicts, today=date(2026, 9, 14))
    history.append_snapshot(metrics_table, verdicts, today=date(2026, 9, 14))
    assert len(history.load_history()) == 1


def test_snapshot_stores_levels(metrics_table, verdicts):
    history.append_snapshot(metrics_table, verdicts, today=date(2026, 9, 14))
    frame = history.load_history()
    for name in ("SP500", "NDX", "VIX"):
        assert frame[f"{name}_level"].iloc[0] == verdicts[name]["level"]


def test_fingerprint_changes_after_write(metrics_table, verdicts):
    """指纹是网页的缓存钥匙，文件一变就必须变。"""
    before = history.fingerprint()
    history.append_snapshot(metrics_table, verdicts, today=date(2026, 9, 14))
    assert history.fingerprint() != before


def test_fingerprint_when_no_file():
    assert history.fingerprint() == (0.0, 0)


def test_backfill_fills_requested_days(prices):
    filled = history.backfill(prices, days=30)
    assert filled == 30
    assert len(history.load_history()) == 30


def test_load_history_without_file_is_empty():
    assert history.load_history().empty
