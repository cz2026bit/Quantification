"""行情数据获取层。

统一对外暴露 ``load_history`` 一个函数，返回标准化的 DataFrame：
    索引: DatetimeIndex（升序）
    列:   open, high, low, close, volume （全部小写）

A股使用 akshare，美股使用 yfinance。两个数据源的字段名/格式差异
都在本模块内部抹平，下游（策略、回测）不需要关心数据来自哪个市场。
"""

from __future__ import annotations

import datetime as dt
import time
from typing import Callable, Literal

import pandas as pd

Market = Literal["A股", "美股"]

# 标准化后的列顺序，下游统一依赖这个约定
STANDARD_COLUMNS = ["open", "high", "low", "close", "volume"]

# 数据源偶发性断连时的重试次数与每次的退避秒数
_MAX_RETRIES = 3
_BACKOFF_SECONDS = 1.5


def _with_retry(fetch: Callable[[], pd.DataFrame]) -> pd.DataFrame:
    """对取数函数做重试。

    akshare/yfinance 依赖外部 HTTP 接口，偶尔会出现 RemoteDisconnected、
    连接重置、超时等瞬时网络错误。这里做几次指数退避重试，把偶发抖动消化掉；
    若多次仍失败，则带上原始原因抛出，便于上层提示用户。
    """
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return fetch()
        except Exception as exc:  # 网络/解析类异常都先吞下重试
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_BACKOFF_SECONDS * (attempt + 1))
    raise RuntimeError(
        f"数据源连续 {_MAX_RETRIES} 次请求失败（可能是网络波动或数据源限流），"
        f"请稍后重试。原始错误：{last_exc}"
    )


def load_history(
    symbol: str,
    market: Market,
    start: dt.date,
    end: dt.date,
) -> pd.DataFrame:
    """获取标准化的日线历史行情。

    Args:
        symbol: A股为6位代码（如 "600519"）；美股为 ticker（如 "AAPL"）。
        market: "A股" 或 "美股"。
        start, end: 起止日期（含端点）。

    Returns:
        标准化 DataFrame，见模块 docstring。

    Raises:
        ValueError: 代码无效或区间内无数据。
    """
    if market == "A股":
        df = _with_retry(lambda: _load_a_share(symbol, start, end))
    elif market == "美股":
        df = _with_retry(lambda: _load_us(symbol, start, end))
    else:  # pragma: no cover - 防御性分支
        raise ValueError(f"未知市场: {market}")

    if df.empty:
        raise ValueError(f"未获取到 {symbol} 在 {start}~{end} 的数据，请检查代码或日期。")

    df = df[STANDARD_COLUMNS].sort_index()
    df = df.dropna(subset=["close"])
    return df


def _load_a_share(symbol: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    """A股前复权日线。

    主源走东方财富（``stock_zh_a_hist``），该接口偶发限流/断连；失败时
    自动回退到新浪源（``stock_zh_a_daily``）。两源字段不同，分别归一化。
    """
    try:
        return _a_share_eastmoney(symbol, start, end)
    except Exception:
        return _a_share_sina(symbol, start, end)


def _a_share_eastmoney(symbol: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    """A股主源：东方财富。"""
    import akshare as ak

    raw = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust="qfq",  # 前复权，回测更贴近真实收益
    )
    if raw is None or raw.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    raw = raw.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
        }
    )
    raw["date"] = pd.to_datetime(raw["date"])
    return raw.set_index("date")


def _a_share_sina(symbol: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    """A股备用源：新浪。需要带交易所前缀（sh/sz/bj）。"""
    import akshare as ak

    raw = ak.stock_zh_a_daily(
        symbol=_sina_symbol(symbol),
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust="qfq",
    )
    if raw is None or raw.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    raw = raw.rename(columns={"date": "date"})
    raw["date"] = pd.to_datetime(raw["date"])
    return raw.set_index("date")


def _sina_symbol(symbol: str) -> str:
    """把 6 位代码转成新浪要求的带交易所前缀格式。"""
    if symbol.startswith(("6",)):
        return f"sh{symbol}"
    if symbol.startswith(("0", "3")):
        return f"sz{symbol}"
    if symbol.startswith(("4", "8")):
        return f"bj{symbol}"
    return symbol


def _load_us(symbol: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    """美股：yfinance 的自动复权日线。"""
    import yfinance as yf

    raw = yf.download(
        symbol,
        start=start.strftime("%Y-%m-%d"),
        # yfinance 的 end 是开区间，+1 天保证含端点
        end=(end + dt.timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    if raw is None or raw.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    # 多 ticker 下载时列是 MultiIndex，这里只取单只，拍平成单层
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    raw = raw.rename(columns=str.lower)
    raw.index.name = "date"
    return raw
