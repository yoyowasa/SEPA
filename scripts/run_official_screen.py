r"""
Official SEPA Trend Template + 52-Week Breakout Screener
========================================================
対象   : NASDAQ-100 全銘柄（Wikipedia 取得）
期間   : 2009-01-01 〜 2024-12-31
条件   : 10-w / 30-w / 40-w SMA, 40-w 上向き4週,
         52-週高値ブレイク, 出来高 Surge ≧ avg×VOL_MULT
出力   : data/screening_results.csv（Backtest 用フォーマット）

CLI:
    (.venv) PS C:\sepa_project> python scripts\run_official_screen.py [-m 1.5]
      -m : Volume Multiplier（既定 1.5）
"""

from __future__ import annotations
from pathlib import Path
import argparse, sys, warnings, datetime

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore", category=UserWarning)

# ----------------------------------------------------------------------
# 設定
# ----------------------------------------------------------------------
ROOT   = Path(__file__).resolve().parents[1]
DATA   = ROOT / "data"; DATA.mkdir(parents=True, exist_ok=True)
OUTCSV = DATA / "screening_results.csv"

START_DATE = "2009-01-01"
END_DATE   = "2024-12-31"

# ----------------------------------------------------------------------
def get_nasdaq100() -> list[str]:
    """Wikipedia から NASDAQ-100 ティッカー一覧を取得"""
    tbl = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")[4]
    return tbl["Ticker"].tolist()

def download_weekly(sym: str) -> pd.DataFrame:
    """単一ティッカーの日足 → 週足 OHLCV DataFrame を返す"""
    daily = yf.download(
        sym,
        start="2008-07-01",
        end=END_DATE,
        auto_adjust=False,         # OHLC をそのまま取得
        progress=False,
        threads=False,
    )

    if daily.empty:
        return pd.DataFrame()

    # --- MultiIndex 対応 ------------------------------------
    # yfinance が ('Open', 'SYM') の形で返す場合にトップレベルを落とす
    if isinstance(daily.columns, pd.MultiIndex):
        try:
            daily = daily.xs(sym, axis=1, level=1)
        except KeyError:
            # ティッカー階層が無い場合は最上位レベルをドロップ
            daily.columns = daily.columns.get_level_values(0)

    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(daily.columns):
        # 不足列がある場合はスキップ
        return pd.DataFrame()
    # --------------------------------------------------------

    weekly = (
        daily.resample("W-FRI")
        .agg({"Open": "first", "High": "max", "Low": "min",
              "Close": "last", "Volume": "sum"})
        .dropna()
    )
    return weekly

def screen_one(df: pd.DataFrame, sym: str, vol_mult: float) -> pd.DataFrame:
    """週足 DataFrame → 条件を満たす週のみ抽出して返す"""
    df = df.copy()
    df["SMA10"] = df["Close"].rolling(10).mean()
    df["SMA30"] = df["Close"].rolling(30).mean()
    df["SMA40"] = df["Close"].rolling(40).mean()

    cond_trend = (
        (df["Close"] > df["SMA10"]) &
        (df["Close"] > df["SMA30"]) &
        (df["Close"] > df["SMA40"]) &
        (df["SMA30"] > df["SMA40"]) &
        (df["SMA40"] > df["SMA40"].shift(4))
    )
    cond_break = df["Close"] > df["Close"].rolling(52).max().shift(1)

    vol_avg20  = df["Volume"].rolling(20).mean()
    cond_vol   = df["Volume"] >= vol_avg20 * vol_mult

    hits = df[cond_trend & cond_break & cond_vol].copy()
    if hits.empty:
        return pd.DataFrame()

    hits = hits.reset_index(names="date")
    hits["symbol"]     = sym
    hits["entry"]      = 1
    hits["exit"]       = 0
    hits["risk_pct"]   = 0.01
    # stop_price: 直近2週の最安値×0.93
    hits["stop_price"] = (
        df["Low"].rolling(2).min().shift().reindex(hits["date"]).values * 0.93
    )
    return hits[["date","symbol","entry","exit","risk_pct","stop_price"]]

# ----------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-m", type=float, default=1.5,
                    help="Volume Multiplier (default 1.5)")
    args = ap.parse_args()

    tickers = get_nasdaq100()
    print("▼ 対象ティッカー:", len(tickers))

    rows = []
    for sym in tickers:
        wk = download_weekly(sym)
        if wk.empty:
            print(f"[SKIP] {sym}: データ無し")
            continue
        res = screen_one(wk, sym, vol_mult=args.m)
        if not res.empty:
            rows.append(res)

    if not rows:
        print("‼ 期間内ヒット 0 件")
        sys.exit()

    df_out = pd.concat(rows, ignore_index=True).sort_values(["date","symbol"])
    # exit フラグ: 次週 Close<10w でクローズ（例）
    # ここでは Backtest 側で再判定する前提で 0 のまま運ぶ
    df_out.to_csv(OUTCSV, index=False, date_format="%Y-%m-%d")
    print(f"✅ {len(df_out):,} 行 → {OUTCSV}")

# ----------------------------------------------------------------------
if __name__ == "__main__":
    main()
