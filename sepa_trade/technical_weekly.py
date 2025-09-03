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
    RS_THRESHOLD = 70          # RSレーティングの下限値
    PCT_FROM_LOW_MIN = 30      # 52週安値からの最低上昇率 (%)
    PCT_FROM_HIGH_MAX = 25     # 52週高値からの最大下落率 (%)

    def __init__(self, df_weekly: pd.DataFrame) -> None:
        self.df = df_weekly.copy()
        self.close = self.df["Close"]

        # 移動平均線
        self.ma10 = self.close.rolling(10).mean()
        self.ma30 = self.close.rolling(30).mean()
        self.ma40 = self.close.rolling(40).mean()

        # 52週高値・安値
        self.low_52w = self.close.rolling(52).min()
        self.high_52w = self.close.rolling(52).max()

    # ──────────────────────────────
    # 公開 API
    # ──────────────────────────────
    def passes(self) -> bool:
        """
        Stage‑2 条件をすべて満たすかを判定。

        Returns
        -------
        bool
        """
        # データ期間のチェック (最も長い期間を要する52週高安値に合わせる)
        if len(self.close) < 52:
            return False

        # 2. 移動平均線のトレンドと順序をチェック
        price = self.close.iloc[-1]
        ma10 = self.ma10.iloc[-1]
        ma30 = self.ma30.iloc[-1]
        ma40 = self.ma40.iloc[-1]

        # 2a. MAの順序: 株価 > 短期 > 中期 > 長期
        #    Minerviniのトレンドテンプレートを週足に適用した強力な条件。
        #    株価が上昇トレンドにあり、かつ短期・中期・長期のトレンドが
        #    すべて上向きに揃っていることを確認します。
        #    (修正点: 10週MAが30週MAを上回る条件を追加し、より厳格化)
        if not (price > ma10 > ma30 > ma40):
            return False

        # 2b. 40週MA(長期)が上昇トレンドにあるか
        if not (self.ma40.iloc[-1] > self.ma40.iloc[-4]):  # 1か月＝4週
            return False

        # 3. 52週高値・安値からの位置を判定
        low_52w = self.low_52w.iloc[-1]
        high_52w = self.high_52w.iloc[-1]

        if low_52w <= 0:  # ゼロ除算を防止
            return False

        pct_from_low = (price - low_52w) / low_52w * 100
        if pct_from_low < self.PCT_FROM_LOW_MIN:
            return False

        pct_from_high = (high_52w - price) / high_52w * 100
        if pct_from_high > self.PCT_FROM_HIGH_MAX:
            return False

        return True
