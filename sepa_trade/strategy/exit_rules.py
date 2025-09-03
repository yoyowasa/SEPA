"""
exit_rules.py

エントリー価格に基づいた損切りルールを判定するクラス。
SEPA公式のリスク管理“下限”に合わせて、ATRストップの係数を **1.5** に設定。

提供シグナル
------------
• atr_trail(n=1.5) : エントリー価格からのATRベースの損切りラインを下回ったら EXIT
• ema_cross()      : 10EMA を終値で明確に割り込んだら EXIT
"""

from __future__ import annotations

import pandas as pd


class ExitStrategy:
    """
    Parameters
    ----------
    df : pd.DataFrame
        日足 OHLCV (列: 'High', 'Low', 'Close')。最低11日分のデータが必要。
    entry_price : float
        建玉平均コスト
    """

    def __init__(self, df: pd.DataFrame, entry_price: float) -> None:
        if len(df) < 11:
            # auto_bot.py側で既にチェックされているが、クラスの堅牢性を高める
            raise ValueError("ExitStrategyには最低11日分のデータが必要です。")

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
    def atr_trail(self, n: float = 1.5) -> bool:
        """
        ATRベースの損切りをヒットしたか判定。
        注意: これは価格に追従する「トレーリング」ストップではなく、
        エントリー価格を基準とした固定の損切りです。
        """
        # 最新のATRが計算できない(NaN)場合は、判定不可としてFalseを返す
        latest_atr = self.df["ATR10"].iloc[-1]
        if pd.isna(latest_atr):
            return False

        stop_price = self.entry_price - latest_atr * n
        return self.df["Low"].iloc[-1] < stop_price

    def ema_cross(self) -> bool:
        """終値が 10EMA を割り込んだら True"""
        # 最新のEMAが計算できない(NaN)場合は、判定不可としてFalseを返す
        latest_ema = self.df["EMA10"].iloc[-1]
        if pd.isna(latest_ema):
            return False

        return self.df["Close"].iloc[-1] < latest_ema
