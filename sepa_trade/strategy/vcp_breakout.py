"""
vcp_breakout.py

ボラティリティ収縮パターン（VCP）を日足で検出し、
ブレイクアウト当日にエントリーシグナルを返すクラス。

※ Minervini が推奨する「収縮幅が段階的に縮小するベース」
   ＋「ピボット価格を出来高増で上抜け」のロジックを実装。

使い方例::
    from sepa_trade.strategy.vcp_breakout import VCPStrategy
    import yfinance as yf

    df = yf.download("AAPL", period="6mo", auto_adjust=False)
    strat = VCPStrategy(df)
    signal, info = strat.check_today()
    if signal:
        print("ENTRY", info)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Optional

import pandas as pd


@dataclass
class BreakoutSignal:
    pivot_price: float
    breakout_price: float
    breakout_volume: float
    atr: float


class VCPStrategy:
    """
    Parameters
    ----------
    df : pd.DataFrame
        日足終値・出来高を持つ DataFrame
        必須列: 'Close', 'High', 'Low', 'Volume'
    shrink_steps : int, default 3
        収縮段階をいくつ検証するか（例: 3 段階）
    shrink_ratio : float, default 0.5
        収縮幅が前段階比で何倍未満なら「縮小」と判定するか
    """

    def __init__(
        self,
        df: pd.DataFrame,
        shrink_steps: int = 3,
        shrink_ratio: float = 0.5,
    ) -> None:
        self.df = df.copy()
        self.shrink_steps = shrink_steps
        self.shrink_ratio = shrink_ratio

        # ATR(10) を追加
        tr = pd.concat(
            [
                self.df["High"] - self.df["Low"],
                (self.df["High"] - self.df["Close"].shift()).abs(),
                (self.df["Low"] - self.df["Close"].shift()).abs(),
            ],
            axis=1,
        ).max(axis=1)
        self.df["ATR10"] = tr.rolling(10).mean()

    # ──────────────────────────────
    # パブリック API
    # ──────────────────────────────
    def check_today(self) -> Tuple[bool, Optional[BreakoutSignal]]:
        """
        今日（日足最終行）で VCP ブレイクアウト・エントリー条件を満たすか判定。

        Returns
        -------
        Tuple[bool, BreakoutSignal | None]
        """
        if len(self.df) < 60:  # データ不足
            return False, None

        # 1) 直近ベースの高値 = ピボットを計算
        pivot_price = self.df["High"].rolling(20).max().iloc[-2]  # 昨日時点の 20 日高値
        today_high = self.df["High"].iloc[-1]
        today_close = self.df["Close"].iloc[-1]

        # 2) 収縮幅が段階的に縮小しているか
        if not self._is_volatility_contracting():
            return False, None

        # 3) 出来高急増＆ピボット突破でブレイク確認
        vol_today = self.df["Volume"].iloc[-1]
        vol_avg20 = self.df["Volume"].rolling(20).mean().iloc[-2]
        volume_surge = vol_today > vol_avg20 * 1.5  # 出来高 1.5 倍以上

        breakout = today_close > pivot_price and volume_surge
        if not breakout:
            return False, None

        signal = BreakoutSignal(
            pivot_price=pivot_price,
            breakout_price=today_close,
            breakout_volume=vol_today,
            atr=self.df["ATR10"].iloc[-1],
        )
        return True, signal

    # ──────────────────────────────
    # 内部ユーティリティ
    # ──────────────────────────────
    def _is_volatility_contracting(self) -> bool:
        """
        高値-安値のレンジ幅が shrink_steps 回連続で縮小しているか判定
        """
        swing = (self.df["High"] - self.df["Low"]).rolling(5).max()  # ざっくり 5 日レンジ
        recent = swing.dropna().iloc[-(self.shrink_steps + 1) :]
        if len(recent) < self.shrink_steps + 1:
            return False

        # 段階的に縮小しているか
        for i in range(1, len(recent)):
            if recent.iloc[i] >= recent.iloc[i - 1] * self.shrink_ratio:
                return False
        return True
