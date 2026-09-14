"""输出层：把指标和结论排成一份 Markdown 日报。

职责
    只做展示。不算数字、不做判断、不上网。
    输入是 metrics 的指标表和 signals 的结论，输出是一份可读的日报。

计划实现的函数（下一步再写）
    render_markdown(metrics, signals, config, today) -> str
        拼出日报正文：总体结论、三个标的一行一个、异常理由列表。
    save_report(text: str, config, today) -> pathlib.Path
        写入 reports\\YYYY-MM-DD.md。
    print_console(text: str) -> None
        同时在终端打印，方便直接在命令行里看。

日报大致长这样（先定下结构，代码后写）
    # 美股市场日报 2026-09-14
    ## 一句话总结     今天 1 个警报、1 个关注
    ## 关键数字       表格：收盘价 / 单日 / 5日 / 相对 MA20
    ## 异常说明       VIX 单日 +21.3%，超过 20% 阈值
    ## 数据说明       数据日期、来源、是否有缺失
"""
