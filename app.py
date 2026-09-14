"""Streamlit 网页：把 data\\history.csv 里的历史做成一个能点的页面。

用法：
    cd F:\\codex\\2026-09-14\\new-chat-4\\outputs\\us-market-monitor
    streamlit run app.py
    （浏览器会自动打开 http://localhost:8501，关掉终端里的进程就停止了）

页面有五块：
    顶部结论卡片   三个标的的最新收盘、单日涨跌、结论
    走势           可选时间窗口，一个标的一个标签页，另加一个"标普 vs 纳指"对比
    历史日报       列出 reports\\ 下的日报，选一天看（含走势图）
    原始数据       历史表的最后 20 行
    侧边栏         一个"立即更新"按钮 + 上次运行的输出

它只做展示：读 history.csv 和 reports\\*.md，不算指标、不下判断。
唯一的例外是"立即更新"按钮——它直接调用 run_daily.main()，复用同一条流水线，
而不是在网页里另写一套取数逻辑。这样网页和定时任务看到的永远是同一份数据。

注意：这个文件是脚本不是库，所以结尾直接调用 main()，没有 if __name__ 那层保护。
"""

import contextlib
import io

import pandas as pd
import streamlit as st

import config
import run_daily
from src import history, signals

WINDOW_OPTIONS = {
    "最近 30 个交易日": 30,
    "最近 90 个交易日": 90,
    "最近 250 个交易日（约一年）": 250,
}
LEVEL_LABELS = signals.LEVEL_LABELS


def level_label(row: pd.Series, name: str) -> str:
    """把 level 的英文键翻成中文；取不到就显示一个短横。"""
    value = row.get(f"{name}_level")
    if isinstance(value, str):
        return LEVEL_LABELS.get(value, value)
    return "—"


def show_sidebar(data: pd.DataFrame) -> None:
    """侧边栏：手动更新按钮 + 数据说明。"""
    with st.sidebar:
        st.header("操作")
        if st.button("立即更新", type="primary"):
            with st.spinner("正在取数、算指标、判异常、出日报 ..."):
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    code = run_daily.main()
            st.session_state["run_log"] = buffer.getvalue()
            st.session_state["run_code"] = code
            st.rerun()

        code = st.session_state.get("run_code")
        if code == 0:
            st.success("更新完成")
        elif code is not None:
            st.error("没拿到数据（退出码 1），看下面的输出")

        log = st.session_state.get("run_log")
        if log:
            with st.expander("上次更新的输出", expanded=False):
                st.code(log, language="text")

        st.divider()
        st.header("数据")
        st.caption(f"历史表：data/history.csv（{len(data)} 行）")
        if not data.empty:
            st.caption(f"最新交易日：{data.index.max().date()}")
        st.caption(f"数据源：{config.DATA_SOURCE_NOTE}")
        st.caption("网页只负责展示；每天的数据由 Windows 定时任务更新。")


def main() -> None:
    st.set_page_config(page_title="美股市场监测", page_icon="📈", layout="wide")
    st.title("美股市场监测")

    data = history.load_history()
    show_sidebar(data)

    if data.empty:
        st.warning("还没有历史数据。点左边的「立即更新」跑一次，或者在终端运行 python run_daily.py。")
        return

    latest = data.iloc[-1]
    st.caption(
        f"最新交易日 {data.index.max().date()}　·　"
        f"共 {len(data)} 个交易日　·　数据源：Yahoo Finance 日线"
    )

    # ---------- 结论卡片 ----------
    cards = st.columns(len(config.SYMBOLS))
    for card, name in zip(cards, config.SYMBOLS):
        close = latest.get(f"{name}_close")
        change = latest.get(f"{name}_change_1d")
        card.metric(
            label=f"{name}　{level_label(latest, name)}",
            value="--" if pd.isna(close) else f"{close:,.2f}",
            delta=None if pd.isna(change) else f"{change:+.2f}%",
            # VIX 涨是坏事，颜色反过来，免得"涨了显绿"让人误读
            delta_color="inverse" if name == "VIX" else "normal",
        )

    # ---------- 走势 ----------
    st.subheader("走势")
    window = st.radio("看多长时间", list(WINDOW_OPTIONS), index=1, horizontal=True)
    recent = data.tail(WINDOW_OPTIONS[window])

    tabs = st.tabs([*config.SYMBOLS, "标普 vs 纳指"])
    for tab, name in zip(tabs, config.SYMBOLS):
        with tab:
            column = f"{name}_close"
            series = recent[column].dropna() if column in recent.columns else pd.Series(dtype=float)
            if series.empty:
                st.info("这段时间没有数据。")
                continue
            st.line_chart(series, height=280)
            st.caption(
                f"区间最高 {series.max():,.2f}　最低 {series.min():,.2f}　"
                f"区间涨跌 {(series.iloc[-1] / series.iloc[0] - 1) * 100:+.2f}%"
            )

    with tabs[-1]:
        pair = [f"{name}_close" for name in ("SP500", "NDX") if f"{name}_close" in recent.columns]
        if len(pair) == 2:
            base = recent[pair].dropna()
            st.line_chart(base / base.iloc[0] * 100, height=280)
            st.caption("把区间起点都当成 100，两条线才能放在一起比。VIX 不参与——它的量级和指数完全不同。")
        else:
            st.info("数据不够，画不了对比图。")

    # ---------- 历史日报 ----------
    st.subheader("历史日报")
    reports = sorted(config.REPORT_DIR.glob("*.md"), reverse=True)
    if not reports:
        st.info("还没有生成过日报。")
    else:
        chosen = st.selectbox("选一天看", reports, format_func=lambda path: path.stem)
        body = chosen.read_text(encoding="utf-8")
        # 报告里的图片写的是相对路径，在网页里会 404。
        # 所以把那一行去掉，改用 st.image 直接显示本机的图片文件。
        body = "\n".join(
            line for line in body.splitlines() if not line.strip().startswith("![")
        )
        st.markdown(body)
        picture = chosen.with_suffix(".png")
        if picture.exists():
            st.image(str(picture), caption=f"{chosen.stem} 走势图")

    # ---------- 原始数据 ----------
    with st.expander("原始数据（历史表最后 20 行）"):
        st.dataframe(data.tail(20))


main()
