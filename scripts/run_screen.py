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
import csv
import datetime as dt
from pathlib import Path
from typing import List
from dotenv import load_dotenv
load_dotenv()            # ← .env があれば自動で環境変数に展開

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


def load_tickers_from_csv(path: Path) -> List[str]:
    tickers: List[str] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if row:
                tickers.append(row[0].strip())
    return tickers


def main() -> None:
    args = parse_args()

    if args.tickers_file:
        universe = load_tickers_from_csv(args.tickers_file)
    elif args.tickers:
        universe = args.tickers
    else:
        raise SystemExit("エラー: ティッカーを指定するか --tickers-file を渡してください。")

    print(f"Universe Size: {len(universe)} tickers")
    screener = SepaScreener(universe)
    winners = screener.screen()

    # 表示
    if winners:
        print("=== SEPA 条件を満たした銘柄 ===")
        print(", ".join(winners))
    else:
        print("該当なし")

    # CSV 保存
    args.output.parent.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["generated_at", timestamp])
        writer.writerow(winners)

    print(f"\n結果を {args.output} に保存しました。")


if __name__ == "__main__":
    main()
