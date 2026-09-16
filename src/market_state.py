"""市场状态层：把"每天的行情数字"翻译成"现在是什么市场"。

这一层**只被网页（app.py）使用**，不参与日报流水线。
fetch / metrics / signals / history / report / run_daily 一行都不用改，
所以已有的日报、定时任务、缓存行为完全不受影响。

它回答四个问题：
    今天三个指数怎么样？          → build_daily_table() 算出来
    现在算 Risk-on 还是 Risk-off？ → assess() 给出的等级 + 风险评分
    为什么是这个结论？             → assess() 里每条得分都有文字说明
    最近这些天分别是什么状态？      → daily_cards()

评分怎么算（0-100，越高越危险）
    所有分数都是"加出来的"，每一分都能在界面上看到它的出处：
        VIX 绝对水平      0-40   分  VIX 越高分越多
        VIX 单日涨幅      0-15   分
        指数单日跌幅      0-15   分  取标普、纳指里跌得多的那个
        50 日均线位置     0-20   分  标普、纳指各 10 分，跌破均线才开始扣
        距 52 周高点      0-10   分
        连续下跌天数      0-10   分
    加起来最高 110，超过 100 就按 100 算。

    等级划分：<20 Risk-on｜20-45 Neutral｜45-70 Risk-off｜≥70 Panic
"""

from datetime import date

import pandas as pd

import config

# ---------- 等级 ----------
STATES = {
    "risk_on": {"label": "Risk-on", "emoji": "🟢", "color": "green", "hint": "风险偏好，市场情绪健康"},
    "neutral": {"label": "Neutral", "emoji": "🟡", "color": "orange", "hint": "中性，留意但不用紧张"},
    "risk_off": {"label": "Risk-off", "emoji": "🟠", "color": "orange", "hint": "避险情绪占上风"},
    "panic": {"label": "Panic", "emoji": "🔴", "color": "red", "hint": "恐慌状态，谨慎应对"},
}

# ---------- 评分曲线：[(数值, 得分), ...]，中间线性插值 ----------
VIX_LEVEL = [(12, 0), (15, 8), (18, 14), (20, 20), (25, 30), (30, 36), (40, 40)]
VIX_CHANGE = [(0, 0), (5, 3), (10, 7), (20, 12), (30, 15)]
INDEX_DROP = [(0, 0), (1, 3), (2, 7), (3, 11), (5, 15)]
BELOW_MA50 = [(0, 0), (1, 3), (3, 6), (5, 10)]
BELOW_HIGH = [(0, 0), (3, 2), (5, 4), (10, 7), (15, 10)]
DOWN_STREAK = [(0, 0), (2, 3), (3, 6), (4, 10)]

# 界面上用的显示名
DISPLAY_NAMES = {"SP500": "标普 500", "NDX": "纳斯达克 100", "VIX": "VIX"}


def _lerp(value, anchors) -> float:
    """在评分曲线上取值：数值落在两个锚点之间就线性插值，超出范围取端点。"""
    if value is None or pd.isna(value):
        return 0.0
    if value <= anchors[0][0]:
        return float(anchors[0][1])
    if value >= anchors[-1][0]:
        return float(anchors[-1][1])
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if x0 <= value <= x1:
            return float(y0 + (value - x0) / (x1 - x0) * (y1 - y0))
    return float(anchors[-1][1])


def _down_streak(closes: pd.Series) -> pd.Series:
    """连续下跌天数。涨的那天归零，连跌就累加。"""
    down = closes.diff() < 0
    groups = (~down).cumsum()
    return down.groupby(groups).cumsum().astype(float)


def build_daily_table(history: pd.DataFrame) -> pd.DataFrame:
    """把历史表加工成"每个交易日一行"的分析表。

    原始历史表只存了收盘价、单日涨跌、相对 MA20 偏离和结论；
    这里补上 5 日/20 日涨跌、MA20/50/200、距 52 周高点、连续下跌天数等，
    全部由收盘价现算，不改动 data\\history.csv 的存法。
    """
    if history.empty:
        return pd.DataFrame()

    table = pd.DataFrame(index=history.index)

    for name in config.SYMBOLS:
        close_column = f"{name}_close"
        if close_column not in history.columns:
            continue

        close = pd.to_numeric(history[close_column], errors="coerce")
        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()
        ma200 = close.rolling(200).mean()
        high_52w = close.rolling(252, min_periods=20).max()

        table[close_column] = close
        table[f"{name}_change_abs"] = close.diff()          # 今日涨跌额（绝对值）
        table[f"{name}_change_1d"] = pd.to_numeric(history.get(f"{name}_change_1d"), errors="coerce")
        table[f"{name}_change_5d"] = close.pct_change(5) * 100
        table[f"{name}_change_20d"] = close.pct_change(20) * 100
        table[f"{name}_ma20"] = ma20
        table[f"{name}_ma50"] = ma50
        table[f"{name}_ma200"] = ma200
        table[f"{name}_vs_ma50"] = (close / ma50 - 1) * 100
        table[f"{name}_vs_ma200"] = (close / ma200 - 1) * 100
        table[f"{name}_dist_high"] = (close / high_52w - 1) * 100
        table[f"{name}_down_streak"] = _down_streak(close)
        if f"{name}_level" in history.columns:
            table[f"{name}_level"] = history[f"{name}_level"]

    # 跨指标：纳指与标普的当日分化
    if "SP500_change_1d" in table.columns and "NDX_change_1d" in table.columns:
        table["gap_ndx_sp500"] = table["NDX_change_1d"] - table["SP500_change_1d"]

    return table


