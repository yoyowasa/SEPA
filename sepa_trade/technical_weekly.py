"""
technical_weekly.py

週足版トレンドテンプレート（Minervini 公式 8 条件相当）。
日足の 50 / 150 / 200 日線を
　→ 10 / 30 / 40 週移動平均線  
52 週高値・安値はそのまま  
という対応に置き換えて判定する。

※ 入力は「週足終値をインデックス＝週末日で持つ DataFrame」。
  └ もし日足 DataFrame を渡したい場合は
      `price_df.resample("W-FRI").last()` 等で週次リサンプリングしてから渡す。
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


class WeeklyTrendTemplate:
    """
    Parameters
    ----------
    price_df : pd.DataFrame
        週足終値を 'Close' 列に持つ DataFrame（最新が末尾）。
    """

    def __init__(self, price_df: pd.DataFrame) -> None:
        if "Close" not in price_df.columns:
            raise ValueError("'Close' 列が必要です（週足終値）。")

        self.df = price_df.copy()
        # 10 / 30 / 40 週単純移動平均線
        self.df["MA10W"] = self.df["Close"].rolling(10).mean()
        self.df["MA30W"] = self.df["Close"].rolling(30).mean()
        self.df["MA40W"] = self.df["Close"].rolling(40).mean()

    # ──────────────────────────────
    # パブリック API
    # ──────────────────────────────
    def passes(
        self,
        rs_rating: float,
        pct_from_low: Optional[float] = None,
        pct_from_high: Optional[float] = None,
        ma40w_lookback: int = 4,  # 4 週 ≒ 1 か月
    ) -> bool:
        """
        週足版トレンドテンプレートを総合判定。

        Returns
        -------
        bool
            条件すべてクリアで True
        """
        latest = self.df.iloc[-1]
        close = latest["Close"]

        # 52 週高値・安値との位置関係
        if pct_from_low is None or pct_from_high is None:
            rolling_high = self.df["Close"].rolling(window=52).max()
            rolling_low = self.df["Close"].rolling(window=52).min()
            if pct_from_low is None:
                pct_from_low = (close - rolling_low.iloc[-1]) / rolling_low.iloc[-1] * 100
            if pct_from_high is None:
                pct_from_high = (rolling_high.iloc[-1] - close) / rolling_high.iloc[-1] * 100

        conditions = [
            close > latest["MA30W"] > 0,
            close > latest["MA40W"] > 0,
            latest["MA30W"] > latest["MA40W"],
            self._ma40w_rising(ma40w_lookback),
            latest["MA10W"] > latest["MA30W"] and latest["MA10W"] > latest["MA40W"],
            close > latest["MA10W"],
            pct_from_low >= 30,   # 52 週安値から +30% 以上
            pct_from_high <= 25,  # 52 週高値から -25% 以内
            rs_rating >= 70,
        ]

        return all(conditions)

    # ──────────────────────────────
    # 内部ユーティリティ
    # ──────────────────────────────
    def _ma40w_rising(self, lookback: int) -> bool:
        """40 週 MA が直近 lookback 週で上向きか"""
        series = self.df["MA40W"].dropna()
        if len(series) < lookback:
            return False
        return series.iloc[-lookback:].is_monotonic_increasing
