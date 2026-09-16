"""展示层分析测试：评分可解释、状态分级、边界情况。"""

import pandas as pd
import pytest

import config
from src import market_state


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, "risk_on"),
        (19.9, "risk_on"),
        (20, "neutral"),
        (44.9, "neutral"),
        (45, "risk_off"),
        (69.9, "risk_off"),
        (70, "panic"),
        (100, "panic"),
    ],
)
def test_state_thresholds(score, expected):
    assert market_state.state_for(score) == expected


def test_score_equals_sum_of_listed_parts(history_frame):
    """界面上列出的加分项加起来必须等于显示的分数。

    用户看到的分数必须是能自己算出来的——否则"可解释"就是假的。
    """
    daily = market_state.build_daily_table(history_frame)
    result = market_state.assess(daily)
    assert result["score"] == min(100, round(sum(part["points"] for part in result["parts"])))
    assert 0 <= result["score"] <= 100


def test_assess_on_empty_data_is_safe():
    result = market_state.assess(pd.DataFrame())
    assert result["score"] == 0
    assert result["checks"] == []
    assert result["label"] == market_state.STATES["neutral"]["label"]


def test_checks_always_carry_explanations(history_frame):
    daily = market_state.build_daily_table(history_frame)
    result = market_state.assess(daily)
    assert result["checks"]
    for item in result["checks"]:
        assert item["ok"] in (True, False, None)
        assert isinstance(item["text"], str) and item["text"]


def test_attention_items_matches_warning_checks(history_frame):
    daily = market_state.build_daily_table(history_frame)
    result = market_state.assess(daily)
    warnings = [item["text"] for item in result["checks"] if item["ok"] is False]
    assert market_state.attention_items(result) == warnings


def test_daily_cards_are_newest_first(history_frame):
    daily = market_state.build_daily_table(history_frame)
    cards = market_state.daily_cards(daily, days=5)
    assert len(cards) == 5
    assert cards[0]["day"] > cards[-1]["day"]
    assert set(cards[0]["values"]) == set(config.SYMBOLS)
    assert "score" in cards[0] and "warnings" in cards[0]


def test_daily_cards_on_empty_data():
    assert market_state.daily_cards(pd.DataFrame(), days=5) == []


@pytest.mark.parametrize(
    ("vix", "color"),
    [(12.0, "green"), (17.0, "gray"), (22.0, "orange"), (30.0, "orange"), (45.0, "red")],
)
def test_vix_zone_colors(vix, color):
    assert market_state.vix_zone(vix)[1] == color


def test_vix_zone_handles_missing_value():
    assert market_state.vix_zone(float("nan"))[1] == "gray"


def test_build_daily_table_has_ma_and_streak(history_frame):
    daily = market_state.build_daily_table(history_frame)
    for column in ("SP500_ma50", "SP500_ma200", "SP500_dist_high", "SP500_down_streak", "gap_ndx_sp500"):
        assert column in daily.columns
