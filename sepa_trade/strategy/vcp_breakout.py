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
import logging
from typing import Tuple, Optional

import pandas as pd

# ロガーの設定
logger = logging.getLogger(__name__)

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
    def check_today(self) -> Tuple[bool, Optional[BreakoutSignal]]:
        """
        本日が VCP ブレイクアウトかを判定。

        Returns
        -------
        (flag, signal)
            flag が True のとき、signal に BreakoutSignal インスタンスを返す
        """
        if len(self.df) < 60:
            logger.debug("データ不足 (60日未満) のため VCP チェックをスキップ")
            return False, None  # データ不足

        today = self.df.iloc[-1]

        # --- 1. ピボットブレイクの確認 ---
        # 直近20日（昨日まで）の高値をピボットポイントとする
        pivot_high = self.df["High"].iloc[-21:-1].max()
        if today["Close"] < pivot_high * 1.01:
            return False, None

        # --- 2. 出来高急増の確認 ---
        # 直近20日（昨日まで）の平均出来高
        avg_volume_20d = self.df["Volume"].iloc[-21:-1].mean()
        volume_threshold = avg_volume_20d * self.volume_ratio

        volume_passes = today["Volume"] >= volume_threshold
        logger.debug(
            "出来高チェック: Today=%d, Avg20=%d, Threshold=%d, Pass=%s",
            today["Volume"], avg_volume_20d, volume_threshold, volume_passes
        )
        if not volume_passes:
            return False, None

        # --- 3. ボラティリティ収縮の確認 ---
        is_contracting = self._is_volatility_contracting()
        logger.debug("ボラティリティ収縮チェック: Pass=%s", is_contracting)
        if not is_contracting:
            return False, None

        # すべての条件を満たした場合、シグナルを生成
        signal = BreakoutSignal(
            breakout_price=today["Close"],
            atr=self.df["ATR10"].iloc[-2]  # 修正: ブレイクアウト前日のATRを使用
        )
        return True, signal

    # ──────────────────────────────
    # 内部メソッド
    # ──────────────────────────────
    def _is_volatility_contracting(self) -> bool:
        """ブレイクアウト前日にかけて、高値-安値レンジが shrink_steps 回以上、連続で収縮しているか判定。"""
        # 比較に必要な期間の日数を計算 (例: 2回収縮を確認するには3日分のレンジが必要)
        required_days = self.shrink_steps + 1
        if len(self.df) < required_days + 1:  # +1 はブレイクアウト当日分
            return False

        # ブレイクアウト当日を含まない、直近のレンジを取得
        ranges = self.df["Range"].iloc[-(required_days + 1) : -1]

        # ジェネレータ式と all() を使い、すべての収縮条件が満たされるかチェック
        return all(
            ranges.iloc[i] < ranges.iloc[i - 1] * self.shrink_ratio
            for i in range(1, len(ranges))
        )
