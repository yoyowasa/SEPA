"""
vcp_breakout.py

ボラティリティ収縮パターン（VCP）を検出し、ブレイクアウトの日に
エントリーシグナルを返すユーティリティ。

Minervini 公式の “最小下限” に合わせて、
    • shrink_steps = 2   （旧 3 から緩和）
    • shrink_ratio = 0.5 （50% 収縮／公式下限そのまま）
をデフォルトにした。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import pandas as pd


@dataclass
class BreakoutSignal:
    breakout_price: float   # ブレイク時終値
    atr: float              # ブレイク前日の ATR10


class VCPStrategy:
    """
    Parameters
    ----------
    df_daily : pd.DataFrame
        yfinance 形式の日足 DataFrame（Open/High/Low/Close/Volume）
    shrink_steps : int, default **2**
        収縮段階数の下限（旧デフォルト 3 → Minervini 下限値 2）
    shrink_ratio : float, default 0.5
        各収縮で高値‑安値レンジが前段階の何倍未満になるか
    volume_ratio : float, default 1.5
        ブレイク時出来高が直近平均の何倍以上なら合格か
    """

    def __init__(
        self,
        df_daily: pd.DataFrame,
        *,
        shrink_steps: int = 2,
        shrink_ratio: float = 0.5,
        volume_ratio: float = 1.5,
    ) -> None:
        self.df = df_daily.copy()
        self.shrink_steps = shrink_steps
        self.shrink_ratio = shrink_ratio
        self.volume_ratio = volume_ratio

        self.df["Range"] = self.df["High"] - self.df["Low"]
        self.df["ATR10"] = (
            pd.concat(
                [
                    self.df["High"] - self.df["Low"],
                    (self.df["High"] - self.df["Close"].shift()).abs(),
                    (self.df["Low"] - self.df["Close"].shift()).abs(),
                ],
                axis=1,
            )
            .max(axis=1)
            .rolling(10)
            .mean()
        )

    # ──────────────────────────────
    # 公開 API
    # ──────────────────────────────
    def check_today(self) -> Tuple[bool, BreakoutSignal | None]:
        """
        本日が VCP ブレイクアウトかを判定。

        Returns
        -------
        (flag, signal)
            flag が True のとき signal に BreakoutSignal を返す
        """
        if len(self.df) < 60:
            return False, None  # データ不足

        today = self.df.iloc[-1]
        pivot = self.df["High"].iloc[-2:-22:-1].max()  # 直近20日高値（前日まで）

        # 1) 高値ブレイク確認（1% 上抜け許容）
        if today["Close"] < pivot * 1.01:
            return False, None

        # 2) 出来高急増確認
        vol_avg = self.df["Volume"].iloc[-21:-1].mean()
        if today["Volume"] < vol_avg * self.volume_ratio:
            return False, None

        # 3) ボラティリティ収縮確認
        if not self._is_volatility_contracting():
            return False, None

        sig = BreakoutSignal(breakout_price=today["Close"], atr=today["ATR10"])
        return True, sig

    # ──────────────────────────────
    # 内部メソッド
    # ──────────────────────────────
    def _is_volatility_contracting(self) -> bool:
        """高値‑安値レンジが shrink_steps 回以上連続で縮小しているか"""
        ranges = self.df["Range"].iloc[-(self.shrink_steps + 2) :]
        for i in range(1, self.shrink_steps + 1):
            if not ranges.iloc[-i] < ranges.iloc[-i - 1] * self.shrink_ratio:
                return False
        return True
