# sepa/breakout.py
# ----------------
"""
Daily breakout detector for SEPA / Minervini entry trigger.

Functions
---------
is_breakout(df,
            lookback: int = 65,
            vol_ma: int = 20,
            vol_mult: float = 1.5,
            check_volume: bool = True)
    → (bool, float | None)
"""

from __future__ import annotations

import pandas as pd


# ----------------------------------------------------------------------
def _pivot_high(df_high: pd.Series, lookback: int) -> float | None:
    """
    Return the highest high within the lookback window,
    excluding the most recent bar itself (strict pivot).

    Parameters
    ----------
    df_high : pd.Series
        Daily high prices.
    lookback : int
        Number of recent bars to inspect (e.g., 65).

    Returns
    -------
    float | None
        Pivot price if found, else None.
    """
    if len(df_high) < lookback + 1:
        return None

    window = df_high.iloc[-(lookback + 1):-1]      # exclude last bar
    return window.max()


# ----------------------------------------------------------------------
def is_breakout(
    df: pd.DataFrame,
    *,
    lookback: int = 65,
    vol_ma: int = 20,
    vol_mult: float = 1.5,
    check_volume: bool = True,
) -> tuple[bool, float | None]:
    """
    Detect daily breakout above pivot high.

    Parameters
    ----------
    df : pd.DataFrame
        Daily OHLCV. Must include 'High', 'Close', 'Volume'.
    lookback : int, default 65
        How many recent bars (excluding today) to search for pivot high.
    vol_ma : int, default 20
        Look-back window for average daily volume.
    vol_mult : float, default 1.5
        Breakout volume must exceed SMA(vol_ma) * vol_mult.
    check_volume : bool, default True
        Whether to enforce the volume condition.

    Returns
    -------
    (bool, pivot_price)
        True if breakout, along with the pivot price used.
        If no valid pivot, returns (False, None).
    """
    # --- Guard clauses --------------------------------------------------
    if df.empty or len(df) < lookback + 2:
        return False, None

    df = df.copy()
    df.columns = [c.capitalize() for c in df.columns]   # unify

    if not {"High", "Close", "Volume"}.issubset(df.columns):
        raise ValueError("DataFrame needs High, Close, Volume columns")

    # --- Step 1. pivot high --------------------------------------------
    pivot = _pivot_high(df["High"], lookback)
    if pivot is None:
        return False, None

    last_close = df["Close"].iat[-1]
    last_vol   = df["Volume"].iat[-1]

    # --- Step 2. price condition ---------------------------------------
    price_ok = last_close > pivot

    # --- Step 3. volume confirmation -----------------------------------
    if check_volume:
        avg_vol = df["Volume"].tail(vol_ma).mean()
        vol_ok  = last_vol >= avg_vol * vol_mult
    else:
        vol_ok = True

    breakout = price_ok and vol_ok
    return breakout, pivot
