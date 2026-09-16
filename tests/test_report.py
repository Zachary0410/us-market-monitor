"""输出层测试：报告结构、日期口径、缺数据时的表现。"""

from datetime import date

from src import report, signals


def test_render_markdown_has_all_sections(metrics_table, verdicts):
    text = report.render_markdown(metrics_table, verdicts, today=date(2026, 9, 14))
    assert text.startswith("# 美股市场日报 · 2026-09-14")
    for section in ("## 关键数字", "## 异常与关注", "## 数据说明"):
        assert section in text
    assert "| SP500 |" in text


def test_render_markdown_mentions_cache_and_chart(metrics_table, verdicts):
    text = report.render_markdown(
        metrics_table,
        verdicts,
        today=date(2026, 9, 14),
        data_note="这次用的是本地缓存",
        chart_file="2026-09-14.png",
    )
    assert "这次用的是本地缓存" in text
    assert "![最近走势](2026-09-14.png)" in text


def test_render_markdown_reports_missing_symbol(metrics_table):
    """缺了标的也要如实写出来，而不是当它不存在。"""
    partial = metrics_table.drop(index=["VIX"])
    verdicts = signals.evaluate_all(partial)
    text = report.render_markdown(partial, verdicts, today=date(2026, 9, 14))
    assert "没有取到 VIX 的数据" in text
    assert "| VIX | -- |" in text


def test_save_report_uses_trading_day_name():
    path = report.save_report("内容", today=date(2026, 9, 14))
    assert path.name == "2026-09-14.md"
    assert path.read_text(encoding="utf-8") == "内容"
