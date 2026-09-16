"""pytest 的公共夹具。

两条铁律：
    1. 测试**不联网**——所有外部数据都靠假数据或打桩。
    2. 测试**不碰真实的 data/ 与 reports/**——目录被指到临时文件夹，跑完自动清理。
"""

from datetime import date

import pandas as pd
import pytest

import config


@pytest.fixture(autouse=True)
def temp_dirs(tmp_path, monkeypatch):
    """把所有落盘路径换到临时目录，避免测试污染真实数据。"""
    data_dir = tmp_path / "data"
    report_dir = tmp_path / "reports"
    data_dir.mkdir()
    report_dir.mkdir()
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "REPORT_DIR", report_dir)
    return tmp_path


def make_prices(days: int = 260, start: str = "2025-09-01") -> dict[str, pd.DataFrame]:
    """造三个标的的假日线，天数足够算 MA200。"""
    index = pd.bdate_range(start, periods=days)
    index.name = "date"
    result: dict[str, pd.DataFrame] = {}
    for name, base, drift in (("SP500", 5000.0, 4.0), ("NDX", 20000.0, 30.0), ("VIX", 20.0, -0.02)):
        close = pd.Series([base + drift * step for step in range(days)], index=index, dtype=float)
        result[name] = pd.DataFrame(
            {
                "open": close,
                "high": close * 1.002,
                "low": close * 0.998,
                "close": close,
                "volume": 1_000_000.0,
            },
            index=index,
        )
    return result


@pytest.fixture
def prices() -> dict[str, pd.DataFrame]:
    return make_prices()


@pytest.fixture
def metrics_table(prices):
    """真实的指标表（由 metrics 层算出，不是手写的）。"""
    from src import metrics

    return metrics.build_metrics(prices)


@pytest.fixture
def verdicts(metrics_table):
    from src import signals

    return signals.evaluate_all(metrics_table)


@pytest.fixture
def history_frame(prices) -> pd.DataFrame:
    """历史表的等价结构（列名和 data\\history.csv 一致）。"""
    frame = pd.DataFrame(index=prices["SP500"].index)
    for name, data in prices.items():
        close = data["close"]
        frame[f"{name}_close"] = close
        frame[f"{name}_change_1d"] = close.pct_change() * 100
        frame[f"{name}_close_vs_ma20"] = (close / close.rolling(20).mean() - 1) * 100
        frame[f"{name}_level"] = "normal"
    return frame


@pytest.fixture
def sample_day() -> date:
    return date(2026, 9, 14)
