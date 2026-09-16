"""信号复盘测试：分组统计的算法必须算得对。"""

import numpy as np
import pandas as pd
import pytest

from src import signal_stats


def _frame(closes, groups) -> tuple[pd.Series, pd.Series]:
    index = pd.bdate_range("2026-01-01", periods=len(closes))
    return pd.Series(groups, index=index), pd.Series(closes, index=index, dtype=float)


def test_forward_return_math():
    close = pd.Series([100.0, 110.0, 121.0], index=pd.bdate_range("2026-01-01", periods=3))
    forward = signal_stats._forward_return(close, 1)
    assert forward.iloc[0] == pytest.approx(10.0)
    assert forward.iloc[1] == pytest.approx(10.0)
    assert np.isnan(forward.iloc[-1])       # 最后一天没有"之后一天"


def test_build_stats_groups_and_counts():
    groups, close = _frame([100.0, 110.0, 120.0, 130.0], ["normal", "watch", "normal", "watch"])
    stats = signal_stats.build_stats(groups, close, horizons=(1,))

    by_group = stats.set_index("group")
    assert by_group.loc["normal", "days"] == 2
    assert by_group.loc["watch", "days"] == 2
    # normal：100→110（+10%）、120→130（+8.33%），平均约 +9.17%
    assert by_group.loc["normal", "mean_1"] == pytest.approx(9.1667, abs=0.001)


def test_build_stats_down_rate():
    closes = [100.0, 95.0, 90.0, 85.0, 80.0, 75.0, 70.0, 65.0, 60.0, 55.0]
    groups, close = _frame(closes, ["watch"] * len(closes))
    stats = signal_stats.build_stats(groups, close, horizons=(5,))

    row = stats.iloc[0]
    assert row["days"] == len(closes)
    assert row["mean_5"] < 0
    assert row["down_rate_5"] == pytest.approx(100.0)   # 一路下跌，5 天后全是负的


def test_by_level_returns_empty_when_column_missing():
    groups, close = _frame([100.0, 101.0], ["normal", "normal"])
    frame = pd.DataFrame({"SP500_close": close})
    assert signal_stats.by_level(frame, "SP500").empty


def test_review_rows_on_synthetic_history(history_frame):
    rows = signal_stats.review_rows(history_frame)
    assert rows
    assert all({"分组", "样本天数", "之后 5 日"} <= set(row) for row in rows)
    labels = [row["分组"] for row in rows]
    # 状态在前，信号在后，而且顺序是按严重程度排的
    assert labels[0].startswith("状态｜")
    assert any(label.startswith("标普信号｜") for label in labels)


def test_small_sample_note():
    rows = [{"分组": "状态｜Panic", "样本天数": 3}, {"分组": "状态｜Neutral", "样本天数": 80}]
    note = signal_stats.small_sample_note(rows)
    assert note and "Panic" in note
    assert signal_stats.small_sample_note([{"分组": "x", "样本天数": 50}]) is None
