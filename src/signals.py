"""判断层：按阈值把指标翻译成"正常 / 关注 / 警报"。

职责
    只做比较和推理。不上网、不算指标、不排版。
    输入是 metrics 给的指标表，输出是每个标的的结论 + 理由。

三档结论
    normal  一切正常
    watch   值得关注（单项指标越线，或数据不全）
    alert   需要警惕（VIX 急升、单日大跌/大涨这类明显异常）

判断规则（阶段一，阈值都在 config.THRESHOLDS 里）
    - 单日涨跌幅绝对值 > daily_change_pct
    - VIX 水平 > vix_level
    - VIX 单日涨幅 > vix_spike_pct
    - 纳指与标普单日涨跌幅差距 > ndx_sp500_gap

计划实现的函数（下一步再写）
    evaluate(metrics_row, config) -> dict
        单个标的：{"level": "...", "reasons": ["..."]}
    evaluate_all(metrics_table, config) -> dict[str, dict]
        整张表逐行判断，返回 README 里约定的那种结构。

设计原则
    每条规则命中时都必须写一句人能看懂的理由，日报里要显示出来。
    宁可多说一句为什么，也不要只给一个孤零零的"警报"。
"""
