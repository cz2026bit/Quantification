# 量化交易回测学习器

一个**最简单的**量化交易学习项目：选一只股票 + 一种策略，立刻看到收益曲线和**最大回撤**。
支持 A股（akshare）和美股（yfinance），网页界面（Streamlit）操作，零金融基础也能上手。

> ⚠️ 仅用于学习量化交易的基本概念，**不构成任何投资建议**。

## 功能

- 🇨🇳🇺🇸 一键切换 A股 / 美股，内置常用标的，也可手填代码
- 📐 三种经典入门策略：双均线交叉、RSI 超买超卖、布林带
- 📊 净值曲线 vs 买入持有基准、回撤曲线、夏普/年化/胜率等指标
- 🎚 策略参数可在界面实时调整

## 快速开始

```bash
# 1. 创建虚拟环境并安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. 启动网页
streamlit run app.py
```

浏览器会自动打开 `http://localhost:8501`。在左侧选股票、选策略、调参数，点「开始回测」即可。

## 项目结构

```
quant/
  data.py         行情获取，把 A股/美股数据统一成标准 DataFrame
  strategies.py   策略：输入行情，输出持仓信号（0/1）
  backtest.py     向量化回测引擎，计算净值与最大回撤等指标
  plotting.py     用 Plotly 画净值/回撤图
app.py            Streamlit 界面，把上面四块组装起来
```

数据流向：`data → strategies → backtest → plotting`。

## 如何新增一个策略

在 `quant/strategies.py` 里写一个函数（输入行情 DataFrame，返回 0/1 的持仓信号 Series），
然后登记到文件底部的 `STRATEGIES` 字典，界面会自动出现这个新策略。
