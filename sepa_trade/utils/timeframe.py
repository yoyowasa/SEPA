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


def daily_to_weekly(close_like) -> pd.DataFrame:
    """
    日足 Series / DataFrame → 週足終値 DataFrame("Close"1列)
    ・週末＝金曜終値
    ・未確定週を除外
    ・欠損は前方補完
    """
    import pandas as pd

    # --- 1) Close 列を Series に抽出 ----------------------------
    if isinstance(close_like, pd.Series):
        close_series = close_like

    else:  # DataFrame
        cols = list(close_like.columns)

        # MultiIndex → 先頭レベルを平坦化
        if isinstance(close_like.columns, pd.MultiIndex):
            close_like = close_like.copy()
            close_like.columns = close_like.columns.get_level_values(0)
            cols = list(close_like.columns)

        if "Close" in cols:
            close_series = close_like["Close"]
        elif "Adj Close" in cols:
            close_series = close_like["Adj Close"]
        elif any(c.startswith("Close") for c in cols):
            use_col = [c for c in cols if c.startswith("Close")][0]
            close_series = close_like[use_col]
        else:
            raise ValueError("Close 列を特定できません")

    # --- 2) 週足変換 -------------------------------------------
    weekly = (
        close_series.resample("W-FRI").last()  # 金曜終値
                   .ffill()                    # 欠損補完
                   .iloc[:-1]                  # 未確定週を除外
                   .to_frame("Close")
    )
    return weekly

