#!/usr/bin/env python
"""
run_full_pipeline.py
========================================================
Trend Template + Volume Breakout + Fundamental (+25%)
→ チャート生成 → ATR リスク計算 を 1 コマンドで実行
--------------------------------------------------------
usage:
    python scripts/run_full_pipeline.py -n 100 -m 1.1 -equity 120000
        -n       対象銘柄数（NASDAQ 上位 n 件, default=100）
        -m       出来高ブレイク倍率 (1.1 = +10 %, default=1.1)
        -equity  口座残高 USD（ポジションサイズ計算用, default=100000）
"""

from pathlib import Path
import argparse
import importlib
import sys

import pandas as pd

# --- SEPA Core -------------------------------------------------
from sepa import pipeline as pp          # スクリーニング本体
import plot_hits            # チャート描画

# --- リスクモジュール（未実装でも動くように） ----------------
try:
    risk = importlib.import_module("sepa.risk")
    HAS_RISK = True
except ImportError:
    HAS_RISK = False

# --- NASDAQ100 ティッカー読み込み -----------------------------
def load_nasdaq100() -> list[str]:
    url = "https://en.wikipedia.org/wiki/Nasdaq-100"
    df = pd.read_html(url)[4]            # 5 番目のテーブル
    return df["Ticker"].tolist()


# --- リスク計算 ------------------------------------------------
def calc_risk_row(ticker: str,
                  equity: float,
                  risk_pct: float = 1.0) -> dict:
    """
    sepa.risk があれば株数などを返し、無ければプレースホルダーを返す
    """
    if not HAS_RISK:
        return {"Ticker": ticker,
                "Shares": "N/A",
                "ATR_Stop%": "N/A",
                "Risk$": "N/A",
                "Stop$": "N/A"}
    row = risk.position_size(ticker,
                             equity=equity,
                             risk_pct=risk_pct)
    return row


# --- メイン ----------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=100, help="対象銘柄数 (NASDAQ)")
    ap.add_argument("-m", type=float, default=1.1, help="ブレイク倍率")
    ap.add_argument("-equity", type=float, default=100000,
                    help="口座残高 USD")
    args = ap.parse_args()

    # 1) スクリーニング ----------------------------------------
    all_tickers = load_nasdaq100()[: args.n]
    hits_df = pp.screen(all_tickers)   
    if hits_df.empty:
        print("該当なし")
        sys.exit(0)

    hits_df.to_csv("hits.csv", index=False)
    print(hits_df)
    print("→ hits.csv 保存完了")

    # 2) チャート生成 ------------------------------------------
    charts_dir = Path("charts")
    charts_dir.mkdir(exist_ok=True)

    for tic in hits_df["Ticker"]:
        df_week = pp._fetch_price(tic)           # 週足 DataFrame
        plot_hits.plot_chart(df_week, tic)

    # 3) ポジションサイズ計算 -----------------------------------
    risk_rows = []
    for tic in hits_df["Ticker"]:
        risk_rows.append(calc_risk_row(tic,
                                       equity=args.equity,
                                       risk_pct=1.0))
    risk_df = pd.DataFrame(risk_rows)
    risk_df.to_csv("risk_plan.csv", index=False)
    print("\n--- Position Size (1 % Risk) ---")
    print(risk_df)
    print("→ risk_plan.csv 保存完了")

    print("\n=== SEPA フルパイプライン完了 ===")


if __name__ == "__main__":
    main()
