"""
timeframe.py  ― データ整形ユーティリティ
------------------------------------------------
・yfinance から日足を取得（調整済み・イベント行なし）
・日足 Series → 週足 DataFrame(列は "Close") に変換
"""
from __future__ import annotations
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
    # auto_adjust=True は既に 'Close' 列を調整済み価格として提供するため、
    # 'Adj Close' からのリネームは不要。
    return df[["Open", "High", "Low", "Close", "Volume"]]


def daily_to_weekly(daily_data: pd.DataFrame | pd.Series) -> pd.DataFrame:
    """
    日足 Series / DataFrame → 週足終値 DataFrame("Close"1列)
    ・週末＝金曜終値
    ・未確定週を除外
    ・欠損は前方補完
    """
    if isinstance(daily_data, pd.DataFrame):
        if "Close" not in daily_data.columns:
            raise ValueError("入力DataFrameに 'Close' 列が見つかりません。")
        close_series = daily_data["Close"]
    elif isinstance(daily_data, pd.Series):
        close_series = daily_data
    else:
        raise TypeError("入力はpandasのDataFrameまたはSeriesである必要があります。")

    weekly = (
        close_series.resample("W-FRI").last()  # 金曜終値
                   .ffill()                    # 欠損補完
                   .iloc[:-1]                  # 未確定週を除外
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
    debug_df = weekly.assign(ma30=ma30, ma40=ma40)
    print(debug_df.tail(5)[["Close", "ma30", "ma40"]].to_string())