def state_for(score: float) -> str:
    """风险评分 → 等级。"""
    if score < 20:
        return "risk_on"
    if score < 45:
        return "neutral"
    if score < 70:
        return "risk_off"
    return "panic"


def score_row(row: pd.Series) -> int:
    """按评分曲线算出这一行的分数（0-100）。"""
    return min(100, int(round(sum(item["points"] for item in _score_parts(row)))))


def state_row(row: pd.Series) -> str:
    """这一行属于哪个等级。"""
    return state_for(score_row(row))


def _score_parts(row: pd.Series) -> list[dict]:
    """拆出每一分的来源。返回的每一项都能直接显示在界面上。"""
    parts: list[dict] = []

    def add(points: float, text: str) -> None:
        if points >= 0.5:
            parts.append({"points": round(points), "text": text})

    # 1) VIX 绝对水平
    vix = row.get("VIX_close")
    if vix is not None and not pd.isna(vix):
        points = _lerp(vix, VIX_LEVEL)
        if points >= 0.5:
            if vix >= 25:
                mood = "已经进入紧张区间"
            elif vix >= 18:
                mood = "偏高，市场有点不安"
            elif vix >= 15:
                mood = "略高于平静区"
            else:
                mood = "属于平静区"
            add(points, f"VIX = {vix:.2f}（{mood}）")

    # 2) VIX 单日涨幅
    vix_change = row.get("VIX_change_1d")
    if vix_change is not None and not pd.isna(vix_change) and vix_change > 0:
        points = _lerp(vix_change, VIX_CHANGE)
        add(points, f"VIX 单日 +{vix_change:.2f}%，波动放大")

    # 3) 指数单日跌幅（取跌得多的那个）
    worst_name, worst_change = None, 0.0
    for name in ("SP500", "NDX"):
        change = row.get(f"{name}_change_1d")
        if change is not None and not pd.isna(change) and change < worst_change:
            worst_name, worst_change = name, float(change)
    if worst_name:
        points = _lerp(abs(worst_change), INDEX_DROP)
        add(points, f"{DISPLAY_NAMES[worst_name]} 单日 {worst_change:+.2f}%")

    # 4) 50 日均线位置（跌破才计分）
    below = []
    for name in ("SP500", "NDX"):
        deviation = row.get(f"{name}_vs_ma50")
        if deviation is None or pd.isna(deviation) or deviation >= 0:
            continue
        points = _lerp(abs(deviation), BELOW_MA50)
        below.append((name, deviation, points))
    for name, deviation, points in below:
        add(points, f"{DISPLAY_NAMES[name]} 低于 50 日均线 {abs(deviation):.2f}%")

    # 5) 距 52 周高点
    deepest_name, deepest = None, 0.0
    for name in ("SP500", "NDX"):
        distance = row.get(f"{name}_dist_high")
        if distance is not None and not pd.isna(distance) and distance < deepest:
            deepest_name, deepest = name, float(distance)
    if deepest_name:
        points = _lerp(abs(deepest), BELOW_HIGH)
        add(points, f"{DISPLAY_NAMES[deepest_name]} 距 52 周高点 {deepest:.2f}%")

    # 6) 连续下跌
    streak_name, streak = None, 0.0
    for name in ("SP500", "NDX"):
        value = row.get(f"{name}_down_streak")
        if value is not None and not pd.isna(value) and value > streak:
            streak_name, streak = name, float(value)
    if streak_name and streak >= 2:
        points = _lerp(streak, DOWN_STREAK)
        add(points, f"{DISPLAY_NAMES[streak_name]} 连续下跌 {int(streak)} 个交易日")

    return parts


