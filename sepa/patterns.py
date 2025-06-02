"""
sepa.patterns
----------------------------------------
SEPA メソッドで使うパターン検出モジュール

* volume_breakout()     : 出来高ブレイク判定
* vcp_mask()            : VCP (Volatility Contraction Pattern) 判定   ←★追加
-------------------------------------------------
VCP 判定アルゴリズム（簡易版）
----------------------------------------
1. True Range = (High - Low) / Close  を週足で計算
2. lookback 期間（既定 60 週）内で
      • True Range が「前回ピークの ratio 倍未満」に 3 回以上
      • かつ ピボット高値から 15 % 以内
   を満たすバーを True とする
-------------------------------------------------
※ Cup-With-Handle は次ステップで個別関数として追加予定
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema  

# ----------------------------------------------------------------------
# 内部ヘルパー（既存）
# ----------------------------------------------------------------------
def _get_column(df: pd.DataFrame, name: str) -> pd.Series:
    """
    'High' / 'Volume' などを、大文字小文字＆MultiIndex対応で
    **必ず Series で** 返すユーティリティ
    """
    # --- 1) 単層列にそのまま存在 -----------------
    if name in df.columns:
        col = df[name]

    # --- 2) 大小無視で一致 ------------------------
    else:
        col = None
        for c in df.columns:
            if isinstance(c, str) and c.lower() == name.lower():
                col = df[c]
                break

        # --- 3) MultiIndex の末尾レベル -------------
        if col is None and isinstance(df.columns, pd.MultiIndex):
            try:
                col = df.xs(name, level=-1, axis=1)
            except KeyError:
                pass

    if col is None:
        raise ValueError(f"DataFrame に '{name}' 列を取得できません。")

    # DataFrame→Series に変換（1 列を想定）
    if isinstance(col, pd.DataFrame):
        col = col.iloc[:, 0]

    return col



# ----------------------------------------------------------------------
# 1) 出来高ブレイク
# ----------------------------------------------------------------------
def volume_breakout(
    df: pd.DataFrame,
    high_window: int = 20,
    vol_window: int = 20,
    vol_multiplier: float = 1.4,
) -> pd.Series:
    """価格が直近 high_window 本高値を抜き & 出来高急増なら True"""
    high = _get_column(df, "High")
    volume = _get_column(df, "Volume")

    pivot_high = high.shift(1).rolling(high_window).max()
    vol_ma = volume.rolling(vol_window).mean()

    return (high > pivot_high) & (volume > vol_ma * vol_multiplier)


# ----------------------------------------------------------------------
# 2) VCP (Volatility Contraction Pattern)
# ----------------------------------------------------------------------
def vcp_mask(
    df: pd.DataFrame,
    lookback: int = 60,            # ← 60週固定
    min_contractions: int = 3,     # ← 3回
    ratio: float = 0.8,            # ← 0.8
    price_near_high_pct: float = 0.12,  # ← −12%
) -> pd.Series:
    """
    ミネルヴィニ公式に沿った VCP 完成判定
    """
    high = _get_column(df, "High")
    low  = _get_column(df, "Low")
    idx  = df.index

    if len(df) < lookback + 1:
        return pd.Series(False, index=idx)

    # True Range (%)
    tr = ((high - low) / high).to_numpy(dtype=float)

    contr_cnt  = np.zeros_like(tr, dtype=int)
    prev_peak  = np.nan
    running    = 0

    for i, tr_val in enumerate(tr):
        win_start = max(0, i - lookback)
        peak = tr[win_start:i+1].max()

        if np.isnan(prev_peak):
            prev_peak = peak

        if tr_val < prev_peak * ratio:
            running += 1
            prev_peak = tr_val

        contr_cnt[i] = running

    contr_ok = contr_cnt >= min_contractions
    pivot_hi = high.rolling(lookback).max()
    near_hi  = high <= pivot_hi * (1 - price_near_high_pct)

    mask = contr_ok & near_hi
    return pd.Series(mask, index=idx, dtype=bool)


# ----------------------------------------------------------------------
# Cup-With-Handle 公式判定  ── インデックスを整数化して安全にスライス
# ----------------------------------------------------------------------
def cup_mask(df: pd.DataFrame,
             depth_pct_upper: float = 0.33,
             handle_pct: float = 0.08,
             handle_weeks: tuple[int, int] = (1, 5)) -> pd.Series:
    """
    Cup-with-Handle 完成週を True にするマスク。
    ・空スライスをスキップ
    ・ハンドル長さを「インデックス位置の差」で判定
    """
    high = df["High"]
    low  = df["Low"]
    idx  = df.index

    is_cup = pd.Series(False, index=idx)

    for pivot_pos in range(len(df)):                   # pivot_pos: 整数位置
        pivot_price = high.iloc[pivot_pos]

        # ---- カップ開始探索（最大26週前） -----------------
        for start_pos in range(max(0, pivot_pos - 26), pivot_pos):
            win_low = low.iloc[start_pos:pivot_pos]
            if win_low.empty:
                continue

            bottom_pos = win_low.argmin() + start_pos  # 位置→絶対位置
            depth_pct = (pivot_price - low.iloc[bottom_pos]) / pivot_price
            if not (0.12 <= depth_pct <= depth_pct_upper):
                continue

            # ---- ハンドル判定 -----------------------------
            handle_start = pivot_pos - handle_weeks[1]
            handle_end   = pivot_pos - handle_weeks[0]
            if handle_start < 0:
                continue
            handle_low = low.iloc[handle_start:handle_end]
            if handle_low.empty:
                continue

            handle_bottom_pos = handle_low.argmin() + handle_start
            handle_depth = (pivot_price - low.iloc[handle_bottom_pos]) / pivot_price
            handle_len   = handle_weeks[0] <= (pivot_pos - handle_bottom_pos) <= handle_weeks[1]

            if handle_depth <= handle_pct and handle_len:
                is_cup.iloc[pivot_pos] = True
                break

    return is_cup





