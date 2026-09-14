"""指标层：把"一堆日线"变成"几个关键数字"。

职责
    纯计算，不上网、不判断、不排版。输入是 fetch 给出的 DataFrame，
    输出是一张"每个指数一行"的指标表。

计划计算的指标
    change_1d / change_5d / change_20d   最近 1、5、20 个交易日的涨跌幅（%）
    ma20 / ma50                          20 日、50 日移动平均线
    close_vs_ma20                        收盘价相对 MA20 的偏离（%）
    vix_value / vix_change_1d            VIX 的绝对水平与单日变化（%）

计划实现的函数（下一步再写）
    build_metrics(prices: dict[str, pandas.DataFrame], config) -> pandas.DataFrame
        把三个指数合成一张指标表。
    change_pct(series, periods) -> float
        计算涨跌幅的通用小工具，供上面的函数复用。

注意
    历史样本不足时（比如数据缺失），要返回 NaN 而不是抛异常，
    让后面的判断层自己决定怎么处理"数据不全"。
"""
