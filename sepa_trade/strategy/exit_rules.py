"""
exit_rules.py

SEPA のリスク管理で代表的な「ATR トレーリングストップ」と
「短期 EMA 割れ利確／損切り」を実装するモジュール。

現在2系統のシグナルを提供：
    • atr_trail : エントリー価格から ATR×n を下回ったら EXIT
    • ema_cross : 10EMA を終値で明確に割り込んだら EXIT

使い方::
    df = get_daily_df("AAPL")       # 必須列: 'Close', 'High', 'Low'
    strat = ExitStrategy(df, entry_price=175.2)

    if strat.atr_trail(n=2):   # ATR×2 下抜け?
        ...  # exit logic
    if strat.ema_cross():      # 10EMA 割れ?
        ...
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


class ExitStrategy:
    """
    Parameters
    ----------
    df : pd.DataFrame
        日足終値・高値・安値を含む DataFrame（インデックス昇順）
    entry_price : float
        建玉の平均取得単価
    """

    def __init__(self, df: pd.DataFrame, entry_price: float) -> None:
        self.df = df.copy()
        self.entry_price = entry_price

        # ATR(10)
        tr = pd.concat(
            [
                self.df["High"] - self.df["Low"],
                (self.df["High"] - self.df["Close"].shift()).abs(),
                (self.df["Low"] - self.df["Close"].shift()).abs(),
            ],
            axis=1,
        ).max(axis=1)
        self.df["ATR10"] = tr.rolling(10).mean()

        # 10EMA
        self.df["EMA10"] = self.df["Close"].ewm(span=10, adjust=False).mean()

    # ──────────────────────────────
    # EXIT シグナル
    # ──────────────────────────────
    def atr_trail(self, n: float = 2.0) -> bool:
        """
        ATR×n のトレーリングストップをヒットしたら True
        """
        latest_low = self.df["Low"].iloc[-1]
        stop_level = self.entry_price - self.df["ATR10"].iloc[-1] * n
        return latest_low < stop_level

    def ema_cross(self) -> bool:
        """
        終値が 10EMA を終値で下抜けたら True
        """
        close = self.df["Close"].iloc[-1]
        ema = self.df["EMA10"].iloc[-1]
        return close < ema
