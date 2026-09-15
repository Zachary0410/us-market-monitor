"""Streamlit Dashboard：10 秒看清今天的市场。

用法：
    cd F:\\codex\\2026-09-14\\new-chat-4\\outputs\\us-market-monitor
    streamlit run app.py        （或者直接双击 run_web.bat）

页面从上到下按"每天要看的顺序"排：
    1. 顶部      标题 + 最新交易日 / 数据更新时间 + 立即更新
    2. KPI 卡片  标普 500 / 纳斯达克 100 / VIX：当前值、涨跌额、涨跌幅、5 日、20 日、迷你走势
    3. 市场状态  风险等级 + 风险评分 + 评分构成；右边是"今日需要关注"
    4. 趋势      1M / 3M / 1Y 区间，SP500 / NDX / VIX 切换，可叠加 MA20/50/200，鼠标悬停看数值
    5. 历史日报  每个交易日一张紧凑卡片，点"查看"才展开完整报告

数据约定
    页面只读 data\\history.csv 和 reports\\*。数据由 run_daily.py（或点"立即更新"）生产，
    这里不改动任何数据获取逻辑；市场状态和风险评分是 src\\market_state.py 现算的展示层结果，
    不写回文件、不影响日报流水线。
"""

import contextlib
import io
from datetime import datetime
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

import config
import run_daily
from src import history, market_state, signals

# ---------- 常量 ----------
CACHE_TTL = "30m"                 # 缓存的兜底寿命（本地靠文件指纹失效，云端靠它定期复查）
FRESH_DAYS = 4                    # 历史表超过这么多天就认为过期，自动重跑流水线
STALE_DAYS = 5                    # 超过这么多天就在页面上提醒"数据可能偏旧"

WINDOWS = {"1M": 21, "3M": 63, "1Y": 250}
DEFAULT_WINDOW = "3M"
TREND_OPTIONS = ["SP500", "NDX", "VIX", "对比"]
MA_OPTIONS = ["MA20", "MA50", "MA200"]

SYMBOL_COLORS = {"SP500": "#1F6FEB", "NDX": "#1A7F37", "VIX": "#D1242F"}
MA_COLORS = {"MA20": "#E8A33D", "MA50": "#8250DF", "MA200": "#57606A"}
LEVEL_LABELS = signals.LEVEL_LABELS


# ---------- 数据（保持原有逻辑不变） ----------
@st.cache_data(ttl=CACHE_TTL, show_spinner="正在准备数据……")
def load_history_data(fingerprint: tuple) -> pd.DataFrame:
    """读历史表；没有数据或数据太旧时，现场跑一遍完整流水线再读。

    指纹参数是缓存钥匙：文件一被改写（定时任务跑完、或点"立即更新"），
    指纹就变了，缓存自动失效，页面立刻是新数据。
    本地没有历史文件、云端容器刚重建磁盘时，这里会自己把过去 250 天补出来。
    """
    data = history.load_history()
    if not data.empty:
        age_days = (config.today() - data.index.max().date()).days
        if age_days <= FRESH_DAYS:
            return data

    run_daily.main()
    return history.load_history()


# ---------- 小工具 ----------
def fmt(value, spec: str = ",.2f") -> str:
    """数字格式化；空值显示成 --，免得表格里出现 nan。"""
    if value is None or pd.isna(value):
        return "--"
    return format(value, spec)


def fmt_pct(value) -> str:
    """涨跌幅；空值显示成 --。"""
    if value is None or pd.isna(value):
        return "--"
    return f"{value:+.2f}%"


def colored_pct(value) -> str:
    """涨跌幅 + 颜色（涨绿跌红），用在 markdown 里。"""
    if value is None or pd.isna(value):
        return "--"
    color = "green" if value >= 0 else "red"
    return f":{color}[{value:+.2f}%]"


def updated_text(fingerprint: tuple) -> str:
    """历史表的最后写入时间（用香港时区显示）。"""
    mtime = fingerprint[0] if fingerprint else 0
    if not mtime:
        return "尚未生成"
    moment = datetime.fromtimestamp(mtime, ZoneInfo(config.TIMEZONE))
    return moment.strftime("%Y-%m-%d %H:%M")


