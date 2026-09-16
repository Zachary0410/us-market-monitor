"""判断层测试：规则该触发时必须触发，不该触发时不能乱报。"""

from datetime import date

import pandas as pd
import pytest

import config
from src import signals


def make_table(sp500=0.0, ndx=0.0, vix=20.0, vix_change=0.0, ma20_dev=0.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "last_date": [date(2026, 9, 14)] * 3,
            "trading_days": [260] * 3,
            "close": [7000.0, 25000.0, vix],
            "change_1d": [sp500, ndx, vix_change],
            "change_5d": [0.0] * 3,
            "change_20d": [0.0] * 3,
            "ma20": [7000.0, 25000.0, 20.0],
            "ma50": [7000.0, 25000.0, 20.0],
            "close_vs_ma20": [ma20_dev] * 3,
        },
        index=["SP500", "NDX", "VIX"],
    )


def test_quiet_market_is_normal():
    verdict = signals.evaluate("SP500", make_table().loc["SP500"])
    assert verdict["level"] == "normal"
    assert verdict["reasons"] == []


@pytest.mark.parametrize(
    ("change", "expected"),
    [(1.6, "watch"), (-3.2, "alert"), (0.4, "normal")],
)
def test_daily_move_thresholds(change, expected):
    row = make_table(sp500=change).loc["SP500"]
    assert signals.evaluate("SP500", row)["level"] == expected


@pytest.mark.parametrize(("vix", "expected"), [(36.0, "alert"), (26.0, "watch"), (18.0, "normal")])
def test_vix_level_thresholds(vix, expected):
    row = make_table(vix=vix).loc["VIX"]
    assert signals.evaluate("VIX", row)["level"] == expected


@pytest.mark.parametrize(("deviation", "expected"), [(4.0, "watch"), (7.0, "alert"), (1.0, "normal")])
def test_ma20_deviation_thresholds(deviation, expected):
    row = make_table(ma20_dev=deviation).loc["SP500"]
    assert signals.evaluate("SP500", row)["level"] == expected


def test_vix_has_no_ma20_rule():
    """VIX 天然贴着均线大幅摆动，所以故意没给它设这条规则。"""
    row = make_table(ma20_dev=25.0).loc["VIX"]
    assert signals.evaluate("VIX", row)["level"] == "normal"


def test_divergence_rule_is_attached_to_ndx():
    table = make_table(sp500=0.0, ndx=4.0)
    verdicts = signals.evaluate_all(table)
    assert any("相差" in reason for reason in verdicts["NDX"]["reasons"])
    assert verdicts["NDX"]["level"] == "alert"


def test_missing_symbol_becomes_watch():
    """今天没取到数据的标的也要出现在结论里，标成"关注"。"""
    table = make_table().drop(index=["VIX"])
    verdicts = signals.evaluate_all(table)
    assert set(verdicts) == set(config.SYMBOLS)
    assert verdicts["VIX"]["level"] == "watch"
    assert "没有取到 VIX 的数据" in verdicts["VIX"]["reasons"][0]


def test_incomplete_metrics_become_watch():
    row = pd.Series({"close": float("nan"), "change_1d": float("nan")})
    verdict = signals.evaluate("SP500", row)
    assert verdict["level"] == "watch"
    assert "数据不完整" in verdict["reasons"][0]


def test_overall_level_takes_the_worst():
    verdicts = {
        "SP500": {"level": "normal", "reasons": []},
        "NDX": {"level": "watch", "reasons": []},
        "VIX": {"level": "alert", "reasons": []},
    }
    assert signals.overall_level(verdicts) == "alert"
    assert signals.overall_level({}) == "normal"
