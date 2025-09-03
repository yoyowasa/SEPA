"""
test_api_connectivity.py

data_fetcher モジュールが外部API (Financial Modeling Prep) へ
正常に接続し、データを取得できるかテストします。
このテストは、FMP_API_KEY が環境変数に設定されている場合にのみ実行されます。
"""

import os

import pandas as pd
import pytest
from dotenv import load_dotenv

from sepa_trade.data_fetcher import get_daily

# .env ファイルを読み込んでおく
load_dotenv()

# --- テストの前提条件 ---
# APIキーが設定されていない場合は、このファイル内のすべてのテストをスキップする
pytestmark = pytest.mark.skipif(
    not os.getenv("FMP_API_KEY"), reason="FMP_API_KEY が環境変数に設定されていません。"
)


def test_data_fetcher_get_daily_for_nvda():
    """data_fetcher.get_daily() が NVDA のデータを正常に取得できるかテストする。"""
    df = get_daily("NVDA", years_back=1)
    assert isinstance(df, pd.DataFrame), f"get_daily が DataFrame を返しませんでした。応答: {type(df)}"
    assert not df.empty, "取得した DataFrame が空です。"
    assert "Close" in df.columns, "DataFrame に 'Close' カラムが含まれていません。"
    assert df.index.name == "date", "DataFrame のインデックスが 'date' ではありません。"