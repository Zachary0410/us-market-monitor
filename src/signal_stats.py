"""信号复盘：用现成的历史数据回答"我这些信号到底有没有用"。

只读 data\\history.csv，不改流水线、不联网、不写任何文件。

做法很朴素：
    1. 把每个交易日按某种口径分组（当天是"正常/关注/警报"，或哪个风险等级）
    2. 算这一天之后 1 / 5 / 20 个交易日，目标指数涨跌了多少
    3. 按组统计平均值、中位数、下跌占比

如果"关注/警报"那几组之后的表现明显比"正常"差，说明阈值定得有意义；
如果两者差不多，那这些信号就是噪音，该调阈值了。

样本少的时候结论不可靠——表里会同时给出每组的天数，少于 10 天的只看方向。
"""

import pandas as pd

import config
from src import market_state

HORIZONS = (1, 5, 20)
DEFAULT_TARGET = "SP500"

# 分组显示顺序（不要按字母排，按严重程度排）
LEVEL_ORDER = ["normal", "watch", "alert"]
STATE_ORDER = ["risk_on", "neutral", "risk_off", "panic"]

LEVEL_LABELS = {"normal": "正常", "watch": "关注", "alert": "警报"}

SMALL_SAMPLE = 10      # 少于这么多天的组，结论仅供参考


def _forward_return(close: pd.Series, horizon: int) -> pd.Series:
    """从每个交易日往后看 horizon 天的涨跌幅（%）。最后几天是 NaN。"""
    return (close.shift(-horizon) / close - 1) * 100


def build_stats(groups: pd.Series, target_close: pd.Series, horizons=HORIZONS) -> pd.DataFrame:
    """按分组统计"之后几天的表现"。

    groups       每个交易日属于哪个组
    target_close 用来衡量结果的收盘价（默认标普 500）
    """
    frame = pd.DataFrame({"group": groups})
    for horizon in horizons:
        frame[f"fwd_{horizon}"] = _forward_return(target_close, horizon)

    rows = []
    for name, chunk in frame.dropna(subset=["group"]).groupby("group", sort=False):
        row = {"group": name, "days": int(len(chunk))}
        for horizon in horizons:
            series = chunk[f"fwd_{horizon}"].dropna()
            row[f"mean_{horizon}"] = float(series.mean()) if len(series) else float("nan")
            if horizon == 5:
                row["median_5"] = float(series.median()) if len(series) else float("nan")
                row["down_rate_5"] = float((series < 0).mean() * 100) if len(series) else float("nan")
        rows.append(row)
    return pd.DataFrame(rows)


def by_level(history: pd.DataFrame, symbol: str, target: str = DEFAULT_TARGET) -> pd.DataFrame:
    """按某个标的当天的结论（正常/关注/警报）分组。"""
    column = f"{symbol}_level"
    if column not in history.columns:
        return pd.DataFrame()
    return build_stats(history[column], history[f"{target}_close"])


def by_state(history: pd.DataFrame, target: str = DEFAULT_TARGET) -> pd.DataFrame:
    """按市场状态（Risk-on / Neutral / Risk-off / Panic）分组。"""
    daily = market_state.build_daily_table(history)
    if daily.empty:
        return pd.DataFrame()
    states = daily.apply(market_state.state_row, axis=1)
    return build_stats(states, history[f"{target}_close"])


def _format_table(stats: pd.DataFrame, order: list[str], prefix: str) -> list[dict]:
    """把统计结果整理成给人看的几行（已按严重程度排序）。"""
    rows = []
    for name in order:
        matched = stats[stats["group"] == name]
        if matched.empty:
            continue
        item = matched.iloc[0]
        label = LEVEL_LABELS.get(name) or market_state.STATES.get(name, {}).get("label", name)
        rows.append(
            {
                "分组": f"{prefix}{label}",
                "样本天数": int(item["days"]),
                "之后 1 日": item["mean_1"],
                "之后 5 日": item["mean_5"],
                "之后 20 日": item["mean_20"],
                "之后 5 日中位数": item["median_5"],
                "之后 5 日下跌占比": item["down_rate_5"],
            }
        )
    return rows


def review_rows(history: pd.DataFrame, target: str = DEFAULT_TARGET) -> list[dict]:
    """给网页用的一张表：市场状态 + 标普信号 + VIX 信号。"""
    rows: list[dict] = []
    rows += _format_table(by_state(history, target), STATE_ORDER, "状态｜")
    rows += _format_table(by_level(history, "SP500", target), LEVEL_ORDER, "标普信号｜")
    rows += _format_table(by_level(history, "VIX", target), LEVEL_ORDER, "VIX 信号｜")
    return rows


def small_sample_note(rows: list[dict]) -> str | None:
    """样本太少的组给一句提醒——别拿三五天当规律。"""
    tiny = [row["分组"] for row in rows if row["样本天数"] < SMALL_SAMPLE]
    if not tiny:
        return None
    return "样本少于 " + str(SMALL_SAMPLE) + " 天的组结论不可靠，只看方向：" + "、".join(tiny)


if __name__ == "__main__":
    from src import history as history_module

    data = history_module.load_history()
    if data.empty:
        print("还没有历史数据，先跑一次 run_daily.py")
        raise SystemExit

    print(f"数据范围：{data.index.min().date()} ~ {data.index.max().date()}（{len(data)} 个交易日）")
    print(f"衡量口径：{DEFAULT_TARGET} 之后的涨跌幅\n")

    rows = review_rows(data)
    if not rows:
        print("数据不够，算不出分组统计。")
        raise SystemExit

    table = pd.DataFrame(rows)
    for column in ("之后 1 日", "之后 5 日", "之后 20 日", "之后 5 日中位数"):
        table[column] = table[column].map(lambda value: f"{value:+.2f}%")
    table["之后 5 日下跌占比"] = table["之后 5 日下跌占比"].map(lambda value: f"{value:.0f}%")
    print(table.to_string(index=False))

    note = small_sample_note(rows)
    if note:
        print(f"\n提醒：{note}")
