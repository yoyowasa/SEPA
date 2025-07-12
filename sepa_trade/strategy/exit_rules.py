"""
exit_rules.py

SEPA公式のリスク管理“下限”に合わせて
ATRトレーリングストップの係数を **1.5** に引き下げた。

提供シグナル
------------
• atr_trail(n=1.5) : ATR×1.5 を下回ったら EXIT
• ema_cross()      : 10EMA を終値で明確に割り込んだら EXIT
"""

from __future__ import annotations

import pandas as pd


class ExitStrategy:
    """
    Parameters
    ----------
    df : pd.DataFrame
        日足 OHLCV (列: 'High', 'Low', 'Close')
    entry_price : float
        建玉平均コスト
    """

    def __init__(self, df: pd.DataFrame, entry_price: float) -> None:
        self.df = df.copy()
        self.entry_price = entry_price

        # ATR(10) 計算
        tr = pd.concat(
            [
                self.df["High"] - self.df["Low"],
                (self.df["High"] - self.df["Close"].shift()).abs(),
                (self.df["Low"] - self.df["Close"].shift()).abs(),
            ],
            axis=1,
        ).max(axis=1)
        self.df["ATR10"] = tr.rolling(10).mean()

        # 10EMA 計算
        self.df["EMA10"] = self.df["Close"].ewm(span=10, adjust=False).mean()

    # ───────── EXIT シグナル ─────────
    def atr_trail(self, n: float = 1.5) -> bool:   # 旧デフォルト 2.0 → 1.5
        """ATR×n のトレーリングストップをヒットしたら True"""
        stop = self.entry_price - self.df["ATR10"].iloc[-1] * n
        return self.df["Low"].iloc[-1] < stop

    def ema_cross(self) -> bool:
        """終値が 10EMA を割り込んだら True"""
        return self.df["Close"].iloc[-1] < self.df["EMA10"].iloc[-1]
