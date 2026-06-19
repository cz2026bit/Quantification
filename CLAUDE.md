# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位

面向量化交易**入门学习**的最小可用项目：用户在网页上选一只股票（A股或美股）+ 一种策略，
即可看到净值曲线和最大回撤。设计目标是简单、可读、易扩展，而非追求生产级撮合精度。

## 常用命令

```bash
# 安装依赖（首次）
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# 启动网页（主要使用方式）
streamlit run app.py

# 不联网验证核心逻辑（策略 + 回测 + 绘图，用合成数据）
python -c "import pandas as pd, numpy as np; from quant import strategies, backtest; \
idx=pd.date_range('2022-01-01',periods=400,freq='B'); \
price=100*(1+pd.Series(np.random.normal(0.0005,0.02,len(idx)),index=idx)).cumprod(); \
df=pd.DataFrame({'open':price,'high':price,'low':price,'close':price,'volume':1e6},index=idx); \
[print(k, backtest.run_backtest(df, s.func(df, **{p.name:p.default for p in s.params})).max_drawdown) for k,s in strategies.STRATEGIES.items()]"

# 验证数据源（需联网）
python -c "import datetime as dt; from quant import data; print(len(data.load_history('600519','A股',dt.date(2024,1,1),dt.date(2024,6,1))))"
```

项目暂无测试框架与 lint 配置；改动核心逻辑后请用上面的合成数据命令做冒烟验证。

## 架构

严格单向数据流，四个模块互不反向依赖，且都**不导入 Streamlit**（UI 与逻辑解耦）：

```
data → strategies → backtest → plotting
                                   ↑
                              app.py 组装为网页
```

- **`quant/data.py`** — 唯一对外函数 `load_history(symbol, market, start, end)`，返回**标准化 DataFrame**：
  `DatetimeIndex` 升序，列固定为 `open/high/low/close/volume`（小写）。A股走 akshare（前复权），
  美股走 yfinance（auto_adjust）。两个数据源的字段名、日期、MultiIndex 等差异**全部在本模块内抹平**，
  下游不感知数据来自哪个市场。新增市场只需在此加一个 `_load_xxx` 私有函数。

- **`quant/strategies.py`** — 每个策略是「行情 DataFrame → 持仓信号 Series（0=空仓，1=满仓）」的纯函数。
  策略只产信号、**不算收益**。所有策略登记在文件底部的 `STRATEGIES` 字典里，配套 `Strategy`/`Param`
  数据类描述其可调参数；`app.py` 据此**自动**渲染下拉框和参数滑块。新增策略 = 写一个函数 + 往字典加一条。

- **`quant/backtest.py`** — 向量化回测。关键约定（务必保持）：信号 `shift(1)` 后才参与持仓，
  即「T 日收盘信号、T+1 日才持仓」，**这是避免未来函数偏差的核心**，修改时不要破坏。
  返回 `BacktestResult`（净值、基准、回撤序列 + 累计/年化/最大回撤/夏普/胜率/换手指标）。年化按 252 交易日。

- **`quant/plotting.py`** — 输入 `BacktestResult`，返回 Plotly `Figure`（净值对比图、回撤填充图）。不做任何计算。

- **`app.py`** — 仅做编排：侧边栏收集输入 → 调用上述模块 → 展示指标卡片与图表。
  `@st.cache_data` 缓存取数；内置 `PRESETS` 常用标的。

## 约定与注意事项

- 全部中文注释/界面（用户为中文使用者）。
- 标准化列名是模块间的契约，改动 `data.py` 输出格式会波及所有下游。
- 数据源依赖外部网络与第三方库，akshare/yfinance 接口偶有变动；取数异常应在 `app.py` 层兜底提示用户，而非崩溃。
