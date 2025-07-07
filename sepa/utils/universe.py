"""
sepa.utils.universe
===================
NASDAQ・NYSE・S&P500 ティッカー一覧を統合して返すユーティリティ。

・オンライン取得はすべて HTTPS
・data/universe_cache.csv に最大 7 日キャッシュ
"""

from __future__ import annotations

import io
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Set

import pandas as pd
import requests

# ----------------------------------------------------------------------
# キャッシュ設定
# ----------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR     = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
CACHE_PATH   = DATA_DIR / "universe_cache.csv"
CACHE_MAX_AGE_DAYS = 7

# ----------------------------------------------------------------------
# 1) 各種取得関数
# ----------------------------------------------------------------------
def _get_sp500() -> Set[str]:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    df  = pd.read_html(url, header=0)[0]
    return set(df["Symbol"].astype(str).str.upper())


def _get_nasdaq_all() -> Set[str]:
    url = "https://nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
    txt = requests.get(url, timeout=10).text
    df  = pd.read_csv(io.StringIO(txt), sep="|")
    return set(df["Symbol"].astype(str).str.upper())


def _get_nyse() -> Set[str]:
    """
    NYSE 上場銘柄（ETF 含む）を HTTPS CSV から取得。
    ・欠損行・数値型を除外し完全に str 化して返す。
    """
    url = "https://www1.nyse.com/publicdocs/nyse/data/NYSE_Listing_Directory.csv"
    try:
        df = pd.read_csv(url)
        col = "ACT Symbol" if "ACT Symbol" in df.columns else "Symbol"
        tickers = (
            df[col]
            .dropna()
            .astype(str)      # float → str へ変換
            .str.upper()
            .str.strip()
        )
        return set(tickers)
    except Exception:
        return set()

# ----------------------------------------------------------------------
# 2) キャッシュ I/O
# ----------------------------------------------------------------------
def _is_cache_valid(path: Path, max_age_days: int) -> bool:
    return path.exists() and datetime.utcnow() - datetime.fromtimestamp(
        path.stat().st_mtime) < timedelta(days=max_age_days)


def _save_cache(tickers: Set[str]) -> None:
    """
    float が紛れ込んだ場合でもエラーにならないよう
    str にキャストしてからソート・保存。
    """
    pd.Series(sorted(map(str, tickers))).to_csv(
        CACHE_PATH, index=False, header=False, encoding="utf-8"
    )


def _load_cache() -> Set[str]:
    return set(pd.read_csv(CACHE_PATH, header=None)[0].astype(str).str.upper())

# ----------------------------------------------------------------------
# 3) 公開 API
# ----------------------------------------------------------------------
def get_universe(
    src: str = "us_all",
    refresh: bool = False,
    cache_days: int = CACHE_MAX_AGE_DAYS,
) -> List[str]:
    """
    Parameters
    ----------
    src : {"nasdaq","nyse","sp500","us_all"}
    refresh : True ならキャッシュ無視で再取得
    cache_days : キャッシュ有効日数
    """
    if not refresh and _is_cache_valid(CACHE_PATH, cache_days):
        return sorted(_load_cache())

    src = src.lower()
    tickers: Set[str] = set()

    if src in ("nasdaq", "us_all"):
        tickers |= _get_nasdaq_all()
    if src in ("sp500", "us_all"):
        tickers |= _get_sp500()
    if src in ("nyse", "us_all"):
        tickers |= _get_nyse()

    _save_cache(tickers)
    return sorted(tickers)

# ----------------------------------------------------------------------
# 4) CLI テスト
# ----------------------------------------------------------------------
if __name__ == "__main__":
    start = time.time()
    uni = get_universe("us_all", refresh=True)
    print(f"取得銘柄数: {len(uni):,}")
    print("先頭 20:", uni[:20])
    print(f"Elapsed: {time.time() - start:.1f} sec")
