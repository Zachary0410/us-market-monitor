"""取数层：把"外部世界的数据"变成"项目内部统一的 DataFrame"。

职责
    请求数据 → 检查数据 → 整理成统一格式 → 存一份本地 CSV 缓存。
    除了这个文件，其它文件都不应该知道数据从哪来、原始格式长什么样。

数据源
    Yahoo Finance 的原始图表接口（免费、不需要 API key）：
    https://query1.finance.yahoo.com/v8/finance/chart/^GSPC?range=1y&interval=1d

    为什么不用 yfinance 库：实测在本机网络下 yfinance 会被 Yahoo 限流
    （YFRateLimitError），而上面这个原始接口是通的。

对外提供的函数
    fetch_index(symbol, days)   取单个指数的日线
    fetch_all(symbols, days)    批量取数，返回 {名字: DataFrame}
    save_cache(name, df)        把数据存成 data\\名字.csv
    load_cache(name)            读回缓存，没有缓存就返回 None

单独测试本文件（注意是 -m，不是直接跑文件）：
    cd F:\\codex\\2026-09-14\\new-chat-4\\outputs\\us-market-monitor
    python -m src.fetch
"""

import sys
import time

import pandas as pd
import requests

import config

# ---------- 常量 ----------
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# 不带 User-Agent 会被 Yahoo 直接拒绝，这是最常见的坑之一
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# 我们约定的列顺序，也是交给 metrics.py 的"数据合同"
COLUMNS = ["open", "high", "low", "close", "volume"]

MAX_ATTEMPTS = 3          # 网络抖动时最多试几次
RETRY_WAIT_SECONDS = 1.5


class FetchError(RuntimeError):
    """取数失败。消息里一定写清楚是哪个标的、为什么失败。"""


def _to_range(days: int) -> str:
    """把"想要多少个交易日"翻译成 Yahoo 接口认识的 range 参数。

    Yahoo 只认 5d / 1mo / 3mo / 6mo / 1y / 2y / 5y 这类固定档位，
    所以这里向上取一档，拿到数据后再精确截取需要的条数。
    """
    steps = ((5, "5d"), (22, "1mo"), (66, "3mo"), (130, "6mo"), (260, "1y"), (520, "2y"))
    for limit, value in steps:
        if days <= limit:
            return value
    return "5y"


def _to_trading_dates(timestamps) -> pd.DatetimeIndex:
    """把 Yahoo 返回的 Unix 时间戳转成"纽约当地的交易日"。

    美股开盘时间换算成纽约时间还是同一天，所以 normalize 到当天零点，
    再去掉时区信息，就得到干净好读的日期索引。
    """
    series = pd.to_datetime(pd.Series(timestamps), unit="s", utc=True)
    new_york = series.dt.tz_convert("America/New_York").dt.normalize().dt.tz_localize(None)
    return pd.DatetimeIndex(new_york)


def _drop_unfinished_session(frame: pd.DataFrame) -> pd.DataFrame:
    """丢掉"今天还没收盘"的那根日线。

    为什么需要这一步：美股盘前或盘中，Yahoo 有时已经返回当天的数据，而且各标的
    进度不一致——VIX 常常比股票指数更早更新。结果是三个标的混着两个日期，
    涨跌幅也会算错（比如 VIX 显示"一天涨 12%"，其实那根线还没走完）。

    规则很简单：美东时间还没过 16:15，当天那根日线一律不要。
    注意这对每天 06:00（香港）的定时任务没有任何影响——那时美东早就收盘了。
    """
    now_new_york = pd.Timestamp.now(tz="America/New_York")
    market_closed = (now_new_york.hour, now_new_york.minute) >= (16, 15)
    if market_closed:
        return frame

    today_new_york = now_new_york.normalize().tz_localize(None)
    return frame[frame.index < today_new_york]


def _request(symbol: str, days: int, timeout: int) -> dict:
    """真正发网络请求的地方，带简单重试。"""
    url = CHART_URL.format(symbol=symbol.replace("^", "%5E"))
    params = {"range": _to_range(days), "interval": "1d"}

    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=timeout)

            # 404 表示这个代码根本不存在，重试也没用，直接给出能看懂的提示
            if response.status_code == 404:
                raise FetchError(f"{symbol}: 数据源说找不到这个代码（404），检查 config.SYMBOLS 里的写法")

            response.raise_for_status()
            return response.json()

        except FetchError:
            raise                 # 原因已经说清楚了，不再重试
        except Exception as exc:  # 超时、连接失败、429、5xx 才值得再试
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_WAIT_SECONDS)

    raise FetchError(
        f"{symbol}: 请求失败（试了 {MAX_ATTEMPTS} 次，最后一次是 {type(last_error).__name__}: {last_error}）"
    )


