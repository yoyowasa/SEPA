"""
sepa.risk
========================================
ATR(10) を使ったストップ幅と
口座リスク 1 % に基づくポジションサイズ計算
----------------------------------------
依存: pandas, numpy, yfinance
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf
from typing import Dict


# ────────────────────────────────────────
# 日足データ取得
# ────────────────────────────────────────
def _fetch_daily(ticker: str,
                 period: str = "6mo",
                 interval: str = "1d") -> pd.DataFrame:
    df = yf.download(
        ticker,
        period=period,
        interval=interval,
        auto_adjust=False,
        group_by=None,
        progress=False,
    )
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)
    return df


# ────────────────────────────────────────
# ATR(10) 計算
# ────────────────────────────────────────
def _atr(df: pd.DataFrame, period: int = 10) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return tr.rolling(window=period, min_periods=period).mean()


# ────────────────────────────────────────
# 公開 API
# ────────────────────────────────────────
def atr_stop(ticker: str,
             period: int = 10,
             multiplier: float = 1.0) -> Dict[str, float]:
    """
    ATR(10) * multiplier を % 表示で返す
    例: {'Ticker': 'AAPL', 'Close': 195.12, 'ATR%': 4.25}
    """
    df = _fetch_daily(ticker, period="6mo")
    if df.empty:
        raise ValueError(f"{ticker}: price data not found")

    close = float(df["Close"].iloc[-1])
    atr_val = float(_atr(df, period).iloc[-1])
    atr_pct = atr_val / close * 100 * multiplier

    return {
        "Ticker": ticker,
        "Close": round(close, 2),
        "ATR%":  round(atr_pct, 2),
    }


def position_size(ticker: str,
                  equity: float,
                  risk_pct: float = 1.0,
                  atr_period: int = 10,
                  multiplier: float = 1.0) -> Dict[str, float]:
    """
    ATR ストップ幅と口座リスクから株数計算
    例:
      {'Ticker': 'AAPL', 'Shares': 82,
       'ATR_Stop%': 4.25, 'Risk$': 99.96, 'Stop$': 186.76}
    """
    df = _fetch_daily(ticker, period="6mo")
    if df.empty:
        raise ValueError(f"{ticker}: price data not found")

    close = float(df["Close"].iloc[-1])
    atr_val = float(_atr(df, atr_period).iloc[-1]) * multiplier
    atr_pct = atr_val / close

    risk_dollar = equity * (risk_pct / 100)
    shares = int(risk_dollar / (close * atr_pct))
    stop_price = close - atr_val

    return {
        "Ticker":     ticker,
        "Shares":     shares,
        "ATR_Stop%":  round(atr_pct * 100, 2),
        "Risk$":      round(shares * atr_val, 2),
        "Stop$":      round(stop_price, 2),
    }
