"""
technical_weekly.py

週足ベースで Minervini Stage‑2（トレンドテンプレート）を判定するクラス。
"""

from __future__ import annotations

import pandas as pd


class WeeklyTrendTemplate:
    """
    Parameters
    ----------
    df_weekly : pd.DataFrame
        インデックス昇順、列 ``Close`` を持つ週足 DataFrame
    """

    # ───────── 公式 Stage‑2 判定の下限値 ───────────
    RS_THRESHOLD = 70          # 旧値 80 → 公式下限 70 に緩和
    PCT_FROM_LOW_MIN = 30      # 52週安値から＋30％
    PCT_FROM_HIGH_MAX = 25     # 52週高値から－25％

    def __init__(self, df_weekly: pd.DataFrame) -> None:
        self.df = df_weekly.copy()
        self.close = self.df["Close"]

        # 移動平均線
        self.ma10 = self.close.rolling(10).mean()
        self.ma30 = self.close.rolling(30).mean()
        self.ma40 = self.close.rolling(40).mean()

    # ──────────────────────────────
    # 公開 API
    # ──────────────────────────────
    def passes(self, rs_rating: float) -> bool:
        """
        Stage‑2 条件をすべて満たすかを判定。

        Parameters
        ----------
        rs_rating : float
            相対力スコア（0‑100）

        Returns
        -------
        bool
        """
        if rs_rating < self.RS_THRESHOLD:
            return False

        price = self.close.iloc[-1]
        if not (
            price > self.ma30.iloc[-1] > self.ma40.iloc[-1]
            and price > self.ma10.iloc[-1]
        ):
            return False

        if not (self.ma40.iloc[-1] > self.ma40.iloc[-4]):  # 1か月＝4週
            return False

        pct_from_low = (price - self.close.min()) / self.close.min() * 100
        pct_from_high = (self.close.max() - price) / self.close.max() * 100

        if pct_from_low < self.PCT_FROM_LOW_MIN:
            return False
        if pct_from_high > self.PCT_FROM_HIGH_MAX:
            return False

        return True
