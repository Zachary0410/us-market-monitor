"""判断层：按阈值把指标翻译成"正常 / 关注 / 警报"。

职责
    只做比较和推理。不上网、不算指标、不排版。
    输入是 metrics 给的指标表，输出是每个标的的结论 + 理由。

三档结论
    normal   正常
    watch    关注——单项指标越线，或者数据不全
    alert    警报——VIX 处于恐慌区、单日剧烈波动这类明显异常

判断规则（阈值全部在 config.py 里，改阈值只改那一个文件）
    1. 数据完整性   指标表里缺标的，或收盘价/涨跌幅是 NaN
    2. 单日涨跌幅   绝对值越过 config.DAILY_MOVE_PCT
    3. 高位水平     越过 config.LEVEL_ABOVE（目前只有 VIX 用）
    4. 偏离 MA20    绝对值越过 config.MA20_DEVIATION_PCT
    5. 风格分化     纳指与标普单日涨跌幅之差越过 config.NDX_SP500_GAP_PCT

    每条规则命中都会生成一句人能看懂的理由，report.py 会原样展示。
    "为什么报警"比"报警了"重要得多——没有理由的警报，一周后你就看不懂了。

对外提供的函数
    evaluate(name, row)      判断单个标的
    evaluate_all(table)      判断整张表，返回 {名字: 结论}
    overall_level(verdicts)  总体档位（取最严重的那个）

单独测试本文件：
    cd F:\\codex\\2026-09-14\\new-chat-4\\outputs\\us-market-monitor
    python -m src.signals
"""

import pandas as pd

import config

# 三档结论的中文名，report.py 也会 import 这个
LEVEL_LABELS = {"normal": "正常", "watch": "关注", "alert": "警报"}

# 谁更严重：数字越大越严重，用来比较档位
LEVEL_ORDER = {"normal": 0, "watch": 1, "alert": 2}

# 判断"数据够不够"时要检查的列
REQUIRED_METRICS = {"close": "收盘价", "change_1d": "单日涨跌幅"}


def _worst(levels: list[str]) -> str:
    """取一组档位里最严重的那个；一个都没有就算正常。"""
    if not levels:
        return "normal"
    return max(levels, key=lambda level: LEVEL_ORDER[level])


def _hit_level(value, thresholds: dict) -> str | None:
    """把数值和门槛比一比：越过警报线返回 "alert"，越过关注线返回 "watch"，都没越过返回 None。

    比较用的是 >=，并且只看大小。需要"两头都算异常"的规则，调用方自己传 abs(...) 进来；
    VIX 水平这种"越高越危险"的规则就直接传原值。
    """
    if value is None or pd.isna(value):
        return None
    if "alert" in thresholds and value >= thresholds["alert"]:
        return "alert"
    if "watch" in thresholds and value >= thresholds["watch"]:
        return "watch"
    return None


def evaluate(name: str, row: pd.Series) -> dict:
    """判断单个标的，返回 {"level": ..., "reasons": [...]}。"""
    hits: list[tuple[str, str]] = []

    close = row.get("close")
    change = row.get("change_1d")
    deviation = row.get("close_vs_ma20")

    # 规则 1：数据完整性。数据缺了不能假装没看见，但也不该直接报"警报"。
    missing = [
        label
        for column, label in REQUIRED_METRICS.items()
        if column not in row.index or pd.isna(row.get(column))
    ]
    if missing:
        hits.append(("watch", f"数据不完整：{'、'.join(missing)}缺失，今天只能部分判断"))

    # 规则 2：单日涨跌幅
    if change is not None and not pd.isna(change):
        limits = config.DAILY_MOVE_PCT.get(name)
        if limits:
            level = _hit_level(abs(change), limits)
            if level:
                direction = "上涨" if change > 0 else "下跌"
                hits.append(
                    (
                        level,
                        f"单日{direction} {abs(change):.2f}%，"
                        f"越过 {limits[level]:.1f}% 的{LEVEL_LABELS[level]}线",
                    )
                )

    # 规则 3：高位水平（VIX 越高代表市场越紧张）
    if close is not None and not pd.isna(close):
        limits = config.LEVEL_ABOVE.get(name)
        if limits:
            level = _hit_level(close, limits)
            if level:
                hits.append(
                    (
                        level,
                        f"收于 {close:.2f}，高于 {limits[level]:.0f} 的{LEVEL_LABELS[level]}线"
                        f"（市场紧张度偏高）",
                    )
                )

    # 规则 4：偏离 MA20
    if deviation is not None and not pd.isna(deviation):
        limits = config.MA20_DEVIATION_PCT.get(name)
        if limits:
            level = _hit_level(abs(deviation), limits)
            if level:
                side = "高于" if deviation > 0 else "低于"
                hits.append(
                    (
                        level,
                        f"收盘价{side} MA20 {abs(deviation):.2f}%，"
                        f"越过 {limits[level]:.1f}% 的{LEVEL_LABELS[level]}线",
                    )
                )

    return {
        "level": _worst([hit[0] for hit in hits]),
        "reasons": [hit[1] for hit in hits],
    }


