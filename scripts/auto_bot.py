#!/usr/bin/env python3
"""
auto_bot.py  (v2)

・日足／週足データ取得を data_fetcher に統一
・週足フィルター → 日足テンプレ → VCP → エントリー
・ATR×2／10EMA 割れで自動エグジット
・Alpaca Paper 発注 + SNS 投稿

※ 依存：python-dotenv, yfinance, alpaca-trade-api, requests_oauthlib
"""

from __future__ import annotations

import argparse
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
# 定数
# ─────────────────────────────────────────────
YEARS_BACK = 2
RS_LOOKBACK = 126
RISK_PER_TRADE = 0.005
ATR_MULT_EXIT = 2.0
W52 = 252

load_dotenv()


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SEPA Auto Bot")
    p.add_argument("--tickers-file", type=Path, required=True)
    p.add_argument("--cash", type=float, required=True)
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
    args = parse_args()
    tickers = load_tickers(args.tickers_file)
    print(f"Universe loaded: {len(tickers)} tickers")

    # ---- データ取得（日足） ----
    daily_dict = {
        tic: get_daily(tic, years_back=YEARS_BACK)["Close"]
        for tic in tickers
    }

    # ---- RS ----
    rs_scores = compute_rs_universe(daily_dict, lookback=RS_LOOKBACK)

    tm = TradeManager(paper=True)
    notifier = SNSNotifier()

    # ───────── ENTRY ループ ─────────
    for tic, daily_series in daily_dict.items():
        if len(daily_series) < W52 * 2:
            continue

        # 週足フィルタ
        weekly_df = to_weekly(daily_series.to_frame(name="Close"))
        w_pass = WeeklyTrendTemplate(weekly_df).passes(rs_rating=rs_scores[tic])
        if not w_pass:
            continue

        # 日足テンプレ
        pct_low = (daily_series.iloc[-1] - daily_series.rolling(W52).min().iloc[-1]) / daily_series.rolling(W52).min().iloc[-1] * 100
        pct_high = (daily_series.rolling(W52).max().iloc[-1] - daily_series.iloc[-1]) / daily_series.rolling(W52).max().iloc[-1] * 100
        d_pass = TrendTemplate(daily_series.to_frame(name="Close")).passes(
            rs_rating=rs_scores[tic],
            pct_from_low=pct_low,
            pct_from_high=pct_high,
        )
        if not d_pass:
            continue

        # VCP ブレイク
        df_daily_full = get_daily(tic, years_back=YEARS_BACK)  # OHLCV
        entry_flag, sig = VCPStrategy(df_daily_full).check_today()
        if not entry_flag or sig is None:
            continue

        # ポジションサイズ
        risk_per_share = sig.atr * 1.5
        qty = max(int(args.cash * RISK_PER_TRADE / risk_per_share), 1)

        order = OrderInfo(
            symbol=tic,
            qty=qty,
            entry_price=sig.breakout_price,
            stop_price=sig.breakout_price - risk_per_share,
        )
        tm.enter_trade(order)
        notifier.post(
            SignalMessage(
                symbol=tic,
                side="ENTRY",
                price=sig.breakout_price,
                qty=qty,
                comment="VCP breakout",
            )
        )

    # ───────── EXIT ループ ─────────
    try:
        positions = tm.api.list_positions()
    except Exception as e:
        print("Failed to fetch positions:", e)
        positions = []

    for pos in positions:
        symbol = pos.symbol
        qty = int(float(pos.qty))
        entry_price = float(pos.avg_entry_price)

        df_recent = get_daily(symbol, years_back=1).tail(90)
        if len(df_recent) < 20:
            continue

        exit_strat = ExitStrategy(df_recent, entry_price)
        if exit_strat.atr_trail(n=ATR_MULT_EXIT) or exit_strat.ema_cross():
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
