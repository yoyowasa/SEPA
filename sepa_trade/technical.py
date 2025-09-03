"""
technical.py

Mark Minervini の「トレンドテンプレート」8 条件を判定するクラス。
短期〜中期スイングのスクリーニングに使用する最初のフィルター。
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


class TrendTemplate:
    """
    Parameters
    ----------
    price_df : pd.DataFrame
        インデックスが日付、少なくとも 'Close' 列を持つ日次株価 DataFrame。
        昇順（古い→新しい）の並びを前提とする。
    """

    # ───────────────────
    # 初期化と準備
    # ───────────────────
    def __init__(self, price_df: pd.DataFrame) -> None:
        if "Close" not in price_df.columns:
            raise ValueError("price_df に 'Close' 列が必要です。")

        self.df = price_df.copy()
        # 単純移動平均線を計算
        self.df["MA50"] = self.df["Close"].rolling(50).mean()
        self.df["MA150"] = self.df["Close"].rolling(150).mean()
        self.df["MA200"] = self.df["Close"].rolling(200).mean()

    # ───────────────────
    # 公開 API
    # ───────────────────
    def passes(
        self,
        pct_from_low: Optional[float] = None,
        pct_from_high: Optional[float] = None,
        ma200_lookback: int = 30,
    ) -> bool:
        """
        トレンドテンプレート 8 条件を総合判定する。

        Parameters
        ----------
        pct_from_low : float, optional
            52 週安値からの上昇率 (%). 未指定なら内部で計算。
        pct_from_high : float, optional
            52 週高値からの下落率 (%). 未指定なら内部で計算。
        ma200_lookback : int
            200 日移動平均線の「上向き」判定期間（日数）。

        Returns
        -------
        bool
            8 条件すべて満たせば True
        """
        # 計算に必要なデータが揃っているか確認
        if len(self.df) < 252:
            return False

        latest = self.df.iloc[-1]
        close = latest["Close"]

        # 52 週高値・安値との位置関係を計算
        if pct_from_low is None or pct_from_high is None:
            window = 252  # ≒ 52 週
            rolling_high = self.df["Close"].rolling(window=window).max().iloc[-1]
            rolling_low = self.df["Close"].rolling(window=window).min().iloc[-1]

            # ゼロ除算を防止
            if rolling_low <= 0 or rolling_high <= 0:
                return False

            if pct_from_low is None:
                pct_from_low = (close - rolling_low) / rolling_low * 100
            if pct_from_high is None:
                pct_from_high = (rolling_high - close) / rolling_high * 100

        # トレンドテンプレート8条件
        conditions = [
            # 1. 現在の株価 > 150日MA and 200日MA
            close > latest["MA150"] and close > latest["MA200"],
            # 2. 150日MA > 200日MA
            latest["MA150"] > latest["MA200"],
            # 3. 200日MAが少なくとも1ヶ月間上昇トレンド
            self._ma200_is_rising(ma200_lookback),
            # 4. 50日MA > 150日MA and 200日MA
            latest["MA50"] > latest["MA150"] and latest["MA50"] > latest["MA200"],
            # 5. 現在の株価 > 50日MA
            close > latest["MA50"],
            # 6. 現在の株価が52週安値から30%以上高い
            pct_from_low >= 30,
            # 7. 現在の株価が52週高値から25%以内
            pct_from_high <= 25,
        ]

        return all(conditions)

    # ───────────────────
    # 内部ユーティリティ
    # ───────────────────
    def _ma200_is_rising(self, lookback: int) -> bool:
        """
        200 日 MA が直近 `lookback` 日で上昇傾向かどうか。
        """
        series = self.df["MA200"].dropna()
        if len(series) < lookback:
            return False
        # monotonic_increasing は True/False
        return series.iloc[-lookback:].is_monotonic_increasing
