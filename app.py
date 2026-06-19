"""Streamlit 网页入口。

把 quant 包的四个模块组装成一个交互界面：
    侧边栏选股票/选策略/调参数 -> data 取数 -> strategies 生成信号
    -> backtest 回测 -> plotting 画图 -> 主区展示指标与图表。

运行：streamlit run app.py
"""

from __future__ import annotations

import datetime as dt

import streamlit as st

from quant import backtest, data, plotting, strategies

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


# ---------------- 主区：结果展示 ----------------
@st.cache_data(show_spinner=False)
def _load(symbol: str, market: str, start: dt.date, end: dt.date):
    """缓存取数，避免重复请求数据源。"""
    return data.load_history(symbol, market, start, end)


if run:
    if not symbol:
        st.error("请先填写股票代码。")
        st.stop()
    try:
        with st.spinner("正在获取行情数据…"):
            df = _load(symbol, market, start, end)
    except Exception as exc:  # 数据源异常统一兜底，提示用户
        st.error(f"获取数据失败：{exc}")
        st.stop()

    signal = strategy.func(df, **params)
    if strategy.overnight:
        # 隔夜策略：尾盘买入、次日开盘卖出，走专用回测
        result = backtest.run_overnight_backtest(df, signal, fee=fee)
    else:
        result = backtest.run_backtest(df, signal, fee=fee)

    # 关键指标卡片
    st.subheader("绩效概览")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("累计收益", f"{result.total_return:.1%}")
    c2.metric("年化收益", f"{result.annual_return:.1%}")
    c3.metric("最大回撤", f"{result.max_drawdown:.1%}")
    c4.metric("夏普比率", f"{result.sharpe:.2f}")
    c5.metric("换手次数", f"{result.num_trades}")

    # 真实股价图（带买卖点）——单位是该股票的货币，方便核对价格
    st.plotly_chart(plotting.price_chart(df, result), use_container_width=True)

    # 净值曲线：把初始资金归一化为 1.0，反映"投 1 块钱跟着策略走会变成几块钱"，
    # 不是股票价格本身，所以 Y 轴在 1.0 附近是正常的。
    st.caption("ℹ️ 下面是**净值曲线**：初始资金记为 1.0，体现资金增长倍数，并非股价本身。")
    st.plotly_chart(plotting.equity_curve(result), use_container_width=True)
    st.plotly_chart(plotting.drawdown_curve(result), use_container_width=True)

    with st.expander("查看原始行情数据"):
        st.dataframe(df, use_container_width=True)
else:
    st.info("👈 在左侧选择股票和策略，然后点击「开始回测」。")
