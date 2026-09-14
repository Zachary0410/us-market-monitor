"""图表层：把历史数据画成一张 PNG 走势图。

职责
    只画图。不算指标、不下判断、不排版。
    输入是 history.load_history() 的历史表，输出是 reports\\YYYY-MM-DD.png。

为什么单独一层
    画图要依赖 matplotlib，是项目里唯一"重"的第三方库。
    独立成一层之后，以后想改用 Streamlit 的网页图表，删掉这个文件、
    去掉 report 里那一行引用就行，其它逻辑一概不受影响。

对外提供的函数
    render_chart(history, days)   画最近 days 个交易日的走势，返回 PNG 路径

单独测试本文件：
    cd F:\\codex\\2026-09-14\\new-chat-4\\outputs\\us-market-monitor
    python -m src.chart
"""

import matplotlib

# 只往文件里画图、不开窗口。定时任务在后台跑，没有桌面，这句是必须的。
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

import config

# 中文字体：不设的话图上中文会变成一排小方块，这是 matplotlib 的经典坑
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# 每个标的固定一种颜色，看久了就认得了
COLORS = {"SP500": "#1f77b4", "NDX": "#2ca02c", "VIX": "#d62728"}
DEFAULT_COLOR = "#555555"


def render_chart(history: pd.DataFrame, days: int = 90, today=None):
    """画标普 / 纳指 / VIX 三张走势图（上下排列、共用时间轴），返回 PNG 路径。

    历史数据少于两天时不画——一条只有一个点的"曲线"没有意义。
    """
    if history.empty or len(history) < 2:
        raise ValueError("历史数据还不到两天，先攒几天再画图")

    recent = history.tail(days)
    names = list(config.SYMBOLS)
    figure, axes = plt.subplots(len(names), 1, figsize=(10, 7.5), sharex=True)

    for axis, name in zip(axes, names):
        column = f"{name}_close"
        if column not in recent.columns:
            axis.set_visible(False)
            continue

        series = recent[column].dropna()
        color = COLORS.get(name, DEFAULT_COLOR)
        axis.plot(series.index, series.values, color=color, linewidth=1.6)
        axis.grid(alpha=0.25)

        if not series.empty:
            axis.set_title(f"{name}    最新 {series.iloc[-1]:,.2f}", loc="left", fontsize=11)

        # 把"警报"的日子涂成淡色，一眼看出什么时候出过事
        levels = recent.get(f"{name}_level")
        if levels is not None:
            for day, level in levels.items():
                if level == "alert":
                    axis.axvspan(
                        day - pd.Timedelta(hours=12),
                        day + pd.Timedelta(hours=12),
                        color=color,
                        alpha=0.15,
                    )

    report_day = today or config.today()
    figure.suptitle(f"{config.REPORT_TITLE} · 最近 {len(recent)} 个交易日", fontsize=13)
    figure.autofmt_xdate()
    figure.tight_layout()

    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = config.REPORT_DIR / f"{report_day}.png"
    figure.savefig(path, dpi=130)
    plt.close(figure)          # 关掉图，免得连着跑很多天时内存越用越多
    return path


if __name__ == "__main__":
    from src import history  # 自测时读现成的历史表，不联网

    data = history.load_history()
    print(f"历史表：{len(data)} 个交易日")
    print(f"走势图已生成：{render_chart(data)}")
