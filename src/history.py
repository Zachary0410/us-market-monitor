"""历史数据层：每天把关键数字攒进 data\\history.csv。

职责
    日报是"今天的快照"，历史表才是能看趋势的东西。
    这一层只做存取：不算指标、不下判断、不排版。

文件格式（宽表，一天一行，用 Excel 直接打开就能看）
    date | SP500_close | SP500_change_1d | SP500_close_vs_ma20 | SP500_level | NDX_... | VIX_...

    - date 用的是"数据日期"，也就是美东收盘的那一天，不是运行日期。
      因为程序在香港早上跑，比美东晚一天——要是用运行日期，图上会出现周六
      这种根本不是交易日的点。
    - 列名按 config.SYMBOLS 自动生成：以后加标的，这个文件不用改。
    - level 列存的是 normal / watch / alert 三个英文键（中文名在 signals.LEVEL_LABELS 里）。
    - 同一个交易日重复运行会覆盖那一行，不会堆出重复数据。

对外提供的函数
    append_snapshot(table, verdicts)   写入今天这一行，返回文件路径
    backfill(prices, days)             用日线把过去几天的数字补齐（第一次运行时用）
    load_history()                     读回全部历史，没有文件就返回空表
    fingerprint()                      历史表的"指纹"，网页拿它当缓存钥匙

单独测试本文件：
    cd F:\\codex\\2026-09-14\\new-chat-4\\outputs\\us-market-monitor
    python -m src.history
"""

import pandas as pd

import config

# 每个标的存哪几列（和日报里那张表保持一致）
SNAPSHOT_COLUMNS = ["close", "change_1d", "close_vs_ma20"]


def history_path():
    """历史表的位置：data\\history.csv"""
    return config.DATA_DIR / "history.csv"


def _value(table: pd.DataFrame, name: str, column: str) -> float:
    """从指标表里安全地取一个数；取不到就返回 NaN，不抛异常。"""
    if name not in table.index or column not in table.columns:
        return float("nan")
    value = table.loc[name, column]
    return float("nan") if pd.isna(value) else float(value)


def _build_row(table: pd.DataFrame, verdicts: dict[str, dict], day) -> dict:
    """把"今天"整理成一行：每个标的 3 个数字 + 1 个结论。"""
    row: dict = {}
    for name, verdict in verdicts.items():
        row[f"{name}_level"] = verdict["level"]
        for column in SNAPSHOT_COLUMNS:
            row[f"{name}_{column}"] = _value(table, name, column)
    return row


def load_history() -> pd.DataFrame:
    """读回全部历史。文件还不存在时返回空表，这不算错误。"""
    path = history_path()
    if not path.exists():
        return pd.DataFrame()

    frame = pd.read_csv(path, index_col="date", parse_dates=True)
    frame.index.name = "date"
    return frame.sort_index()


def fingerprint() -> tuple[float, int]:
    """历史表的"指纹"：文件最后修改时间 + 大小。

    用途：网页把它当作缓存的钥匙。文件一被重写（定时任务跑完、或你手动跑
    run_daily.bat），指纹就变了，缓存自动失效，页面立刻能看到新数据——
    不用等缓存过期，也不用去点"立即更新"。

    文件不存在时返回 (0.0, 0)。这也是一个有效的指纹，含义是"还没有数据"。
    """
    path = history_path()
    if not path.exists():
        return (0.0, 0)

    info = path.stat()
    return (info.st_mtime, info.st_size)


def _save(new_rows: pd.DataFrame):
    """把新行合并进历史表并落盘。同一天的旧行会被覆盖，所以一天永远只有一行。"""
    history = load_history()
    if not history.empty:
        history = history[~history.index.isin(new_rows.index)]

    # concat 会自动对齐列：以后加了新标的，旧行对应位置是空值，不会报错
    combined = pd.concat([history, new_rows]).sort_index()

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = history_path()
    combined.to_csv(path, encoding="utf-8-sig")
    return path


def _snapshot_day(table: pd.DataFrame, fallback):
    """这一行该记到哪个交易日。

    优先用指标表里的 last_date（数据日期）；表是空的才退回到运行日期。
    """
    if "last_date" in table.columns:
        dates = table["last_date"].dropna()
        if not dates.empty:
            return pd.Timestamp(max(dates))
    return pd.Timestamp(fallback)


def append_snapshot(table: pd.DataFrame, verdicts: dict[str, dict], today=None):
    """把最新一天的快照写进历史表（同一个交易日重复运行会覆盖），返回文件路径。"""
    day = _snapshot_day(table, today or config.today())
    new_row = pd.DataFrame([_build_row(table, verdicts, day)], index=[day])
    new_row.index.name = "date"
    return _save(new_row)


def backfill(prices: dict[str, pd.DataFrame], days: int = 90) -> int:
    """用刚取回来的日线数据，把过去 days 个交易日的数字补齐，返回补了多少天。

    为什么需要它：如果只从今天开始攒，你得等两三个月才能看到一张像样的走势图。
    其实过去每一天的涨跌幅、均线、甚至当时的结论，都能从日线重新算出来。

    注意：这里用的是**现在**的规则和阈值去回填过去——所以历史结论反映的是
    "按今天的标准，那天算不算异常"。以后改了阈值，想重算就删掉 history.csv 再跑一次。
    """
    from src import metrics, signals  # 放在函数里，避免模块之间互相 import

    calendar = sorted({day for frame in prices.values() for day in frame.index})
    if not calendar:
        return 0

    rows = []

    for day in calendar[-days:]:
        table = metrics.build_metrics(prices, as_of=day)
        verdicts = signals.evaluate_all(table)
        rows.append(pd.DataFrame([_build_row(table, verdicts, day)], index=[day]))

    if not rows:
        return 0

    new_rows = pd.concat(rows).sort_index()
    new_rows.index.name = "date"
    _save(new_rows)
    return len(new_rows)


if __name__ == "__main__":
    from src import fetch, metrics, signals  # 自测时才需要联网

    print("1) 取数 ...")
    prices = fetch.fetch_all()

    print("2) 算指标 ...")
    table = metrics.build_metrics(prices)

    print("3) 判断异常 ...")
    verdicts = signals.evaluate_all(table)

    print("4) 写入历史表 ...")
    path = append_snapshot(table, verdicts)

    all_history = load_history()
    print(f"\n累计 {len(all_history)} 个交易日 -> {path}\n")
    print("最近 5 天：")
    print(all_history.tail(5).to_string())
