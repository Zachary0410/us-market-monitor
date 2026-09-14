"""每日运行的入口（总指挥）。

用法：
    cd F:\\codex\\2026-09-14\\new-chat-4\\outputs\\us-market-monitor
    python run_daily.py

它自己不实现任何业务逻辑，只按固定顺序调用四层：

    1. 读 config.py 里的配置
    2. src.fetch     取回三个指数的日线数据
    3. src.metrics   算出涨跌幅、均线、VIX 指标
    4. src.signals   按阈值判断 正常 / 关注 / 警报
    5. src.report    生成 reports\\YYYY-MM-DD.md 并打印到终端

当前状态：骨架。上面五步的实现还没写，下一步从 src/fetch.py 开始。
"""

if __name__ == "__main__":
    print("骨架阶段：取数 → 算指标 → 判异常 → 出报告 的流程还没实现。")
    print("下一步先补 src/fetch.py，让三个指数的真实数据先跑出来。")
