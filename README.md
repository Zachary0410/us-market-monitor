# 美股市场监测（第一阶段）

每天回答三个问题：**S&P 500、Nasdaq 100、VIX 现在什么情况？有没有出现异常？**

第一阶段只做四步：取数 → 算指标 → 判断异常 → 出日报。不做实时行情，不做回测，不做自动推送。

项目位置：`F:\codex\2026-09-14\new-chat-4\outputs\us-market-monitor`

---

## 一、它是怎么运转的

```
config.py      配置：监测什么、阈值多少、文件放哪里
    ↓
run_daily.py   总指挥：按顺序调用下面四步（自己不干活）
    ↓
src/fetch.py    上网取 S&P 500 / Nasdaq 100 / VIX 的历史日线
src/metrics.py  算涨跌幅、均线、VIX 相关指标
src/signals.py  按阈值判断：正常 / 关注 / 警报
src/report.py   写成 reports\2026-09-14.md，并打印到终端
```

一句话记住这个设计：**只有 fetch.py 会上网，只有 signals.py 负责下判断。**

这样做的好处很实际——以后数据源从 Yahoo 换成新浪，只需要改 `fetch.py`；
阈值想调松调紧，只需要改 `config.py`。其它文件都不用动。

---

## 二、目录结构

```
us-market-monitor\
├── README.md            你正在看的这份说明书
├── requirements.txt     需要安装哪些第三方库
├── .gitignore           告诉 Git 哪些文件不用管
├── config.py            ★ 唯一的配置开关（标的、阈值、路径）
├── run_daily.py         ★ 每天运行的入口
├── src\                 业务逻辑，四个文件各一层
│   ├── __init__.py      让 src 成为一个可以被 import 的包
│   ├── fetch.py         取数层：外部数据 → 内部统一格式
│   ├── metrics.py       指标层：统一格式 → 数字指标
│   ├── signals.py       判断层：数字指标 → 异常结论
│   └── report.py        输出层：结论 → Markdown 日报
├── data\                原始数据缓存（CSV，不进 Git）
│   └── .gitkeep         占位文件，让 Git 保留这个空目录
└── reports\             每天生成的日报（Markdown，不进 Git）
    └── .gitkeep         占位文件
```

---

## 三、每个文件具体是干什么的

