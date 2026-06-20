"""Streamlit 网页入口。

把 quant 包的四个模块组装成一个交互界面：
    侧边栏选股票/选策略/调参数 -> data 取数 -> strategies 生成信号
    -> backtest 回测 -> plotting 画图 -> 主区展示指标与图表。

运行：streamlit run app.py
"""

from __future__ import annotations

import datetime as dt

import streamlit as st

from quant import backtest, data, optimize, plotting, strategies

# 常用标的预设，方便快速上手（也可在输入框手动填代码）
PRESETS = {
    "A股": {
        "贵州茅台 600519": "600519",
        "宁德时代 300750": "300750",
        "比亚迪 002594": "002594",
        "中国平安 601318": "601318",
    },
    # 美股 AI 相关龙头股，AMD 排第一（默认选中）
    "美股": {
        "AMD AMD": "AMD",
        "NVIDIA NVDA": "NVDA",
        "Microsoft MSFT": "MSFT",
        "Alphabet/Google GOOGL": "GOOGL",
        "Meta META": "META",
        "Amazon AMZN": "AMZN",
        "Broadcom AVGO": "AVGO",
        "台积电 TSM": "TSM",
        "Micron 美光 MU": "MU",
        "Oracle 甲骨文 ORCL": "ORCL",
        "Marvell 迈威尔 MRVL": "MRVL",
        "Intel 英特尔 INTC": "INTC",
        "半导体3倍做多 SOXL": "SOXL",
        "Roundhill内存ETF DRAM": "DRAM",
        "Palantir PLTR": "PLTR",
        "Arm ARM": "ARM",
        "Tesla TSLA": "TSLA",
        "Apple AAPL": "AAPL",
    },
}

st.set_page_config(page_title="量化回测学习器", layout="wide")
st.title("📈 量化交易回测学习器")
st.caption("选一只股票 + 一种策略，看看它的收益和最大回撤。仅供学习，不构成投资建议。")

# ---------------- 侧边栏：参数选择 ----------------
with st.sidebar:
    st.header("① 选择股票")
    market = st.radio("市场", ["美股", "A股"], horizontal=True)

    preset_label = st.selectbox("常用标的", list(PRESETS[market].keys()))
    default_code = PRESETS[market][preset_label]
    symbol = st.text_input("股票代码", value=default_code).strip()

    today = dt.date.today()
    col1, col2 = st.columns(2)
    start = col1.date_input("开始日期", value=today - dt.timedelta(days=365 * 3))
    end = col2.date_input("结束日期", value=today)

    st.header("② 选择策略")
    strat_key = st.selectbox(
        "策略",
        list(strategies.STRATEGIES.keys()),
        format_func=lambda k: strategies.STRATEGIES[k].label,
    )
    strategy = strategies.STRATEGIES[strat_key]
    st.info(strategy.description)

    # 根据策略定义动态生成参数输入框
    params = {}
    for p in strategy.params:
        params[p.name] = st.slider(p.label, p.min, p.max, p.default)

    fee = st.number_input("单边手续费率", value=0.0003, format="%.4f", step=0.0001)

    run = st.button("开始回测", type="primary", use_container_width=True)

    st.divider()
    st.header("③ 参数寻优（可选）")
    opt_metric_label = st.selectbox(
        "寻优目标", ["累计收益", "夏普比率", "卡玛比率"],
        help="网格搜索会按这个指标找最优参数组合",
    )
    optimize_run = st.button("🔍 自动找最优参数", use_container_width=True)


# ---------------- 主区：结果展示 ----------------
@st.cache_data(show_spinner=False)
def _load(symbol: str, market: str, start: dt.date, end: dt.date):
    """缓存取数，避免重复请求数据源。"""
    return data.load_history(symbol, market, start, end)


def _get_data():
    """按钮触发后统一取数，失败则提示并中止。"""
    if not symbol:
        st.error("请先填写股票代码。")
        st.stop()
    try:
        with st.spinner("正在获取行情数据…"):
            return _load(symbol, market, start, end)
    except Exception as exc:  # 数据源异常统一兜底，提示用户
        st.error(f"获取数据失败：{exc}")
        st.stop()


# 寻优指标中文标签 -> 内部列名
_METRIC_MAP = {"累计收益": "total_return", "夏普比率": "sharpe", "卡玛比率": "calmar"}

