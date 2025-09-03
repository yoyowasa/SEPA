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

import yfinance as yf
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import pandas as pd

from sepa_trade.technical_weekly import WeeklyTrendTemplate
from sepa_trade.technical import TrendTemplate
from sepa_trade.strategy.vcp_breakout import VCPStrategy

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
    # --- 戦略パラメータ ---
    ATR_MULT_EXIT = 2.0
    RISK_PER_TRADE = 0.01  # 資産の1%をリスクに晒す
    W52 = 252              # 52週の日数

    def init(self) -> None:
        """インジケータを事前に計算"""
        # ATR(10): 元のコードと同様にTrue Rangeの単純移動平均を使用
        high, low, close = self.data.High, self.data.Low, self.data.Close
        tr_df = pd.DataFrame({
            'h_l': high - low,
            'h_pc': (high - close.shift()).abs(),
            'l_pc': (low - close.shift()).abs()
        })
        true_range = tr_df.max(axis=1)
        self.atr10 = self.I(lambda x: pd.Series(x).rolling(10).mean(), true_range, name="ATR10")

        # EMA(10)
        self.ema10 = self.I(lambda x: pd.Series(x).ewm(span=10, adjust=False).mean(), self.data.Close, name="EMA10")

    def next(self) -> None:
        """各時間足で実行されるメインロジック"""
        price = self.data.Close[-1]

        # --- 1. EXITロジック ---
        # ポジションがある場合、まずエグジット条件をチェック
        if self.position:
            entry_price = self.position.avg_price
            # ATRトレイリングストップ、または終値がEMA10をクロスして下回った場合に手仕舞い
            atr_stop_price = entry_price - self.atr10[-1] * self.ATR_MULT_EXIT
            if price < atr_stop_price or crossover(self.ema10, self.data.Close):
                self.position.close()
            return

        # --- 2. ENTRYロジック ---
        # 52週分のデータがなければエントリーしない
        if len(self.data.Close) < self.W52:
            return

        # ルックアヘッドバイアスを避けるため、現在までのデータでDataFrameを作成
        current_df = self.data.df.iloc[:len(self.data)]

        # ===== 2a. 週足フィルター =====
        weekly_close = current_df["Close"].resample("W-FRI").last()
        if len(weekly_close) < 41:  # 40週MAの計算に十分な期間が必要
            return
        weekly_df = weekly_close.to_frame(name="Close")
        rs_dummy = 80  # 個別銘柄のバックテストではRSは計算困難なためダミー値を使用
        if not WeeklyTrendTemplate(weekly_df).passes(rs_rating=rs_dummy):
            return

        # ===== 2b. 日足トレンドテンプレート =====
        # 52週高値/安値からの乖離率を計算
        rolling_min_52w = current_df["Close"].rolling(self.W52).min().iloc[-1]
        rolling_max_52w = current_df["Close"].rolling(self.W52).max().iloc[-1]
        pct_from_low = (price - rolling_min_52w) / rolling_min_52w * 100
        pct_from_high = (rolling_max_52w - price) / rolling_max_52w * 100

        if not TrendTemplate(current_df[["Close"]]).passes(
            rs_rating=rs_dummy, pct_from_low=pct_from_low, pct_from_high=pct_from_high
        ):
            return

        # ===== 2c. VCP ブレイクアウト =====
        vcp = VCPStrategy(current_df)
        entry, sig = vcp.check_today()
        if entry and sig:
            # ポジションサイズを計算
            risk_per_share = sig.atr * 1.5
            if risk_per_share <= 0:
                return
            size = int(self.equity * self.RISK_PER_TRADE / risk_per_share)
            if size > 0:
                self.buy(size=size, sl=price - risk_per_share)


# ───────────────────────────────────────────
# Main
# ───────────────────────────────────────────
def main() -> None:
    args = parse_args()

    for tic in args.tickers:
        print(f"\n--- バックテスト開始: {tic} ({args.years}年分) ---")
        # auto_adjust=Trueで調整済み株価を取得
        df = yf.download(tic, period=f"{args.years}y", auto_adjust=True, progress=False)
        if df.empty or len(df) < VCPBacktestStrategy.W52:
            print(f"スキップ: データ不足 (期間: {len(df)}日)")
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
        print(stats)
        # グラフをブラウザで表示したい場合は以下のコメントを解除
        # bt.plot()


if __name__ == "__main__":
    main()
