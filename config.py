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
# 阶段一先给一组"能跑起来"的默认值，之后我们看着真实数据一起调
THRESHOLDS = {
    "daily_change_pct": 1.5,    # 单日涨跌幅超过 ±1.5% 记为"波动偏大"
    "vix_level": 25.0,          # VIX 高于 25 视为"市场紧张"
    "vix_spike_pct": 20.0,      # VIX 单日涨超 20% 视为"恐慌急升"
    "ndx_sp500_gap": 2.0,       # 纳指与标普涨跌幅差距超过 2 个百分点
}

# ---------- 报告 ----------
REPORT_TITLE = "美股市场日报"
TIMEZONE = "Asia/Hong_Kong"