| 文件 | 作用 | 你多久会改它一次 |
| --- | --- | --- |
| `config.py` | 所有"会变的数字"都放这：监测哪三个标的、异常阈值多少、数据存哪里。其它文件只 import，不自己写死。 | 经常（想调阈值时） |
| `run_daily.py` | 每日入口。读配置 → 取数 → 算指标 → 判异常 → 出报告。它自己不实现任何逻辑，只负责按顺序调用。 | 几乎不改 |
| `src/fetch.py` | **唯一会上网的文件**。负责请求数据、校验数据、整理成统一格式、存一份 CSV 缓存。 | 换数据源时 |
| `src/metrics.py` | 把"一堆日线"变成"几个关键数字"：1日/5日/20日涨跌幅、MA20/MA50、收盘价偏离均线多少、VIX 的绝对水平和单日变化。 | 想加新指标时 |
| `src/signals.py` | 项目的"大脑"。拿 `config.py` 里的阈值去比对指标，输出 `normal / watch / alert` 三档结论，并写清楚**为什么**这么判。 | 想改判断规则时 |
| `src/report.py` | 只管展示，不算数字也不做判断。把指标和结论排成一份 Markdown 日报，写入 `reports\` 并打印到终端。 | 想换报告样子时 |
| `requirements.txt` | 记录项目依赖（第一阶段只有 `pandas` 和 `requests`）。 | 加库时 |
| `.gitignore` | 排除缓存、虚拟环境、生成的数据和报告，避免把垃圾提交进 Git。 | 几乎不改 |
| `data\.gitkeep`、`reports\.gitkeep` | 空目录 Git 不会保存，用占位文件保住目录结构。 | 不改 |

---

## 四、层与层之间的"数据合同"

分层的关键是约定好每一层交出去的格式：上层不用关心下层怎么实现，只认格式。

**1. `fetch.py` 交给 `metrics.py` 的东西**

每个指数一个 `pandas.DataFrame`：

- 行索引：日期（`DatetimeIndex`，从旧到新排列）
- 列：`open`、`high`、`low`、`close`、`volume`

**2. `metrics.py` 交给 `signals.py` 的东西**

一张指标表，每个指数一行（三行：SP500 / NDX / VIX）：

| 列名 | 含义 |
| --- | --- |
| `last_date` | 最新数据的日期 |
| `trading_days` | 参与计算的有效交易日数 |
| `close` | 最新收盘价（VIX 的"水平"就是它自己的收盘价，所以不需要单独一列） |
| `change_1d` / `change_5d` / `change_20d` | 涨跌幅（%） |
| `ma20` / `ma50` | 20 日、50 日移动平均线 |
| `close_vs_ma20` | 收盘价相对 MA20 偏离多少（%） |

样本不足时这些列会是 `NaN` 而不是报错，由 `signals.py` 决定怎么处理。

**3. `signals.py` 交给 `report.py` 的东西**

```python
{
    "SP500": {
        "level": "alert",
        "reasons": [
            "单日下跌 3.40%，越过 3.0% 的警报线",
            "收盘价低于 MA20 7.00%，越过 6.0% 的警报线",
        ],
    },
    "NDX": {"level": "normal", "reasons": []},
    "VIX": {"level": "watch", "reasons": ["今天没有取到 VIX 的数据，未参与判断"]},
}
```

`level` 只有三档：`normal`（正常）、`watch`（关注）、`alert`（警报）。
`reasons` 是留给以后的你看的——判断异常时**必须**留下理由，否则你不知道它为什么报警。

两个细节：

- 阈值按标的分别设在 `config.py` 里。**某个标的没出现在某条规则的字典里，就表示这条规则对它不适用**（比如 VIX 不检查"偏离 MA20"，因为它天然就贴着均线大幅摆动）。
- 即使某个标的今天根本没取到数据，它也会出现在结果里并标成"关注"——日报要如实写出"今天缺了谁"。

**4. `report.py` 交给你**

`reports\2026-09-14.md`，以及终端上的一次打印。

---

## 五、怎么运行

用 VS Code 打开项目文件夹（菜单 `文件 → 打开文件夹`），然后在终端里：

```powershell
cd F:\codex\2026-09-14\new-chat-4\outputs\us-market-monitor
python run_daily.py
```

Python 3.13.15 和依赖库已经装好，直接用 `python` 命令即可。

> 前三个模块已经写完了。想单独验证某一层，在**项目根目录**用 `-m` 方式跑：
>
> ```powershell
> python -m src.fetch      # 只看取数：三个指数的收盘价
> python -m src.metrics    # 看指标：涨跌幅、均线、相对均线偏离
> python -m src.signals    # 看判断：触发了哪条规则、整体结论是什么
> ```
>
> 注意中间是 `-m src.fetch`。如果你直接写 `python src\fetch.py`，会报
> `ModuleNotFoundError: No module named 'config'`——因为 Python 只把脚本所在目录（`src\`）
> 加进搜索路径，找不到根目录的 `config.py`。这是 Python 的导入规则，不是代码有问题。

如果终端里的中文显示成乱码，先执行一次 `chcp 65001`（切换成 UTF-8）即可。

---

## 六、第一阶段明确不做的事

- 不做实时行情、盘中刷新（做日报，收盘后跑一次就够）
- 不做估值指标（PE、CAPE 这类要么付费要么爬虫，先不碰）
- 不做自动推送（微信、邮件、钉钉都留到以后）
- 不做回测和 AI 预测（先把数据管道跑通，再谈其余）

---

## 七、接下来的顺序（一次只写一个文件）

1. ✅ `fetch.py` —— 已完成，能取回三个指数的真实日线并缓存到 `data\`
2. ✅ `metrics.py` —— 已完成，算出涨跌幅、均线、相对均线偏离
3. ✅ `signals.py` —— 已完成，按标的阈值判异常并写出理由
4. `report.py` —— 出第一份 Markdown 日报
5. 最后把 `run_daily.py` 串起来，再考虑定时任务和 Streamlit 界面