def _checks(row: pd.Series) -> list[dict]:
    """✓ / ⚠ 清单：把"为什么是这个结论"摊开给人看。"""
    checks: list[dict] = []

    for name in ("SP500", "NDX"):
        label = DISPLAY_NAMES[name]
        deviation = row.get(f"{name}_vs_ma50")
        if deviation is None or pd.isna(deviation):
            checks.append({"ok": None, "text": f"{label} 的 50 日均线还没有足够历史数据"})
        elif deviation >= 0:
            checks.append({"ok": True, "text": f"{label} 高于 50 日均线（+{deviation:.2f}%）"})
        else:
            checks.append({"ok": False, "text": f"{label} 跌破 50 日均线（{deviation:.2f}%）"})

    vix = row.get("VIX_close")
    if vix is not None and not pd.isna(vix):
        zone_text, _ = vix_zone(vix)
        if vix >= 25:
            checks.append({"ok": False, "text": f"VIX = {vix:.2f}，{zone_text}"})
        elif vix >= 20:
            checks.append({"ok": None, "text": f"VIX = {vix:.2f}，{zone_text}"})
        else:
            checks.append({"ok": True, "text": f"VIX = {vix:.2f}，{zone_text}"})

    vix_change = row.get("VIX_change_1d")
    if vix_change is not None and not pd.isna(vix_change) and vix_change >= 10:
        checks.append({"ok": False, "text": f"VIX 单日上涨 {vix_change:.2f}%，超过 10%"})

    for name in ("SP500", "NDX"):
        streak = row.get(f"{name}_down_streak")
        if streak is not None and not pd.isna(streak) and streak >= 3:
            checks.append({"ok": False, "text": f"{DISPLAY_NAMES[name]} 连续 {int(streak)} 日下跌"})

    for name in ("SP500", "NDX"):
        distance = row.get(f"{name}_dist_high")
        if distance is not None and not pd.isna(distance) and distance <= -5:
            checks.append({"ok": False, "text": f"{DISPLAY_NAMES[name]} 距 52 周高点 {distance:.2f}%，回撤超过 5%"})

    gap = row.get("gap_ndx_sp500")
    if gap is not None and not pd.isna(gap) and abs(gap) >= 2:
        leader = "科技股更强" if gap > 0 else "传统股更强"
        checks.append({"ok": None, "text": f"纳指与标普单日相差 {abs(gap):.2f} 个百分点（{leader}）"})

    return checks


def assess(daily: pd.DataFrame) -> dict:
    """最新一天的市场状态：等级 + 风险评分 + 评分构成 + ✓/⚠ 清单。"""
    if daily.empty:
        return {
            "state": "neutral",
            "score": 0,
            "parts": [],
            "checks": [],
            "label": STATES["neutral"]["label"],
            "emoji": STATES["neutral"]["emoji"],
            "hint": "还没有数据",
        }

    row = daily.iloc[-1]
    parts = _score_parts(row)
    score = score_row(row)
    state = state_for(score)
    info = STATES[state]

    return {
        "state": state,
        "score": score,
        "parts": sorted(parts, key=lambda item: item["points"], reverse=True),
        "checks": _checks(row),
        "label": info["label"],
        "emoji": info["emoji"],
        "hint": info["hint"],
        "day": daily.index[-1].date(),
    }


def attention_items(result: dict) -> list[str]:
    """从清单里挑出需要关注的部分（⚠）。没有就是空列表。"""
    return [item["text"] for item in result.get("checks", []) if item["ok"] is False]


def daily_cards(daily: pd.DataFrame, days: int = 7) -> list[dict]:
    """历史日报卡片用的紧凑数据：最近 days 个交易日，每天一条。"""
    if daily.empty:
        return []

    cards: list[dict] = []
    for day, row in daily.tail(days).iloc[::-1].iterrows():
        parts = _score_parts(row)
        score = score_row(row)
        state = state_for(score)
        info = STATES[state]
        cards.append(
            {
                "day": day.date() if hasattr(day, "date") else day,
                "state": state,
                "label": info["label"],
                "emoji": info["emoji"],
                "color": info["color"],
                "score": score,
                "levels": {name: row.get(f"{name}_level") for name in config.SYMBOLS},
                "values": {
                    name: (row.get(f"{name}_close"), row.get(f"{name}_change_1d"))
                    for name in config.SYMBOLS
                },
                "warnings": len(attention_items({"checks": _checks(row)})),
            }
        )
    return cards


def vix_zone(vix) -> tuple[str, str]:
    """VIX 落在哪个区间：返回 (文字, 颜色)，给卡片上的小标签用。"""
    if vix is None or pd.isna(vix):
        return ("无数据", "gray")
    if vix < 15:
        return ("平静区 <15", "green")
    if vix < 20:
        return ("正常区 15-20", "gray")
    if vix < 25:
        return ("偏紧张 20-25", "orange")
    if vix < 35:
        return ("紧张区 25-35", "orange")
    return ("恐慌区 ≥35", "red")


if __name__ == "__main__":
    from src import history

    data = history.load_history()
    daily = build_daily_table(data)
    result = assess(daily)

    print(f"数据范围：{daily.index.min().date()} ~ {daily.index.max().date()}（{len(daily)} 个交易日）")
    print(f"\n市场状态：{result['emoji']} {result['label']}　风险评分 {result['score']} / 100　{result['hint']}")
    print("\n评分构成：")
    for item in result["parts"] or [{"points": 0, "text": "所有指标都在正常范围"}]:
        print(f"    +{item['points']:>2}  {item['text']}")
    print("\n✓/⚠ 清单：")
    for item in result["checks"]:
        mark = "✓" if item["ok"] else ("⚠" if item["ok"] is False else "·")
        print(f"    {mark} {item['text']}")
    print("\n最近 5 天的历史卡片：")
    for card in daily_cards(daily, days=5):
        print(f"    {card['day']}  {card['emoji']} {card['label']}  评分 {card['score']:>3}  异常 {card['warnings']} 条")
