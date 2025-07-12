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
    print(f"Universe: {len(tickers)} tickers")

    # 日足取得 & RS 計算
    daily_dict = {tic: get_daily(tic, YEARS_BACK)["Close"] for tic in tickers}
    rs_scores = compute_rs_universe(daily_dict, lookback=RS_LOOKBACK)

    tm = TradeManager(paper=True)
    notifier = SNSNotifier()

    # ───────── ENTRY ループ ─────────
    for tic, daily_series in daily_dict.items():
        if len(daily_series) < W52 * 2:
            continue

        # 週足フィルター（RS70 下限は WeeklyTrendTemplate 内定義）
        weekly_df = to_weekly(daily_series.to_frame(name="Close"))
        if not WeeklyTrendTemplate(weekly_df).passes(rs_rating=rs_scores[tic]):
            continue

        # 日足テンプレ
        pct_low = (daily_series.iloc[-1] - daily_series.rolling(W52).min().iloc[-1]) / daily_series.rolling(W52).min().iloc[-1] * 100
        pct_high = (daily_series.rolling(W52).max().iloc[-1] - daily_series.iloc[-1]) / daily_series.rolling(W52).max().iloc[-1] * 100
        if not TrendTemplate(daily_series.to_frame(name="Close")).passes(
            rs_rating=rs_scores[tic],
            pct_from_low=pct_low,
            pct_from_high=pct_high,
        ):
            continue

        # VCP ブレイク判定（shrink_steps=2 デフォルト）
        df_full = get_daily(tic, YEARS_BACK)  # OHLCV
        entry_flag, sig = VCPStrategy(df_full).check_today()
        if not entry_flag or sig is None:
            continue

        # ポジションサイズ計算
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
        print("Alpaca API error:", e)
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
