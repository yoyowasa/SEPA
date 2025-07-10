#!/usr/bin/env python3
"""
backtest_vcp.py

Backtesting.py ライブラリを用いて
週足フィルター＋日足トレンドテンプレート＋VCP ブレイクアウト
＋ATR/EMA エグジット を検証するシンプルなバックテスト。

必要ライブラリ
    poetry add backtesting matplotlib

使い方例
    poetry run python scripts/backtest_vcp.py AAPL MSFT NVDA --years 5
"""

from __future__ import annotations

import argparse
import datetime as dt
from typing import List

import yfinance as yf
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import pandas as pd

from sepa_trade.technical_weekly import WeeklyTrendTemplate
from sepa_trade.technical import TrendTemplate
from sepa_trade.rs import compute_rs_universe
from sepa_trade.strategy.vcp_breakout import VCPStrategy
from sepa_trade.strategy.exit_rules import ExitStrategy

# ───────────────────────────────────────────
# CLI
# ───────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="VCP strategy backtest")
    p.add_argument("tickers", nargs="+", help="ティッカー一覧")
    p.add_argument("--years", type=int, default=5, help="取得年数")
    return p.parse_args()


# ───────────────────────────────────────────
# Strategy クラス
# ───────────────────────────────────────────
class VCPBacktestStrategy(Strategy):
    ATR_MULT_EXIT = 2.0

    def init(self) -> None:
        # ATR(10) と EMA10 を事前計算
        high = pd.Series(self.data.High)
        low = pd.Series(self.data.Low)
        close = pd.Series(self.data.Close)
        tr = pd.concat(
            [
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs(),
            ],
            axis=1,
        ).max(axis=1)
        self.atr10 = self.I(lambda x: x.rolling(10).mean(), tr)
        self.ema10 = self.I(lambda x: x.ewm(span=10, adjust=False).mean(), close)

    def next(self) -> None:
        price = self.data.Close[-1]

        # エントリー済み: EXIT 判定
        if self.position:
            entry_price = self.position.avg_price
            if (
                price < entry_price - self.atr10[-1] * self.ATR_MULT_EXIT
                or crossover(self.ema10, self.data.Close)
            ):
                self.position.close()
            return

        # ===== 週足フィルター =====
        df = self.data.df
        weekly = df["Close"].resample("W-FRI").last().to_frame(name="Close")
        rs = 80  # ダミー高 RS（個別銘柄で計算省略）
        w_ok = WeeklyTrendTemplate(weekly).passes(rs_rating=rs)
        if not w_ok:
            return

        # ===== 日足テンプレ =====
        d_template = TrendTemplate(df["Close"].to_frame(name="Close"))
        pct_low = (price - df["Close"].rolling(52 * 5).min().iloc[-1]) / df["Close"].rolling(52 * 5).min().iloc[-1] * 100
        pct_high = (df["Close"].rolling(52 * 5).max().iloc[-1] - price) / df["Close"].rolling(52 * 5).max().iloc[-1] * 100
        if not d_template.passes(rs_rating=rs, pct_from_low=pct_low, pct_from_high=pct_high):
            return

        # ===== VCP ブレイク =====
        vcp = VCPStrategy(df)
        entry, sig = vcp.check_today()
        if entry and sig:
            size = int(self.equity * 0.01 / (sig.atr * 1.5))
            if size > 0:
                self.buy(size=size, sl=price - sig.atr * 1.5)


# ───────────────────────────────────────────
# Main
# ───────────────────────────────────────────
def main() -> None:
    args = parse_args()
    start = dt.date.today() - dt.timedelta(days=365 * args.years)

    for tic in args.tickers:
        df = yf.download(tic, start=start.isoformat(), auto_adjust=False)
        if len(df) < 200:
            print(f"Skip {tic}: insufficient data")
            continue

        bt = Backtest(
            df,
            VCPBacktestStrategy,
            cash=100_000,
            commission=0.001,
            exclusive_orders=True,
            trade_on_close=True,
        )
        stats = bt.run()
        print(f"=== {tic} ===")
        print(stats[["Return [%]", "Win Rate [%]", "Max. Drawdown [%]"]])
        # グラフを見たい場合: bt.plot()


if __name__ == "__main__":
    main()
