"""每日运行的入口（总指挥）。

用法：
    cd F:\\codex\\2026-09-14\\new-chat-4\\outputs\\us-market-monitor
    python run_daily.py

它自己不实现任何业务逻辑，只按固定顺序调用五层：

    [1/5] src.fetch     取回三个指数的日线（取不到的用本地缓存兜底）
    [2/5] src.metrics   算出涨跌幅、均线、VIX 指标
    [3/5] src.signals   按阈值判断 正常 / 关注 / 警报
    [4/5] src.history   把今天这一行追加进 data\\history.csv
    [5/5] src.chart + src.report   画出走势图，生成 reports\\YYYY-MM-DD.md 并打印

退出码：0 = 正常；1 = 一个标的数据都没拿到（以后挂到定时任务上，靠它判断有没有出问题）
"""

import sys

from src import chart, fetch, history, metrics, report, signals

import config


def main() -> int:
    # ---------- 1. 取数 ----------
    print("[1/5] 取数 ...")
    prices: dict = {}
    try:
        prices = fetch.fetch_all()
        for name, frame in prices.items():
            fetch.save_cache(name, frame)   # 顺手存一份，下次网络不通就有得用
    except fetch.FetchError as exc:
        print(f"      取数失败：{exc}")

    # 没取到的标的，用本地缓存兜底，并把"谁用了缓存"记下来
    from_cache: list[str] = []
    for name in config.SYMBOLS:
        if name in prices:
            continue
        cached = fetch.load_cache(name)
        if cached is not None and not cached.empty:
            prices[name] = cached
            from_cache.append(name)

    if prices:
        print(f"      拿到 {len(prices)} 个标的：{'、'.join(prices)}")
    if from_cache:
        print(f"      其中以下标的是本地缓存、不是最新数据：{'、'.join(from_cache)}")

    # ---------- 2. 算指标 ----------
    print("[2/5] 算指标 ...")
    table = metrics.build_metrics(prices)

    # ---------- 3. 判断异常 ----------
    print("[3/5] 判断异常 ...")
    verdicts = signals.evaluate_all(table)

    # 一个数据都没拿到时，什么都别写。
    # 否则会在历史表里留下一天的空数据，还会把当天已经生成的好报告覆盖成一份全是 "--" 的废纸。
    if not prices:
        print("[4/5] 存历史数据 ... 跳过")
        print("[5/5] 生成日报 ... 跳过")
        print("[错误] 今天一个标的数据都没拿到：网络不通，本地也没有缓存。")
        print("       先检查网络；如果只是临时故障，稍后重跑一次即可。")
        return 1

    # ---------- 4. 存历史 ----------
    print("[4/5] 存历史数据 ...")
    try:
        if history.load_history().empty:
            filled = history.backfill(prices, days=config.HISTORY_DAYS)
            print(f"      第一次运行，先用日线把过去 {filled} 个交易日补齐")
        saved = history.append_snapshot(table, verdicts)
        print(f"      已累计 {len(history.load_history())} 个交易日 -> {saved.name}")
    except OSError as exc:
        print(f"      写历史失败，继续出报告：{exc}")

    # ---------- 5. 出报告 ----------
    print("[5/5] 生成日报 ...\n")

    chart_file = None
    try:
        chart_file = chart.render_chart(history.load_history()).name
        print(f"      走势图：{chart_file}")
    except Exception as exc:  # 画图只是锦上添花，不能让它拖垮整份日报
        print(f"      跳过走势图：{exc}")

    note = f"以下标的用的是本地缓存、不是最新数据：{'、'.join(from_cache)}" if from_cache else None
    text = report.render_markdown(table, verdicts, data_note=note, chart_file=chart_file)
    report.print_console(text)
    path = report.save_report(text)
    print(f"\n已写入：{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
