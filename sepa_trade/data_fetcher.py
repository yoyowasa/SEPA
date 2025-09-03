"""
data_fetcher.py

Financial Modeling Prep API から株価データを取得するためのモジュール。
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from financialmodelingprep.client import FMPClient

logger = logging.getLogger(__name__)

# --- APIクライアントの初期化 ---
# 環境変数からAPIキーを読み込む
API_KEY = os.getenv("FMP_API_KEY")
if not API_KEY:
    # APIキーがない場合は、モジュール読み込み時にエラーを発生させる
    raise ValueError("FMP_API_KEY が .env ファイルに設定されていません。")

fmp_client = FMPClient(api_key=API_KEY, timeout=30)


def get_daily(ticker: str, years_back: int = 2) -> Optional[pd.DataFrame]:
    """
    指定されたティッカーの日足データを取得し、DataFrameとして返す。

    Args:
        ticker (str): 銘柄のティッカーシンボル。
        years_back (int): 何年分のデータを遡って取得するか。

    Returns:
        Optional[pd.DataFrame]: 成功した場合は株価データのDataFrame、失敗した場合はNone。
    """
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years_back * 365)

        # APIは辞書のリストを返す
        data_list = fmp_client.get_historical_price(
            ticker,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
        )

        if not data_list or not isinstance(data_list, list):
            logger.warning(f"[{ticker}] APIから有効なデータが返されませんでした。")
            return None

        df = pd.DataFrame(data_list)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        # カラム名を標準的な 'Close', 'Open' などに統一
        df = df.rename(columns=str.capitalize)
        return df

    except Exception:
        logger.error(f"[{ticker}] の日足データ取得中に予期せぬエラーが発生しました。", exc_info=True)
        return None


def to_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """日足データを週足データに変換する。"""
    logic = {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }
    # カラム名が大文字・小文字どちらでも対応できるようにする
    logic = {k.capitalize(): v for k, v in logic.items() if k.capitalize() in daily_df.columns}
    return daily_df.resample("W-FRI").agg(logic).dropna()