"""指标层：把"一堆日线"变成"几个关键数字"。

职责
    纯计算。不上网、不下判断、不排版。
    输入是 fetch 给出的 {名字: DataFrame}，输出是一张"每个指数一行"的指标表。

这一层**不**做的事
    不判断"超过 1.5% 算不算异常"——那是 signals.py 的事。
    这里只负责把数字算准、算齐，让下一层有东西可比。

指标定义（会决定输出表的列名，所以写在这里，不放 config）
    last_date        最新数据的日期
    trading_days     参与计算的有效交易日数
    close            最新收盘价
    change_1d        最近 1 个交易日涨跌幅（%）
    change_5d        最近 5 个交易日涨跌幅（%）
    change_20d       最近 20 个交易日涨跌幅（%）
    ma20 / ma50      最近 20 / 50 个交易日的收盘均线
    close_vs_ma20    收盘价比 MA20 高/低多少（%）

    为什么窗口数字不放 config：它们决定的是"列名"，属于指标定义；
    config 里放的是"多少算异常"这类阈值。两者性质不同，别混在一起。

单独测试本文件：
    cd F:\\codex\\2026-09-14\\new-chat-4\\outputs\\us-market-monitor
    python -m src.metrics
"""

import pandas as pd

# 观察窗口（交易日）。改这里就等于改指标定义，列名也会跟着变。
CHANGE_WINDOWS = {"change_1d": 1, "change_5d": 5, "change_20d": 20}
MA_WINDOWS = {"ma20": 20, "ma50": 50}

# 输出表的列顺序，也是交给 signals.py 的"数据合同"
METRIC_COLUMNS = [
    "last_date",
    "trading_days",
    "close",
    "change_1d",
    "change_5d",
    "change_20d",
    "ma20",
    "ma50",
    "close_vs_ma20",
]


def _ratio_pct(latest: float, base: float) -> float:
    """(latest / base - 1) * 100。base 无效时返回 NaN，而不是抛异常。

    为什么不抛异常：数据缺失很常见（停牌、新股），这里一抛，整份日报就没了。
    返回 NaN 之后由 signals.py 决定——它会把"数据不全"标成"关注"。
    """
    if base is None or pd.isna(base) or base == 0:
        return float("nan")
    return (latest / base - 1) * 100


def change_pct(closes: pd.Series, periods: int) -> float:
    """最近 periods 个交易日的涨跌幅（%）。样本不够返回 NaN。"""
    if len(closes) <= periods:
        return float("nan")
    return _ratio_pct(float(closes.iloc[-1]), float(closes.iloc[-1 - periods]))


def moving_average(closes: pd.Series, window: int) -> float:
    """最近 window 个交易日的收盘均线。样本不够返回 NaN。"""
    if len(closes) < window:
        return float("nan")
    return float(closes.tail(window).mean())


def build_metrics(prices: dict[str, pd.DataFrame], as_of=None) -> pd.DataFrame:
    """把 {名字: 日线 DataFrame} 合成一张指标表：每个标的一行。

    返回的 DataFrame：
        index  标的内部名字（SP500 / NDX / VIX）
        列     见 METRIC_COLUMNS

    as_of   只看这个日期（含）之前的数据。正常跑日报用默认的 None（看最新）。
            只有历史回填才会用到它——"假如那天就收工，当时的指标是多少"。
    """
    rows: dict[str, dict] = {}

    for name, frame in prices.items():
        if as_of is not None:
            frame = frame.loc[:as_of]

        closes = frame["close"].astype(float).dropna()
        if closes.empty:
            continue

        latest = float(closes.iloc[-1])
        ma20 = moving_average(closes, MA_WINDOWS["ma20"])
        ma50 = moving_average(closes, MA_WINDOWS["ma50"])

        row = {
            "last_date": frame.index[-1].date(),
            "trading_days": int(len(closes)),
            "close": latest,
            "ma20": ma20,
            "ma50": ma50,
            "close_vs_ma20": _ratio_pct(latest, ma20),
        }
        for column, window in CHANGE_WINDOWS.items():
            row[column] = change_pct(closes, window)

        rows[name] = row

    table = pd.DataFrame.from_dict(rows, orient="index")
    return table.reindex(columns=METRIC_COLUMNS)


def _fmt(value, spec: str = ",.2f") -> str:
    """自测用的显示工具：NaN 显示成 --，免得满屏 nan。"""
    if value is None or pd.isna(value):
        return "--"
    return format(value, spec)


if __name__ == "__main__":
    from src import fetch  # 自测时才需要联网，正常工作流程里由 run_daily.py 喂数据

    print("1) 取数 ...")
    prices = fetch.fetch_all()

    print("2) 算指标 ...\n")
    table = build_metrics(prices)

    for name, row in table.iterrows():
        print(f"{name}   数据日期 {row['last_date']}   样本 {int(row['trading_days'])} 个交易日")
        print(
            f"    收盘 {_fmt(row['close'], '>10,.2f')}"
            f"   单日 {_fmt(row['change_1d'], '+.2f')}%"
            f"   5日 {_fmt(row['change_5d'], '+.2f')}%"
            f"   20日 {_fmt(row['change_20d'], '+.2f')}%"
        )
        print(
            f"    MA20 {_fmt(row['ma20'], '>10,.2f')}"
            f"   MA50 {_fmt(row['ma50'], '>10,.2f')}"
            f"   相对 MA20 {_fmt(row['close_vs_ma20'], '+.2f')}%"
        )
        print()
