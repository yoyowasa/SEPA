"""
timeframe.py  ― データ整形ユーティリティ
------------------------------------------------
・yfinance から日足を取得（調整済み・イベント行なし）
・日足 Series → 週足 DataFrame(列は "Close") に変換
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import yfinance as yf


def load_daily(ticker: str, years: int = 5) -> pd.DataFrame:
    """調整済み OHLCV を日足で取得（配当・分割行を除外）"""
    df = yf.download(
        ticker,
        period=f"{years}y",
        auto_adjust=True,   # 調整済み価格のみ
        actions=False,      # 配当 / 分割行を含めない
        progress=False,
    )
    return df[["Open", "High", "Low", "Close", "Volume"]]


def daily_to_weekly(close: pd.Series) -> pd.DataFrame:
    """
    日足 Series → 週足終値 DataFrame
    ・週末を金曜終値で固定
    ・未確定週は除外
    ・欠損は前方補完で埋める
    """
    weekly = (
        close.resample("W-FRI").last()  # 金曜終値
             .ffill()                   # 欠損を前週値で補完
             .iloc[:-1]                 # 今週（未確定）は除外
             .to_frame("Close")
    )
    return weekly