def fetch_index(symbol: str, days: int = config.HISTORY_DAYS, timeout: int = config.REQUEST_TIMEOUT) -> pd.DataFrame:
    """取单个指数最近 days 个交易日的日线。

    返回的 DataFrame：
        index  日期（DatetimeIndex，从旧到新）
        列     open / high / low / close / volume
    """
    payload = _request(symbol, days, timeout)
    chart = payload.get("chart") or {}

    if chart.get("error"):
        raise FetchError(f"{symbol}: 数据源报错 -> {chart['error']}")

    results = chart.get("result") or []
    if not results:
        raise FetchError(f"{symbol}: 数据源没有返回任何结果（代码是不是写错了？）")

    result = results[0]
    timestamps = result.get("timestamp") or []
    if not timestamps:
        raise FetchError(f"{symbol}: 返回结果里没有时间戳")

    quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    data = {column: quotes.get(column, [None] * len(timestamps)) for column in COLUMNS}

    frame = pd.DataFrame(data, index=_to_trading_dates(timestamps))
    frame.index.name = "date"
    frame = frame.dropna(subset=["close"])               # 去掉停牌、数据缺失的行
    frame = frame[~frame.index.duplicated(keep="last")]  # 去掉重复日期
    frame = frame.sort_index()                           # 保证从旧到新
    frame = _drop_unfinished_session(frame)              # 丢掉还没收盘的今天

    if frame.empty:
        raise FetchError(f"{symbol}: 去掉空数据后一条都不剩")

    return frame.tail(days)[COLUMNS]


def fetch_all(symbols: dict[str, str] | None = None, days: int = config.HISTORY_DAYS) -> dict[str, pd.DataFrame]:
    """批量取数，返回 {内部名字: DataFrame}。

    个别标的失败不会让整个程序崩掉：能取到的照常返回，失败的会在终端提醒，
    这样日报里还能显示"哪个数据缺了"。只有全都失败才抛 FetchError。
    """
    targets = symbols if symbols is not None else config.SYMBOLS
    prices: dict[str, pd.DataFrame] = {}
    failures: list[str] = []

    for name, symbol in targets.items():
        try:
            prices[name] = fetch_index(symbol, days=days)
        except FetchError as exc:
            failures.append(str(exc))

    if failures:
        message = "；".join(failures)
        if not prices:
            raise FetchError(f"所有标的都取数失败 -> {message}")
        print(f"[警告] 有 {len(failures)} 个标的取数失败 -> {message}", file=sys.stderr)

    return prices


def cache_path(name: str):
    """缓存文件的完整路径：data\\名字.csv"""
    return config.DATA_DIR / f"{name}.csv"


def save_cache(name: str, frame: pd.DataFrame):
    """把取回来的数据存成 CSV，以后网络不通时还有得用。

    用 utf-8-sig 编码：这样直接用 Excel 打开不会乱码。
    """
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(name)
    frame.to_csv(path, encoding="utf-8-sig")
    return path


def load_cache(name: str) -> pd.DataFrame | None:
    """读回缓存。没有缓存就返回 None——这不算错误，交给调用方决定怎么办。"""
    path = cache_path(name)
    if not path.exists():
        return None

    frame = pd.read_csv(path, index_col="date", parse_dates=True)
    frame.index.name = "date"
    return frame[COLUMNS]


if __name__ == "__main__":
    # 自测：把三个指数的真实数据打出来，眼见为实
    print(f"正在从 Yahoo 取数（最近 {config.HISTORY_DAYS} 个交易日）...\n")
    prices = fetch_all()

    for name, frame in prices.items():
        latest = frame.iloc[-1]
        print(f"{name}  共 {len(frame)} 个交易日  最新 {frame.index[-1].date()}")
        print(
            f"      收盘 {latest['close']:>10,.2f}"
            f"   最高 {latest['high']:>10,.2f}"
            f"   最低 {latest['low']:>10,.2f}"
        )

    print("\n最近 3 天原始数据（这里用第一个标的做例子）：")
    print(next(iter(prices.values())).tail(3).to_string())

    print("\n写入缓存：")
    for name, frame in prices.items():
        print("   ", save_cache(name, frame))
