"""输出层：把指标和结论排成一份 Markdown 日报。

职责
    只做展示。不算数字、不做判断、不上网。
    输入是 metrics 的指标表和 signals 的结论，输出是一份人看得懂的日报。

日报的结构（固定几段，方便你每天用同样的眼光扫一遍）
    # 标题 + 整体结论
    ## 关键数字        表格：收盘 / 单日 / 5 日 / 20 日 / MA20 / 相对 MA20 / 结论
    ## 异常与关注      只列出"关注"和"警报"的标的，以及具体理由
    ## 走势图          引用 chart.py 生成的 PNG（历史数据不够两天时这一段不出现）
    ## 数据说明        数据日期、样本数、生成时间、数据来源

对外提供的函数
    render_markdown(table, verdicts)   拼出日报正文（字符串）
    save_report(text)                  写入 reports\\YYYY-MM-DD.md
    print_console(text)                同时打印到终端

单独测试本文件：
    cd F:\\codex\\2026-09-14\\new-chat-4\\outputs\\us-market-monitor
    python -m src.report
"""

import pandas as pd

import config
from src import signals

LEVEL_LABELS = signals.LEVEL_LABELS
LEVEL_ORDER = signals.LEVEL_ORDER


def _num(value, spec: str = ",.2f") -> str:
    """数字转文本；空值显示成 --，免得表格里出现 nan。"""
    if value is None or pd.isna(value):
        return "--"
    return format(value, spec)


def _pct(value) -> str:
    """涨跌幅转文本，一定带正负号。"""
    if value is None or pd.isna(value):
        return "--"
    return f"{value:+.2f}%"


def _count_levels(verdicts: dict[str, dict]) -> dict[str, int]:
    counts = {"normal": 0, "watch": 0, "alert": 0}
    for verdict in verdicts.values():
        counts[verdict["level"]] += 1
    return counts


def render_markdown(
    table: pd.DataFrame,
    verdicts: dict[str, dict],
    today=None,
    data_note: str | None = None,
    chart_file: str | None = None,
) -> str:
    """拼出日报正文。

    table    metrics.build_metrics() 的输出
    verdicts signals.evaluate_all() 的输出
    today    报告日期，默认取 config.TIMEZONE 下的今天（测试时可以传进来）
    data_note 关于数据本身的提醒，比如"这次用的是本地缓存、不是最新数据"。
              只要不是最新数据，就一定要写出来——报告宁可难看，不能骗人。
    chart_file 走势图的文件名（和日报放在同一个目录，所以用相对路径引用）。
              传 None 就跳过走势图那一段。
    """
    report_day = today or config.today()
    counts = _count_levels(verdicts)
    overall = signals.overall_level(verdicts)

    lines: list[str] = []

    # ---------- 标题与整体结论 ----------
    lines.append(f"# {config.REPORT_TITLE} · {report_day}")
    lines.append("")
    lines.append(
        f"**整体结论：{LEVEL_LABELS[overall]}**"
        f"（警报 {counts['alert']} · 关注 {counts['watch']} · 正常 {counts['normal']}）"
    )
    lines.append("")

    # ---------- 关键数字 ----------
    lines.append("## 关键数字")
    lines.append("")
    lines.append("| 标的 | 收盘 | 单日 | 5 日 | 20 日 | MA20 | 相对 MA20 | 结论 |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |")

    for name, verdict in verdicts.items():
        row = table.loc[name] if name in table.index else None
        if row is None:
            # 今天没取到这个标的的数据，如实留空
            lines.append(f"| {name} | -- | -- | -- | -- | -- | -- | {LEVEL_LABELS[verdict['level']]} |")
            continue
        lines.append(
            f"| {name} | {_num(row.get('close'))} | {_pct(row.get('change_1d'))} "
            f"| {_pct(row.get('change_5d'))} | {_pct(row.get('change_20d'))} "
            f"| {_num(row.get('ma20'))} | {_pct(row.get('close_vs_ma20'))} "
            f"| {LEVEL_LABELS[verdict['level']]} |"
        )
    lines.append("")

    # ---------- 异常与关注 ----------
    lines.append("## 异常与关注")
    lines.append("")

    flagged = [
        (name, verdict)
        for name, verdict in verdicts.items()
        if verdict["level"] != "normal"
    ]
    if not flagged:
        lines.append("今天没有异常：所有标的都在正常范围内。")
    else:
        # 严重的排在前面，扫一眼就知道该先看哪个
        flagged.sort(key=lambda item: LEVEL_ORDER[item[1]["level"]], reverse=True)
        for name, verdict in flagged:
            lines.append(f"- **{name}（{LEVEL_LABELS[verdict['level']]}）**")
            for reason in verdict["reasons"]:
                lines.append(f"  - {reason}")
    lines.append("")

    # ---------- 走势图 ----------
    if chart_file:
        lines.append("## 走势图")
        lines.append("")
        lines.append(f"![最近走势]({chart_file})")
        lines.append("")

    # ---------- 数据说明 ----------
    lines.append("## 数据说明")
    lines.append("")
    lines.append(f"- 数据来源：{config.DATA_SOURCE_NOTE}")

    if data_note:
        lines.append(f"- **注意**：{data_note}")

    if not table.empty and "last_date" in table.columns:
        dates = sorted({str(value) for value in table["last_date"].dropna()})
        lines.append(f"- 数据日期：{'、'.join(dates) if dates else '--'}")
    else:
        lines.append("- 数据日期：--（今天没有取到任何数据）")

    if not table.empty and "trading_days" in table.columns:
        sample = int(table["trading_days"].min())
        lines.append(f"- 参与计算的样本：{sample} 个交易日")

    lines.append(f"- 报告生成时间：{config.now().strftime('%Y-%m-%d %H:%M')}（{config.TIMEZONE}）")
    lines.append("")
    lines.append("> 本报告由 us-market-monitor 自动生成，仅为数据记录，不构成任何投资建议。")

    return "\n".join(lines)


def save_report(text: str, today=None):
    """把日报写入 reports\\YYYY-MM-DD.md，返回文件路径。

    文件名里的日期是**交易日**（和历史表、走势图统一口径），不是运行日期。
    同一个交易日重复运行会覆盖同名文件——一天一份，重跑一次就刷新一次。
    """
    report_day = today or config.today()
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = config.REPORT_DIR / f"{report_day}.md"
    path.write_text(text, encoding="utf-8")
    return path


def print_console(text: str) -> None:
    """把日报打印到终端，不想开文件时直接看。"""
    print(text)


if __name__ == "__main__":
    from src import fetch, metrics  # 自测时才需要联网

    print("1) 取数 ...")
    prices = fetch.fetch_all()

    print("2) 算指标 ...")
    table = metrics.build_metrics(prices)

    print("3) 判断异常 ...")
    verdicts = signals.evaluate_all(table)

    print("4) 生成日报 ...\n")
    text = render_markdown(table, verdicts)
    print_console(text)

    print(f"\n已写入：{save_report(text)}")
