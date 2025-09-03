#!/usr/bin/env python3
"""
auto_bot.py  (v3)

週足フィルター → 日足トレンドテンプレート → VCP ブレイク
公式ガイドラインの **下限値** で運用する自動売買ボット。

主な調整点
-----------
* RS_THRESHOLD   : 80 → 70（WeeklyTrendTemplate 内で反映済み）
* VCP shrink     : shrink_steps 3 → 2（VCPStrategy デフォルト変更済み）
* RISK_PER_TRADE : 0.005 (0.5 %) → **0.0125 (1.25 %)**
* ATR_MULT_EXIT  : 2.0 → **1.5**（損切り幅 ≒10 %以内に収める目安）
"""

from __future__ import annotations

import argparse
import logging
import datetime as dt
from pathlib import Path
from typing import List

import pandas as pd
from dotenv import load_dotenv

from sepa_trade.data_fetcher import get_daily, to_weekly
from sepa_trade.rs import compute_rs_universe
from sepa_trade.technical_weekly import WeeklyTrendTemplate
from sepa_trade.technical import TrendTemplate
from sepa_trade.strategy.vcp_breakout import VCPStrategy
from sepa_trade.strategy.exit_rules import ExitStrategy
from sepa_trade.live.trade_manager import TradeManager, OrderInfo
from sepa_trade.utils.notifier import SNSNotifier, SignalMessage

# ─────────────────────────────────────────────
# 定数（公式下限で統一）
# ─────────────────────────────────────────────
YEARS_BACK = 2
RS_LOOKBACK = 126          # 半年
RISK_PER_TRADE = 0.0125    # 口座の 1.25 % をリスク許容
ATR_MULT_EXIT = 1.5        # ATR×1.5 ≒ 株価10%以内ストップ
W52 = 252                  # 52 週（日足換算）

load_dotenv()


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SEPA Auto Bot (official lower‑bound params)")
    p.add_argument("--tickers-file", type=Path, required=True, help="1列CSV (tickers)")
    p.add_argument("--cash", type=float, required=True, help="運用元本")
    p.add_argument("--live", action="store_true", help="本番取引モードで実行（デフォルトはペーパー）")
    return p.parse_args()


def load_tickers(path: Path) -> List[str]:
    return (
        pd.read_csv(path, header=None)
        .iloc[:, 0]
        .astype(str)
        .str.upper()
        .tolist()
    )


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    args = parse_args()
    tickers = load_tickers(args.tickers_file)
    logger.info(f"Universe: {len(tickers)} tickers from {args.tickers_file}")

    tm = TradeManager(paper=not args.live)
    notifier = SNSNotifier()

    if tm.paper:
        logger.warning("PAPER TRADING MODE: No real orders will be placed.")
    else:
        logger.warning("LIVE TRADING MODE: Real orders will be placed.")

    # ───────── 1. データ取得 & RS計算 ─────────
    logger.info("--- 1. Fetching data and computing RS ratings ---")
    ohlcv_data = {}
    for tic in tickers:
        df = get_daily(tic, YEARS_BACK)
        # 52週(252日)の計算に十分なデータを確保
        if df is not None and len(df) >= W52 + 1:
            ohlcv_data[tic] = df

    if not ohlcv_data:
        logger.warning("No tickers with sufficient data. Exiting.")
        return

    logger.info(f"  > Data loaded for {len(ohlcv_data)} tickers.")
    close_dict = {tic: df["Close"] for tic, df in ohlcv_data.items()}
    rs_scores = compute_rs_universe(close_dict, lookback=RS_LOOKBACK)
    logger.info("  > RS ratings computed.")

    # ───────── ENTRY ループ ─────────
    logger.info("--- 2. Screening for entry signals ---")
    entry_candidates: List[OrderInfo] = []
    for tic, df_full in ohlcv_data.items():
        daily_series = df_full["Close"]
        rs_rating = rs_scores.get(tic)
        if rs_rating is None:
            continue  # RS計算に失敗した銘柄はスキップ

        # 週足フィルター（RS70 下限は WeeklyTrendTemplate 内定義）
        weekly_df = to_weekly(daily_series.to_frame(name="Close"))
        if not WeeklyTrendTemplate(weekly_df).passes(rs_rating=rs_rating):
            continue

        # 日足テンプレ
        pct_low = (daily_series.iloc[-1] - daily_series.rolling(W52).min().iloc[-1]) / daily_series.rolling(W52).min().iloc[-1] * 100
        pct_high = (daily_series.rolling(W52).max().iloc[-1] - daily_series.iloc[-1]) / daily_series.rolling(W52).max().iloc[-1] * 100
        if not TrendTemplate(daily_series.to_frame(name="Close")).passes(
            rs_rating=rs_rating,
            pct_from_low=pct_low,
            pct_from_high=pct_high,
        ):
            continue

        # VCP ブレイク判定（shrink_steps=2 デフォルト）
        entry_flag, sig = VCPStrategy(df_full).check_today()
        if not entry_flag or sig is None:
            continue

        # ポジションサイズ計算
        risk_per_share = sig.atr * 1.5
        if risk_per_share <= 0:
            continue
        qty = max(int(args.cash * RISK_PER_TRADE / risk_per_share), 1)

        logger.info(f"  > ✅ Entry signal found for {tic}")
        entry_candidates.append(OrderInfo(
            symbol=tic,
            qty=qty,
            entry_price=sig.breakout_price,
            stop_price=sig.breakout_price - risk_per_share,
        ))

    # ───────── ENTRY 実行 ─────────
    if not entry_candidates:
        logger.info("  > No new entry signals found.")
    else:
        for order in entry_candidates:
            tm.enter_trade(order)
            notifier.post(
                SignalMessage(
                    symbol=order.symbol,
                    side="ENTRY",
                    price=order.entry_price,
                    qty=order.qty,
                    comment="VCP breakout",
                )
            )

    # ───────── EXIT ループ ─────────
    logger.info("--- 3. Checking for exit signals ---")
    try:
        positions = tm.api.list_positions()
        if not positions:
            logger.info("  > No open positions to check.")
            return
    except Exception as e:
        logger.error(f"  > Alpaca API error when listing positions: {e}")
        return

    for pos in positions:
        symbol = pos.symbol
        qty = int(float(pos.qty))
        entry_price = float(pos.avg_entry_price)
        logger.info(f"  > Checking exit for position: {symbol}")

        # 効率化: スクリーニングで取得済みのデータを再利用
        if symbol in ohlcv_data:
            df_recent = ohlcv_data[symbol]
        else:
            logger.info(f"    > Position {symbol} not in initial data, fetching fresh data.")
            df_recent = get_daily(symbol, years_back=1)

        if df_recent is None or len(df_recent) < 20:
            logger.warning(f"    > Insufficient data for exit check on {symbol}, skipping.")
            continue

        exit_strat = ExitStrategy(df_recent, entry_price)
        if exit_strat.atr_trail(n=ATR_MULT_EXIT) or exit_strat.ema_cross():
            logger.info(f"    > EXIT signal triggered for {symbol}. Closing position.")
            tm.exit_trade(symbol)
            notifier.post(
                SignalMessage(
                    symbol=symbol,
                    side="EXIT",
                    price=df_recent["Close"].iloc[-1],
                    qty=qty,
                    comment="ATR/EMA exit",
                )
            )


if __name__ == "__main__":
    main()
