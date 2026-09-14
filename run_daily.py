"""每日运行的入口（总指挥）。

用法：
    cd F:\\codex\\2026-09-14\\new-chat-4\\outputs\\us-market-monitor
    python run_daily.py

它自己不实现任何业务逻辑，只按固定顺序调用四层：

    [1/4] src.fetch     取回三个指数的日线（取不到的用本地缓存兜底）
    [2/4] src.metrics   算出涨跌幅、均线、VIX 指标
    [3/4] src.signals   按阈值判断 正常 / 关注 / 警报
    [4/4] src.report    生成 reports\\YYYY-MM-DD.md 并打印到终端

退出码：0 = 正常；1 = 一个标的数据都没拿到（以后挂到定时任务上，靠它判断有没有出问题）
"""

import sys

from src import fetch, metrics, report, signals

import config


def main() -> int:
    # ---------- 1. 取数 ----------
    print("[1/4] 取数 ...")
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
    print("[2/4] 算指标 ...")
    table = metrics.build_metrics(prices)

    # ---------- 3. 判断异常 ----------
    print("[3/4] 判断异常 ...")
    verdicts = signals.evaluate_all(table)

    # ---------- 4. 出报告 ----------
    # 一个数据都没拿到时，不写文件——否则会把当天已经生成的好报告覆盖成一份全是 "--" 的废纸
    if not prices:
        print("[4/4] 生成日报 ... 跳过")
        print("[错误] 今天一个标的数据都没拿到：网络不通，本地也没有缓存。")
        print("       先检查网络；如果只是临时故障，稍后重跑一次即可。")
        print("       为避免覆盖当天已有的报告，这次不写文件。")
        return 1

    print("[4/4] 生成日报 ...\n")
    note = f"以下标的用的是本地缓存、不是最新数据：{'、'.join(from_cache)}" if from_cache else None
    text = report.render_markdown(table, verdicts, data_note=note)
    report.print_console(text)
    path = report.save_report(text)
    print(f"\n已写入：{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
