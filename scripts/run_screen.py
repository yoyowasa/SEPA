#!/usr/bin/env python3
"""
run_screen.py

SEPA スクリーナーを実行し、基準を満たした銘柄リストを
コンソール表示＆CSV 保存するワンショット CLI スクリプト。

使い方::
    # 例: S&P500 ティッカーをファイルから読み込み
    python scripts/run_screen.py --tickers-file data/raw/sp500.csv

    # 例: ティッカーを直接指定
    python scripts/run_screen.py AAPL MSFT NVDA TSLA
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path
from typing import List

import pandas as pd
from dotenv import load_dotenv
load_dotenv()  # .env があれば自動で環境変数に展開

from sepa_trade.pipeline.screener import SepaScreener


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run SEPA screener")
    p.add_argument(
        "tickers",
        nargs="*",
        help="ティッカーを空白区切りで指定 (例: AAPL MSFT)",
    )
    p.add_argument(
        "--tickers-file",
        type=Path,
        help="ティッカーを 1 列 CSV で渡す場合のファイルパス",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/sepa_candidates.csv"),
        help="結果を保存する CSV パス",
    )
    return p.parse_args()


def load_tickers(path: Path) -> List[str]:
    """Loads tickers from a single-column CSV file, cleaning them up."""
    return (
        pd.read_csv(path, header=None)
        .iloc[:, 0]
        .astype(str)
        .str.strip()
        .str.upper()
        .tolist()
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    args = parse_args()

    if args.tickers_file:
        universe = load_tickers(args.tickers_file)
    elif args.tickers:
        universe = args.tickers
    else:
        logger.error("エラー: ティッカーを直接指定するか --tickers-file を使用してください。")
        raise SystemExit(1)

    logger.info(f"Universe Size: {len(universe)} tickers")
    screener = SepaScreener(universe)
    winners = screener.screen()

    # 表示
    if winners:
        logger.info("=== SEPA 条件を満たした銘柄 ===")
        logger.info(", ".join(winners))
    else:
        logger.info("該当なし")

    # CSV 保存
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df_winners = pd.DataFrame(winners, columns=["ticker"])
    df_winners.to_csv(args.output, index=False)

    logger.info(f"\n結果を {args.output} に保存しました。")


if __name__ == "__main__":
    main()
