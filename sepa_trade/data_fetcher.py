"""
data_fetcher.py

yfinance で日足／週足データを取得・キャッシュするヘルパ。

主な関数
---------
get_daily(ticker, years_back=2)  -> pd.DataFrame
    日足 OHLCV DataFrame を返す

to_weekly(df_daily) -> pd.DataFrame
    日足 DataFrame を "W-FRI" にリサンプリングし
    週足終値ベースの DataFrame を返す
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Dict

import pandas as pd
import yfinance as yf

_CACHE_DIR = Path(".cache")
_CACHE_DIR.mkdir(exist_ok=True)


def _cache_path(ticker: str, years: int) -> Path:
    return _CACHE_DIR / f"{ticker}_{years}y.parquet"


def get_daily(ticker: str, years_back: int = 2, use_cache: bool = True) -> pd.DataFrame:
    """
    日足 OHLCV DataFrame を取得（最新が末尾）。

    Parameters
    ----------
    ticker : str
    years_back : int
        過去何年ぶん取得するか
    use_cache : bool
        True ならローカル parquet キャッシュを利用
    """
    tic = ticker.upper()
    fp = _cache_path(tic, years_back)

    if use_cache and fp.exists():
        return pd.read_parquet(fp)

    start = (dt.date.today() - dt.timedelta(days=365 * years_back)).isoformat()
    df = yf.download(tic, start=start, auto_adjust=False)

    df.to_parquet(fp)
    return df


def to_weekly(df_daily: pd.DataFrame) -> pd.DataFrame:
    """
    日足 DataFrame → 週足終値 DataFrame へ変換。

    Parameters
    ----------
    df_daily : pd.DataFrame
        yfinance download と同形式の日足

    Returns
    -------
    pd.DataFrame
        週末金曜基準 "W-FRI" の終値 DataFrame (列: 'Close')
    """
    if "Close" not in df_daily.columns:
        raise ValueError("'Close' 列が必要です")

    weekly = df_daily["Close"].resample("W-FRI").last().to_frame(name="Close")
    return weekly