# ---------- 立即更新 ----------
def run_update() -> None:
    """跑一遍完整流水线，然后把页面刷新到最新数据。"""
    with st.spinner("正在取数、算指标、判异常、存历史、出日报 ..."):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = run_daily.main()
    st.session_state["run_log"] = buffer.getvalue()
    st.session_state["run_code"] = code
    st.cache_data.clear()      # 清缓存，页面立刻读到刚生成的新数据
    st.rerun()


def render_update_button(key: str) -> None:
    if st.button("立即更新", type="primary", icon=":material/refresh:", key=key):
        run_update()


# ---------- 侧边栏（只放全局信息和设置） ----------
def render_sidebar(data: pd.DataFrame, result: dict, fingerprint: tuple) -> tuple[int, bool]:
    with st.sidebar:
        st.markdown(f"#### {result['emoji']} {result['label']}")
        st.progress(result["score"] / 100, text=f"风险评分 {result['score']} / 100")
        st.caption(result["hint"])

        st.space("small")
        st.caption(f"**数据更新**　{updated_text(fingerprint)}")
        if not data.empty:
            st.caption(f"**最新交易日**　{data.index.max().date()}")
        st.caption("**数据来源**　Yahoo Finance 日线")

        st.space("small")
        render_update_button("refresh_sidebar")

        code = st.session_state.get("run_code")
        if code == 0:
            st.success("更新完成", icon=":material/check_circle:")
        elif code is not None:
            st.error("没拿到数据，看下面的输出", icon=":material/error:")
        log = st.session_state.get("run_log")
        if log:
            with st.expander("上次更新输出", expanded=False):
                st.code(log, language="text")

        with st.expander("设置", icon=":material/settings:"):
            card_days = st.segmented_control(
                "历史日报显示天数", [5, 10, 20], default=10, key="card_days"
            )
            show_raw = st.toggle("显示分析数据表", key="show_raw")

    return card_days or 10, bool(show_raw)


# ---------- 顶部 ----------
def render_header(data: pd.DataFrame, result: dict, fingerprint: tuple) -> None:
    left, right = st.columns([5, 1], vertical_alignment="center")
    with left:
        st.title("美股市场监测", icon=":material/monitoring:")
        pieces = [f"{result['emoji']} {result['label']}"]
        if not data.empty:
            pieces.append(f"最新交易日 {data.index.max().date()}")
            if (config.today() - data.index.max().date()).days > STALE_DAYS:
                pieces.append(":orange[⚠ 数据可能偏旧]")
        pieces.append(f"数据更新于 {updated_text(fingerprint)}")
        st.caption("　·　".join(pieces))
    with right:
        render_update_button("refresh_top")


# ---------- 第二行：三个 KPI 卡片 ----------
def render_kpi_card(daily: pd.DataFrame, name: str) -> None:
    close = daily[f"{name}_close"].iloc[-1]
    change_abs = daily[f"{name}_change_abs"].iloc[-1]
    change = daily[f"{name}_change_1d"].iloc[-1]
    change_5d = daily[f"{name}_change_5d"].iloc[-1]
    change_20d = daily[f"{name}_change_20d"].iloc[-1]
    level = daily[f"{name}_level"].iloc[-1] if f"{name}_level" in daily.columns else None
    sparkline = daily[f"{name}_close"].tail(24).tolist()

    with st.container(border=True):
        st.metric(
            label=f"{market_state.DISPLAY_NAMES[name]}　{LEVEL_LABELS.get(level, '--')}",
            value=fmt(close),
            delta=f"{fmt(change_abs, '+,.2f')}　{fmt_pct(change)}",
            # VIX 涨是坏事，颜色反过来，免得"涨了显绿"让人误读
            delta_color="inverse" if name == "VIX" else "normal",
            chart_data=sparkline,
            chart_type="line",
            border=False,
        )
        st.caption(f"5 日 {fmt_pct(change_5d)}　·　20 日 {fmt_pct(change_20d)}")
        if name == "VIX":
            zone_text, zone_color = market_state.vix_zone(close)
            st.badge(f"风险指标 · {zone_text}", color=zone_color)


def render_kpi_cards(daily: pd.DataFrame) -> None:
    for column, name in zip(st.columns(len(config.SYMBOLS)), config.SYMBOLS):
        with column:
            render_kpi_card(daily, name)


