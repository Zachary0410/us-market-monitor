"""指标层测试。纯计算，不联网。"""

import math

import pandas as pd
import pytest

import config
from src import metrics


def test_change_pct_basic():
    closes = pd.Series([100.0, 110.0])
    assert metrics.change_pct(closes, 1) == pytest.approx(10.0)


def test_change_pct_not_enough_history_returns_nan():
    """样本不够要返回 NaN，而不是抛异常——否则某天数据缺失整份日报就没了。"""
    closes = pd.Series([100.0, 110.0])
    assert math.isnan(metrics.change_pct(closes, 5))


def test_change_pct_handles_zero_base():
    assert math.isnan(metrics.change_pct(pd.Series([0.0, 10.0]), 1))


def test_moving_average():
    closes = pd.Series([1.0, 2.0, 3.0, 4.0])
    assert metrics.moving_average(closes, 2) == pytest.approx(3.5)
    assert math.isnan(metrics.moving_average(closes, 10))


def test_build_metrics_contract(metrics_table):
    """输出表的结构就是给 signals 的"数据合同"，列名和顺序都不能变。"""
    assert list(metrics_table.columns) == metrics.METRIC_COLUMNS
    assert set(metrics_table.index) == set(config.SYMBOLS)


def test_build_metrics_short_history_gives_nan_not_crash():
    index = pd.bdate_range("2026-01-01", periods=10)
    short = {"SP500": pd.DataFrame({"close": range(10)}, index=index, dtype=float)}

    table = metrics.build_metrics(short)
    assert not math.isnan(table.loc["SP500", "change_5d"])
    assert math.isnan(table.loc["SP500", "change_20d"])
    assert math.isnan(table.loc["SP500", "ma20"])
    assert math.isnan(table.loc["SP500", "close_vs_ma20"])


def test_build_metrics_as_of_looks_back(prices):
    """as_of 是"假如那天就收工"——历史回填靠它。"""
    full = metrics.build_metrics(prices)
    cut = prices["SP500"].index[100]
    earlier = metrics.build_metrics(prices, as_of=cut)

    assert earlier.loc["SP500", "close"] == pytest.approx(prices["SP500"]["close"].iloc[100])
    assert earlier.loc["SP500", "last_date"] < full.loc["SP500", "last_date"]
