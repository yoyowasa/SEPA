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
    日足 Series / DataFrame を週足終値 DataFrame ("Close"1列) に変換する。
    ・週末＝金曜終値
    ・未確定週を除外
    ・欠損は前方補完
    """

    # --- 1) Close 列を Series に抽出 ----------------------------
    if isinstance(close_like, pd.Series):
        close_series = close_like
    else:
        df = close_like.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # "Close" / "Adj Close" の優先順で列を取得し、なければ "Close" で始まる列の先頭を使う
        try:
            close_series = df[["Close", "Adj Close"]].iloc[:, 0]
        except KeyError:
            close_cols = [c for c in df.columns if c.startswith("Close")]
            if not close_cols:
                raise ValueError("Close 列を特定できません")
            close_series = df[close_cols[0]]

    # --- 2) 週足変換 -------------------------------------------
    weekly = (
        close_series.resample("W-FRI").last()  # 金曜終値
        .ffill()                                # 欠損補完
        .iloc[:-1]                              # 未確定週を除外
        .to_frame("Close")
    )
    return weekly

def debug_print_weekly_ma(ticker: str, weekly: pd.DataFrame) -> None:
    """
    デバッグ専用：直近 5 週の Close / ma30 / ma40 を表示
    """
    ma30 = weekly["Close"].rolling(30).mean()
    ma40 = weekly["Close"].rolling(40).mean()
    print(f"\n[{ticker}] 直近 5 週")
    print(weekly.tail(5)
          .assign(ma30=ma30, ma40=ma40)
          .tail(5)[["Close", "ma30", "ma40"]]
          .to_string())
