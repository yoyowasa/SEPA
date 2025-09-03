#!/usr/bin/env python3
"""
batch_backtest.py

指定されたティッカーリストに対して、VCPバックテスト戦略を並列実行し、
結果を集計して CSV に保存するスクリプト。

`backtest_vcp.py` のロジックを多数の銘柄で効率的に検証することを目的とします。
"""

from __future__ import annotations

import datetime as dt
import logging
import argparse
import multiprocessing as mp
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf
from backtesting import Backtest

from scripts.backtest_vcp import VCPBacktestStrategy

# ───────────────────────────────────────────
#  ヘルパ
# ───────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--tickers-file", type=Path, required=True)
    p.add_argument("--years", type=int, default=2)
    p.add_argument("--processes", type=int, default=4)
    return p.parse_args()

def load_tickers(path: Path) -> List[str]:
    """Loads tickers from a single-column CSV file."""
    return (
        pd.read_csv(path, header=None)
        .iloc[:, 0]
        .astype(str)
        .str.strip()
        .str.upper()
        .tolist()
    )

# ───────────────────────────────────────────
#  1 銘柄バックテスト
# ───────────────────────────────────────────

def run_backtest(ticker: str, years: int) -> Optional[Dict[str, float]]:
    """
    1銘柄に対して VCPBacktestStrategy を実行し、統計情報を辞書で返す。
    データ不足やエラーの場合は None を返す。
    """
    try:
        # backtest_vcp.py と同じ方法でデータを取得
        df = yf.download(ticker, period=f"{years}y", auto_adjust=True, progress=False)
        if df.empty or len(df) < VCPBacktestStrategy.W52:
            return None

        bt = Backtest(
            df,
            VCPBacktestStrategy,
            cash=100_000,
            commission=0.001,
            trade_on_close=True,
            exclusive_orders=True,
        )
        stats = bt.run()

        # 結果を整形して返す
        result = {
            "Ticker":      ticker,
            "Return [%]":  stats["Return [%]"],
            "WinRate [%]": stats["Win Rate [%]"],
            "MaxDD [%]":   stats["Max. Drawdown [%]"],
            "Trades":      stats["# Trades"],
        }
        return result

    except Exception as e:
        # エラーが発生した場合はスキップ
        # print(f"Error processing {ticker}: {e}") # デバッグ用に残しても良い
        return None

# ───────────────────────────────────────────
#  メイン処理
# ───────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    args = parse_args()
    tickers = load_tickers(args.tickers_file)
    logger.info(
        f"Starting backtest for {len(tickers)} tickers over {args.years} years "
        f"using {args.processes} processes..."
    )

    with mp.Pool(processes=args.processes) as pool:
        # run_backtestがNoneを返す可能性があるので、結果をフィルタリング
        raw_results = pool.starmap(run_backtest, [(tic, args.years) for tic in tickers])
        results = [r for r in raw_results if r is not None]

    if not results:
        logger.warning("No backtests finished successfully.")
        return

    df_res = pd.DataFrame(results).fillna(0)
    df_res = df_res[df_res["Trades"] > 0].reset_index(drop=True)
    if df_res.empty:
        logger.info("▶ No tickers resulted in any trades.")
        return

    today = dt.date.today().strftime("%Y%m%d")
    out_path = Path("results") / f"vcp_backtest_{today}.csv"
    out_path.parent.mkdir(exist_ok=True)
    df_res.to_csv(out_path, index=False)

    logger.info(f"Completed {len(results)} backtests. Found {len(df_res)} tickers with trades.")

    # 上位 20 を表示
    print("\n===== TOP 20 by Return [%] =====")
    print(df_res.sort_values("Return [%]", ascending=False).head(20).to_string(index=False))

    print("\n===== Overall Statistics (for tickers with trades) =====")
    summary = df_res.describe()
    print(summary[["Return [%]", "WinRate [%]", "MaxDD [%]", "Trades"]].to_string())

    logger.info(f"\nSaved full results to {out_path}")


if __name__ == "__main__":
    main()