if optimize_run:
    if not strategy.params:
        st.warning(f"策略「{strategy.label}」没有可调参数，无需寻优。")
        st.stop()
    df = _get_data()
    metric = _METRIC_MAP[opt_metric_label]
    with st.spinner("正在网格搜索全部参数组合…"):
        table = optimize.grid_search(df, strategy, fee=fee, metric=metric)

    best = table.iloc[0]
    pnames = [p.name for p in strategy.params]
    plabels = {p.name: p.label for p in strategy.params}
    # 持有收益对所有参数组合都一样（同股同期），算一次作为基准
    hold_return = float(df["close"].iloc[-1] / df["close"].iloc[0] - 1)

    st.subheader(f"🔍 「{strategy.label}」参数寻优结果")
    st.caption(f"共测试 {len(table)} 种参数组合，按「{opt_metric_label}」排序。")

    # 最优参数卡片
    cols = st.columns(len(pnames) + 3)
    for i, n in enumerate(pnames):
        cols[i].metric(f"最优 {plabels[n]}", int(best[n]))
    cols[-3].metric(
        "累计收益", f"{best.total_return:.1%}",
        delta=f"{best.total_return - hold_return:+.1%} vs 持有",
        help="最优参数的收益；箭头表示比『一直持有』多赚或少赚。",
    )
    cols[-2].metric("持有收益", f"{hold_return:.1%}", help="同期买入持有不动的收益。")
    cols[-1].metric("最大回撤", f"{best.max_drawdown:.1%}")

    # 多少组参数跑赢了持有？给个直观提示
    beat = int((table["total_return"] > hold_return).sum())
    st.caption(f"📌 {len(table)} 组参数里，只有 **{beat}** 组跑赢了「持有收益」"
               f"（{beat / len(table):.0%}）——跑赢比例越低，越说明这个策略在该股上不占优。")

    # 寻优图（折线/热力图）
    st.plotly_chart(
        plotting.optimization_chart(table, pnames, metric, opt_metric_label),
        use_container_width=True,
    )

    st.markdown("**收益最高的前 10 组参数：**")
    show = table.head(10).copy()
    show["超额收益%"] = ((show["total_return"] - hold_return) * 100).round(1)
    show["total_return"] = (show["total_return"] * 100).round(1)
    show["max_drawdown"] = (show["max_drawdown"] * 100).round(1)
    show["sharpe"] = show["sharpe"].round(2)
    show = show.rename(columns={**plabels, "total_return": "累计收益%",
                                "max_drawdown": "最大回撤%", "sharpe": "夏普",
                                "calmar": "卡玛", "num_trades": "交易次数"})
    st.dataframe(show, use_container_width=True, hide_index=True)
    st.caption(f"「超额收益%」= 该组参数收益 − 持有收益（{hold_return:.1%}）；正数才算跑赢躺平。")

    st.warning(
        "⚠️ **小心过拟合**：这里的『最优参数』是在这段历史上挑出来的，"
        "换一段时间或换只股票很可能失效。它帮你理解『参数如何影响结果』，"
        "**不能直接拿去实盘**。务必把最优参数换到别的股票/时间段再验证一遍。"
    )
    st.stop()

if run:
    df = _get_data()

    signal = strategy.func(df, **params)
    if strategy.overnight:
        # 隔夜策略：尾盘买入、次日开盘卖出，走专用回测
        result = backtest.run_overnight_backtest(df, signal, fee=fee)
    else:
        result = backtest.run_backtest(df, signal, fee=fee)

    # 关键指标卡片。持有收益 = 同期买入持有不动的收益，作为对比基准。
    hold_return = float(result.benchmark.iloc[-1] - 1)
    st.subheader("绩效概览")
    r1 = st.columns(3)
    r1[0].metric(
        "累计收益", f"{result.total_return:.1%}",
        delta=f"{result.total_return - hold_return:+.1%} vs 持有",
        help="策略的总收益；下方绿/红箭头表示比『一直持有不动』多赚或少赚。",
    )
    r1[1].metric(
        "持有收益", f"{hold_return:.1%}",
        help="同期买入持有不动的收益。策略只有跑赢它才算真有用。",
    )
    r1[2].metric("年化收益", f"{result.annual_return:.1%}")
    # 第二行集中放风险类指标：回撤 / 夏普 / 卡玛
    r2 = st.columns(4)
    r2[0].metric("最大回撤", f"{result.max_drawdown:.1%}")
    r2[1].metric("夏普比率", f"{result.sharpe:.2f}",
                 help="收益 ÷ 波动率，衡量『赚得稳不稳』。>1 不错，>2 优秀。")
    r2[2].metric("卡玛比率", f"{result.calmar:.2f}",
                 help="年化收益 ÷ 最大回撤，衡量『赚得扛不扛得住』。>1 不错，>3 优秀。")
    r2[3].metric("换手次数", f"{result.num_trades}")

    # 真实股价图——单位是该股票的货币，方便核对价格。
    # 隔夜策略每天都买卖，逐点标注没有意义，故不画买卖点。
    st.plotly_chart(
        plotting.price_chart(df, result, show_signals=not strategy.overnight),
        use_container_width=True,
    )

    # 净值曲线：把初始资金归一化为 1.0，反映"投 1 块钱跟着策略走会变成几块钱"，
    # 不是股票价格本身，所以 Y 轴在 1.0 附近是正常的。
    st.caption("ℹ️ 下面是**净值曲线**：初始资金记为 1.0，体现资金增长倍数，并非股价本身。")
    st.plotly_chart(plotting.equity_curve(result), use_container_width=True)
    st.plotly_chart(plotting.drawdown_curve(result), use_container_width=True)

    with st.expander("查看原始行情数据"):
        st.dataframe(df, use_container_width=True)
else:
    st.info("👈 在左侧选择股票和策略，然后点击「开始回测」。")