# ---------- 第三行：市场状态 + 今日需要关注 ----------
def render_state(result: dict) -> None:
    with st.container(border=True):
        st.subheader("市场状态")
        st.markdown(f"## {result['emoji']} {result['label']}")
        st.progress(result["score"] / 100, text=f"风险评分 {result['score']} / 100")
        st.caption(result["hint"])

        if result["parts"]:
            st.markdown("**评分构成**")
            for part in result["parts"]:
                st.markdown(f":gray[+{part['points']}]　{part['text']}")
        else:
            st.caption("所有指标都在正常范围，没有加分的风险项。")


def render_attention(result: dict) -> None:
    with st.container(border=True):
        st.subheader("今日需要关注")
        attention = market_state.attention_items(result)
        if attention:
            for text in attention:
                st.markdown(f":orange[⚠ {text}]")
        else:
            st.markdown(":green[✓ 今日没有明显异常信号]")

        healthy = [item["text"] for item in result["checks"] if item["ok"] is True]
        if healthy:
            st.markdown("**正常项**")
            for text in healthy:
                st.caption(f"✓ {text}")


# ---------- 第四行：趋势图 ----------
def build_trend_chart(recent: pd.DataFrame, symbol: str, ma_list: list[str]):
    """Altair 折线图：真实比例（Y 轴不从 0 起）、鼠标悬停看具体数值。"""
    frame = recent.reset_index()

    if symbol == "对比":
        # 归一化：把区间起点都当成 100，两条线才能放在一起比
        base = recent[["SP500_close", "NDX_close"]].dropna()
        if base.empty:
            return None
        rebased = (base / base.iloc[0] * 100).reset_index()
        long = rebased.melt(id_vars="date", var_name="series", value_name="value").dropna(subset=["value"])
        long["series"] = long["series"].map({"SP500_close": "标普 500", "NDX_close": "纳斯达克 100"})
        color_scale = alt.Scale(
            domain=["标普 500", "纳斯达克 100"],
            range=[SYMBOL_COLORS["SP500"], SYMBOL_COLORS["NDX"]],
        )
    else:
        wanted = {f"{symbol}_close": market_state.DISPLAY_NAMES[symbol]}
        for ma in ma_list:
            column = f"{symbol}_{ma.lower()}"
            if column in recent.columns:
                wanted[column] = ma
        long = frame.melt(id_vars="date", value_vars=list(wanted), var_name="series", value_name="value")
        long = long.dropna(subset=["value"])
        long["series"] = long["series"].map(wanted)
        colors = [SYMBOL_COLORS.get(symbol, "#1F6FEB")]
        colors += [MA_COLORS[ma] for ma in ma_list if f"{symbol}_{ma.lower()}" in recent.columns]
        color_scale = alt.Scale(domain=list(wanted.values()), range=colors)

    return (
        alt.Chart(long)
        .mark_line(strokeWidth=1.8)
        .encode(
            x=alt.X("date:T", title=None, axis=alt.Axis(format="%m-%d", grid=False, tickCount=6)),
            y=alt.Y(
                "value:Q",
                title=None,
                scale=alt.Scale(zero=False),      # 关键：不从 0 起，否则小幅波动会被压平
                axis=alt.Axis(format=",.0f", tickCount=5),
            ),
            color=alt.Color(
                "series:N",
                scale=color_scale,
                legend=alt.Legend(title=None, orient="top", direction="horizontal"),
            ),
            tooltip=[
                alt.Tooltip("date:T", title="日期", format="%Y-%m-%d"),
                alt.Tooltip("series:N", title="系列"),
                alt.Tooltip("value:Q", title="数值", format=",.2f"),
            ],
        )
        .properties(height=300)
        .configure_view(strokeOpacity=0)
        .configure_axis(labelColor="#57606A", labelFontSize=12, domainColor="#E3E8EF", tickColor="#E3E8EF")
        .configure_legend(labelFontSize=12, symbolSize=60)
    )


