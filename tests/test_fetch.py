"""取数层测试。不联网——所有请求都打桩。"""

import pandas as pd
import pytest

from src import fetch


def test_to_range_buckets():
    """天数要映射到 Yahoo 认识的那几档 range。"""
    assert fetch._to_range(5) == "5d"
    assert fetch._to_range(22) == "1mo"
    assert fetch._to_range(66) == "3mo"
    assert fetch._to_range(130) == "6mo"
    assert fetch._to_range(250) == "1y"
    assert fetch._to_range(520) == "2y"
    assert fetch._to_range(999) == "5y"


def _frame_with(dates):
    return pd.DataFrame({"close": [1.0] * len(dates)}, index=pd.DatetimeIndex(dates))


def test_drop_unfinished_session_before_close(monkeypatch):
    """盘中（美东 10:00）当天的日线必须丢掉。

    这就是 VIX 假涨 12% 那个 bug 的回归测试：盘前 VIX 更新得比指数早，
    不丢掉的话三个标的会混着两个日期。
    """
    monkeypatch.setattr(fetch, "_now_new_york", lambda: pd.Timestamp("2026-09-14 10:00", tz="America/New_York"))
    kept = fetch._drop_unfinished_session(_frame_with(["2026-09-11", "2026-09-14"]))
    assert list(kept.index) == [pd.Timestamp("2026-09-11")]


def test_drop_unfinished_session_after_close(monkeypatch):
    """收盘之后（美东 18:00）当天的日线要保留。"""
    monkeypatch.setattr(fetch, "_now_new_york", lambda: pd.Timestamp("2026-09-14 18:00", tz="America/New_York"))
    kept = fetch._drop_unfinished_session(_frame_with(["2026-09-11", "2026-09-14"]))
    assert len(kept) == 2


def _payload(dates) -> dict:
    """造一份 Yahoo 图表接口的返回（时间戳用美股开盘的 14:30 UTC）。"""
    stamps = [int(pd.Timestamp(f"{day} 14:30", tz="UTC").timestamp()) for day in dates]
    closes = [100.0 + index for index in range(len(dates))]
    return {
        "chart": {
            "result": [
                {
                    "timestamp": stamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": closes,
                                "high": closes,
                                "low": closes,
                                "close": closes,
                                "volume": [1] * len(dates),
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


class _FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_fetch_index_parses_payload(monkeypatch):
    """把接口返回整理成约定的 DataFrame（日期索引 + 五列）。"""
    payload = _payload(["2024-01-02", "2024-01-03", "2024-01-04"])
    monkeypatch.setattr(fetch.requests, "get", lambda *args, **kwargs: _FakeResponse(payload))

    frame = fetch.fetch_index("^GSPC", days=5)
    assert list(frame.columns) == fetch.COLUMNS
    assert frame.index.name == "date"
    assert len(frame) == 3
    assert frame["close"].iloc[-1] == pytest.approx(102.0)
    assert str(frame.index[-1].date()) == "2024-01-04"     # 交易日不能偏移


def test_fetch_index_404_gives_clear_message(monkeypatch):
    """代码写错时要立刻报错，而不是傻等重试。"""
    monkeypatch.setattr(fetch.requests, "get", lambda *args, **kwargs: _FakeResponse(status_code=404))
    with pytest.raises(fetch.FetchError) as info:
        fetch.fetch_index("NOTREAL", days=5)
    assert "找不到" in str(info.value)


def test_fetch_index_empty_result_raises(monkeypatch):
    monkeypatch.setattr(
        fetch.requests, "get", lambda *args, **kwargs: _FakeResponse({"chart": {"result": [], "error": None}})
    )
    with pytest.raises(fetch.FetchError):
        fetch.fetch_index("NOTREAL", days=5)


def test_fetch_all_keeps_going_when_one_symbol_fails(monkeypatch):
    """一个标的挂了，其他标的照常返回（日报里能显示"今天缺了谁"）。"""

    def fake_index(symbol, days=250, timeout=20):
        if symbol == "^VIX":
            raise fetch.FetchError("VIX: 模拟失败")
        return _frame_with(["2026-09-11"])

    monkeypatch.setattr(fetch, "fetch_index", fake_index)
    assert set(fetch.fetch_all()) == {"SP500", "NDX"}


def test_fetch_all_raises_when_everything_fails(monkeypatch):
    def fake_index(symbol, days=250, timeout=20):
        raise fetch.FetchError(f"{symbol}: 模拟失败")

    monkeypatch.setattr(fetch, "fetch_index", fake_index)
    with pytest.raises(fetch.FetchError):
        fetch.fetch_all()
