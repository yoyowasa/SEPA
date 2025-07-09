#!/usr/bin/env python3
"""
demo_screen.py

SEPA トレンドテンプレート + RS レーティングで
候補銘柄をざっくりスクリーニングするテストスクリプト。

- yfinance で過去 2 年の日次株価を取得
- 半年リターン (126 営業日) を基に RS を計算
- トレンドテンプレート 8 条件を判定
- 条件を満たすティッカーを標準出力に表示

※ 本番運用では API 回数や精度の高い財務データに置き換えてください。
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

# 自作モジュール
from sepa_trade.rs import compute_rs_universe
from sepa_trade.technical import TrendTemplate

# .env 読み込み（必要なら API キーなどを使う）
load_dotenv()

# ─────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────
# 対象ティッカー（例として大型株＋ ETF）
TICKERS = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "QQQ", "SPY"]

# 株価取得期間
YEARS_BACK = 2  # 2 年分

# RS 算出パラメータ
RS_LOOKBACK = 126  # 約半年

# 52 週 (252 営業日) 計算用
W52 = 252


# ─────────────────────────────────────────────
# データ取得
# ─────────────────────────────────────────────
print("Downloading price data …")
start = (dt.date.today() - dt.timedelta(days=YEARS_BACK * 365)).isoformat()
raw = yf.download(TICKERS, start=start, progress=False)

# yfinance が "Adj Close" 列を返さない場合は "Close" を利用する
if "Adj Close" in raw.columns:
    raw_df = raw["Adj Close"]
elif "Close" in raw.columns:
    raw_df = raw["Close"]
else:
    raise KeyError("yfinance から 'Adj Close' も 'Close' も取得できませんでした。")

# yf.download が列 MultiIndex になる場合を平坦化
if isinstance(raw_df.columns, pd.MultiIndex):
    raw_df.columns = raw_df.columns.get_level_values(0)

# ─────────────────────────────────────────────
# RS レーティング計算
# ─────────────────────────────────────────────
print("Computing RS ratings …")
close_dict = {tic: raw_df[tic].dropna() for tic in TICKERS}
rs_series = compute_rs_universe(close_dict, lookback=RS_LOOKBACK)

# ─────────────────────────────────────────────
# トレンドテンプレート判定
# ─────────────────────────────────────────────
print("\n=== Screening Results ===")
candidates: list[str] = []

for tic in TICKERS:
    series = close_dict[tic]
    if len(series) < W52 + 1:
        print(f"{tic}: データ不足でスキップ")
        continue

    # 52 週高値・安値
    pct_from_low = (series.iloc[-1] - series.rolling(W52).min().iloc[-1]) / series.rolling(W52).min().iloc[-1] * 100
    pct_from_high = (series.rolling(W52).max().iloc[-1] - series.iloc[-1]) / series.rolling(W52).max().iloc[-1] * 100

    # テクニカル判定
    template = TrendTemplate(series.to_frame(name="Close"))
    passes = template.passes(
        rs_rating=rs_series[tic],
        pct_from_low=pct_from_low,
        pct_from_high=pct_from_high,
    )

    status = "✓ PASS" if passes else "✗ FAIL"
    print(f"{tic:<5} RS={rs_series[tic]:>5.1f}  {status}")

    if passes:
        candidates.append(tic)

# ─────────────────────────────────────────────
# 結果出力
# ─────────────────────────────────────────────
print("\nトレンドテンプレートを満たした銘柄:")
if candidates:
    print(", ".join(candidates))
else:
    print("該当なし")
