"""项目唯一的"配置开关"。

原则：所有"会变的数字和路径"都写在这里，其它文件只 import，不自己写死。
想改监测对象、改异常阈值、改文件位置，只动这一个文件。
"""

from pathlib import Path

# ---------- 路径 ----------
PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"        # 原始数据缓存（CSV）
REPORT_DIR = PROJECT_DIR / "reports"   # 生成的日报（Markdown）

# ---------- 监测标的 ----------
# key   = 我们内部使用的名字，也是日报里显示的名字
# value = 数据源 Yahoo 原始接口用的代码，^ 开头的代表指数
SYMBOLS = {
    "SP500": "^GSPC",
    "NDX": "^NDX",
    "VIX": "^VIX",
}

# ---------- 取数参数 ----------
HISTORY_DAYS = 250        # 多取一些历史，算均线才有足够样本
REQUEST_TIMEOUT = 20      # 单次网络请求超时（秒）

# ---------- 异常判断阈值 ----------
# 重要：不同标的的"正常波动"根本不是同一个量级。
# 标普单日动 5% 是历史级事件，VIX 单日动 5% 只是普通的一天。
# 所以阈值按标的分开设，而且——某个标的没出现在字典里，就表示这条规则对它不适用。
#
# 每一档都是 {"watch": 关注线, "alert": 警报线}：越过关注线记"关注"，越过警报线记"警报"。

# 各标的的单日涨跌幅（两头都算异常，所以看绝对值）
DAILY_MOVE_PCT = {
    "SP500": {"watch": 1.5, "alert": 3.0},
    "NDX": {"watch": 2.0, "alert": 4.0},
    "VIX": {"watch": 15.0, "alert": 25.0},
}

# 收盘价"高于多少"代表市场紧张——目前只有 VIX 用这条，越高越危险
LEVEL_ABOVE = {
    "VIX": {"watch": 25.0, "alert": 35.0},
}

# 收盘价相对 MA20 的偏离幅度（两头都算）
# VIX 故意不设：它天然就贴着均线大幅摆动，偏离 3% 是家常便饭，这条规则对它没有意义
MA20_DEVIATION_PCT = {
    "SP500": {"watch": 3.0, "alert": 6.0},
    "NDX": {"watch": 4.0, "alert": 8.0},
}

# 纳指与标普的单日涨跌幅之差，用来发现"风格分化"（钱在科技股和传统股之间搬家）
NDX_SP500_GAP_PCT = {"watch": 2.0, "alert": 3.5}

# ---------- 报告 ----------
REPORT_TITLE = "美股市场日报"
TIMEZONE = "Asia/Hong_Kong"
DATA_SOURCE_NOTE = "Yahoo Finance 日线（原始图表接口，免费、不需要 API key）"