def render_trend(daily: pd.DataFrame) -> None:
    with st.container(border=True):
        st.subheader("趋势")
        col1, col2, col3 = st.columns([2, 2, 3], vertical_alignment="bottom")
        with col1:
            symbol = st.segmented_control("指标", TREND_OPTIONS, default="SP500", key="trend_symbol")
        with col2:
            window = st.segmented_control("区间", list(WINDOWS), default=DEFAULT_WINDOW, key="trend_window")
        with col3:
            ma_list = st.pills("均线", MA_OPTIONS, selection_mode="multi", default=["MA20"], key="trend_ma")

        symbol = symbol or "SP500"
        window = window or DEFAULT_WINDOW
        ma_list = ma_list or []
        recent = daily.tail(WINDOWS[window])

        chart = build_trend_chart(recent, symbol, ma_list)
        if chart is None:
            st.info("这段时间没有可用数据。")
            return
        st.altair_chart(chart)

        if symbol != "对比":
            series = recent[f"{symbol}_close"].dropna()
            if not series.empty:
                st.caption(
                    f"{market_state.DISPLAY_NAMES[symbol]}　"
                    f"区间最高 {series.max():,.2f}　最低 {series.min():,.2f}　"
                    f"区间涨跌 {fmt_pct((series.iloc[-1] / series.iloc[0] - 1) * 100)}"
                )
        else:
            st.caption("两条线都以区间起点为 100，方便比较同期表现。VIX 不参与——它的量级和指数完全不同。")


# ---------- 第五行：历史日报 ----------
def summarize_card(card: dict) -> str:
    """把一天的信息压成一行：日期、状态、评分、三个指数、信号条数。"""
    values = []
    for name in config.SYMBOLS:
        close, change = card["values"][name]
        values.append(f"{name} {fmt(close, ',.0f')} {colored_pct(change)}")
    warnings = card["warnings"]
    tail = f":orange[{warnings} 条信号]" if warnings else ":green[无异常]"
    return (
        f"**{card['day']}**　{card['emoji']} {card['label']}　"
        f"风险 {card['score']}/100　　" + "　".join(values) + f"　　{tail}"
    )


def render_full_report(day_text: str) -> None:
    """展开某一天的完整日报（正文 + 走势图）。"""
    path = config.REPORT_DIR / f"{day_text}.md"
    if not path.exists():
        st.caption(f"没有找到 {day_text} 的日报文件（可能那天没生成，或者文件被清理过）。")
        return

    body = path.read_text(encoding="utf-8")
    # 报告里的图片是相对路径，网页里会 404；去掉那一行，改用 st.image 直接显示本机图片
    body = "\n".join(line for line in body.splitlines() if not line.strip().startswith("!["))
    with st.expander(f"{day_text} 完整日报", expanded=True, icon=":material/description:"):
        st.markdown(body)
        picture = path.with_suffix(".png")
        if picture.exists():
            st.image(str(picture))


def render_history(daily: pd.DataFrame, card_days: int) -> None:
    cards = market_state.daily_cards(daily, days=card_days)
    with st.container(border=True):
        st.subheader("历史日报")
        st.caption(f"最近 {len(cards)} 个交易日。点右边「查看」展开当天的完整日报。")
        for card in cards:
            row = st.columns([12, 1], vertical_alignment="center")
            with row[0]:
                st.markdown(summarize_card(card))
            with row[1]:
                if st.button("查看", key=f"view_{card['day']}", icon=":material/description:"):
                    st.session_state["view_day"] = str(card["day"])

        view_day = st.session_state.get("view_day")
        if view_day:
            render_full_report(view_day)


# ---------- 入口 ----------
def main() -> None:
    st.set_page_config(
        page_title="美股市场监测",
        page_icon=":material/monitoring:",
        layout="wide",
        initial_sidebar_state="collapsed",   # 侧栏默认收起，把宽度留给数据
    )

    fingerprint = history.fingerprint()
    data = load_history_data(fingerprint)
    daily = market_state.build_daily_table(data)
    result = market_state.assess(daily)

    card_days, show_raw = render_sidebar(data, result, fingerprint)
    render_header(data, result, fingerprint)

    if data.empty:
        st.warning("还没有历史数据。点右上角「立即更新」跑一次，或在终端运行 python run_daily.py。")
        return

    render_kpi_cards(daily)
    render_state(result)
    render_attention(result)
    render_trend(daily)
    render_history(daily, card_days)

    if show_raw:
        with st.expander("分析数据表（最后 20 行）", expanded=False):
            st.dataframe(daily.tail(20))


main()