def _check_divergence(verdicts: dict[str, dict], table: pd.DataFrame) -> None:
    """规则 5：纳指与标普的单日涨跌幅差多少算"风格分化"。

    这条规则说的是两个标的之间的关系，不适合挂在标的上，
    所以统一记在 NDX 那一行，理由里写清楚是和谁比的。
    """
    if "SP500" not in table.index or "NDX" not in table.index:
        return

    sp500_change = table.loc["SP500", "change_1d"]
    ndx_change = table.loc["NDX", "change_1d"]
    if pd.isna(sp500_change) or pd.isna(ndx_change):
        return

    gap = float(ndx_change) - float(sp500_change)
    level = _hit_level(abs(gap), config.NDX_SP500_GAP_PCT)
    if not level:
        return

    leader = "科技股更强" if gap > 0 else "传统股更强"
    verdict = verdicts["NDX"]
    verdict["level"] = _worst([verdict["level"], level])
    verdict["reasons"].append(
        f"纳指与标普单日涨跌幅相差 {abs(gap):.2f} 个百分点（{leader}），"
        f"越过 {config.NDX_SP500_GAP_PCT[level]:.1f} 的{LEVEL_LABELS[level]}线"
    )


def evaluate_all(table: pd.DataFrame, symbols: dict | None = None) -> dict[str, dict]:
    """判断整张指标表，返回 {名字: {"level": ..., "reasons": [...]}}。

    注意这里遍历的是 config.SYMBOLS，而不是指标表的行——这样"今天没取到数据"
    的标的也会出现在结果里，日报才能如实写上"今天缺了谁"。
    """
    names = list(symbols) if symbols is not None else list(config.SYMBOLS)
    verdicts: dict[str, dict] = {}

    for name in names:
        if name not in table.index:
            verdicts[name] = {
                "level": "watch",
                "reasons": [f"今天没有取到 {name} 的数据，未参与判断"],
            }
            continue
        verdicts[name] = evaluate(name, table.loc[name])

    _check_divergence(verdicts, table)
    return verdicts


def overall_level(verdicts: dict[str, dict]) -> str:
    """所有标的里最严重的那一档，日报的"一句话总结"用它。"""
    return _worst([verdict["level"] for verdict in verdicts.values()])


if __name__ == "__main__":
    from src import fetch, metrics  # 自测时才需要联网

    print("1) 取数 ...")
    prices = fetch.fetch_all()

    print("2) 算指标 ...\n")
    table = metrics.build_metrics(prices)

    print("3) 判断异常 ...\n")
    verdicts = evaluate_all(table)

    print(f"整体结论：{LEVEL_LABELS[overall_level(verdicts)]}\n")
    for name, verdict in verdicts.items():
        print(f"{name}  ->  {LEVEL_LABELS[verdict['level']]}")
        if not verdict["reasons"]:
            print("    （没有触发任何规则）")
        for reason in verdict["reasons"]:
            print(f"    - {reason}")
