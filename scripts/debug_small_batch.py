#!/usr/bin/env python3
"""
debug_small_batch.py

・ユニバースを少数（例：NASDAQ100）に限定
・並列を使わず逐次処理で各フィルタの通過可否を print
   1) Stage‑2 (週足テンプレ)
   2) 日足テンプレ
   3) VCP ブレイク
最終的に Trades が 0 になる原因を特定するためのデバッグ用。

使い方例:
    poetry run python scripts/debug_small_batch.py --years 5
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd
import yfinance as yf

from sepa_trade.technical_weekly import WeeklyTrendTemplate
from sepa_trade.technical import TrendTemplate
from sepa_trade.strategy.vcp_breakout import VCPStrategy
from sepa_trade.rs import compute_rs_universe

RAW_DIR = Path("data/raw")
NDX_CSV = RAW_DIR / "nasdaq.csv"    # 事前に作成しておく


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Debug SEPA pipeline on small universe")
    p.add_argument("--years", type=int, default=5, help="過去データ年数")
    return p.parse_args()


def load_nasdaq100() -> list[str]:
    if not NDX_CSV.exists():
        raise FileNotFoundError(f"{NDX_CSV} がありません。先に CSV を用意してください。")
    return (
        pd.read_csv(NDX_CSV, header=None)[0]
        .astype(str)
        .str.upper()
        .tolist()
    )


def main() -> None:
    args = parse_args()
    tickers = load_nasdaq100()
    print(f"▶︎ NASDAQ100 デバッグ開始 ({len(tickers)} tickers)")

    # ─────────────────────────────
    # 1) RS 計算用データの取得
    #    ─ 欠損・期間不足の銘柄はここで除外
    # ─────────────────────────────
    lookback = 126
    closes: dict[str, pd.Series] = {}

    for tic in tickers:
        series = yf.download(
            tic, period=f"{args.years}y", progress=False
        )["Close"]

        # lookback+1 本より短い、または全 NaN → スキップ
        if len(series.dropna()) < lookback + 1:
            print(f"{tic:6} : データ不足 skip")
            continue

        closes[tic] = series

    # 有効銘柄が 0 の場合は終了
    if not closes:
        print("有効な銘柄がありません。")
        return

    # 1) RS スコア計算を個別に置き換え
    pct_ret = {
        tic: float((s.iloc[-1] / s.iloc[-lookback - 1] - 1) * 100)
        for tic, s in closes.items()
    }
    rs_scores = (
        pd.Series(pct_ret, dtype="float64")
        .dropna()
        .rank(pct=True) * 100
    )

    # ─────────────────────────────
    # 2) フィルタごとのカウンタ
    # ─────────────────────────────
    cnt_stage2 = 0
    cnt_daily  = 0
    cnt_vcp    = 0

    # ★★★ ここで失敗理由カウンタを用意 ★★★
    fail_cnt = {
        "rs": 0,
        "ma_order": 0,
        "ma40_slope": 0,
        "pct_from_low": 0,
        "pct_from_high": 0,
    }

    for tic, close in closes.items():
        # ……(DataFrame → Series 統一の処理はそのまま)……
        # ---- Stage‑2 判定 ----
        # 旧:
        # weekly = close.resample("W-FRI").last()....

        # 新: dropna 後、改めて DataFrame 化して wt を作成

        # ---- Stage‑2 判定 ----
        # 週足終値を取得し、必ず「Close」1 列の DataFrame に統一
        weekly_raw = close.resample("W-FRI").last().ffill()   # 前週値で欠損補完

        # ① Series → DataFrame 化
        if isinstance(weekly_raw, pd.Series):
            weekly = weekly_raw.to_frame(name="Close")

        # ② DataFrame の場合
        else:
            # MultiIndex → 先頭レベルを平坦化
            if isinstance(weekly_raw.columns, pd.MultiIndex):
                weekly_raw.columns = weekly_raw.columns.get_level_values(0)

            cols = list(weekly_raw.columns)

            # “Close” があれば採用
            if "Close" in cols:
                weekly = weekly_raw[["Close"]]

            # “Adj Close” だけある場合 → Rename
            elif "Adj Close" in cols:
                weekly = weekly_raw[["Adj Close"]].rename(
                    columns={"Adj Close": "Close"}
                )

            # “Close_x” “Close_y” など suffix 付き → 最初に見つかったものを流用
            elif any(c.startswith("Close") for c in cols):
                use_col = [c for c in cols if c.startswith("Close")][0]
                weekly = weekly_raw[[use_col]].rename(columns={use_col: "Close"})

            # それ以外はスキップしてカウント
            else:
                print(f"{tic:6}: Close 列なし skip (columns={cols})")
                fail_cnt["ma_order"] += 1
                continue

        # WeeklyTrendTemplate 判定に進む
        wt = WeeklyTrendTemplate(weekly)





        # ─── 各条件ごとに if → continue ───
        if rs_scores[tic] < wt.RS_THRESHOLD:
            fail_cnt["rs"] += 1
            continue

        # ma_order 判定ブロック
        if not (close.iloc[-1] > wt.ma30.iloc[-1] > wt.ma40.iloc[-1]
                and close.iloc[-1] > wt.ma10.iloc[-1]):
            fail_cnt["ma_order"] += 1

            # << ここを絶対に実行させる >>
            print(f"\nDEBUG {tic}:")
            print(" price :", close.iloc[-1])
            print(" ma10  :", wt.ma10.iloc[-1])
            print(" ma30  :", wt.ma30.iloc[-1])
            print(" ma40  :", wt.ma40.iloc[-1])

            continue

        if not (wt.ma40.iloc[-1] > wt.ma40.iloc[-4]):
            fail_cnt["ma40_slope"] += 1
            continue

        pct_from_low = (close.iloc[-1] - close.min()) / close.min() * 100
        if pct_from_low < wt.PCT_FROM_LOW_MIN:
            fail_cnt["pct_from_low"] += 1
            continue

        pct_from_high = (close.max() - close.iloc[-1]) / close.max() * 100
        if pct_from_high > wt.PCT_FROM_HIGH_MAX:
            fail_cnt["pct_from_high"] += 1
            continue

        # ここまで全部通過で Stage‑2 合格
        cnt_stage2 += 1
        # ---- 日足テンプレ判定 ----
        pct_from_low = (
            (close.iloc[-1] - close.rolling(252).min().iloc[-1])
            / close.rolling(252).min().iloc[-1]
            * 100
        )
        pct_from_high = (
            (close.rolling(252).max().iloc[-1] - close.iloc[-1])
            / close.rolling(252).max().iloc[-1]
            * 100
        )
        if not TrendTemplate(close.to_frame(name="Close")).passes(
            rs_rating=rs_scores[tic],
            pct_from_low=pct_from_low,
            pct_from_high=pct_from_high,
        ):
            print(f"{tic:6} : 日足テンプレ不合格")
            continue
        cnt_daily += 1

        # ---- VCP ブレイク判定 ----
        ohlcv = yf.download(
            tic, period=f"{args.years}y", progress=False
        )
        entry_flag, _ = VCPStrategy(ohlcv).check_today()
        if not entry_flag:
            print(f"{tic:6} : VCP ブレイク無し")
            continue
        cnt_vcp += 1
        print(f"{tic:6} : ✅ VCP ブレイク → エントリー候補")

    # ───────── 集計結果 ─────────
    print("\n==== Stage‑2 不合格 内訳 ====")
    for k, v in fail_cnt.items():
        print(f"{k:14}: {v}")

    print("\n==== 集計結果 ====")
    print(f"Stage‑2 合格   : {cnt_stage2}")
    print(f"日足テンプレ合格: {cnt_daily}")
    print(f"VCP ブレイク   : {cnt_vcp}")




if __name__ == "__main__":
    main()
