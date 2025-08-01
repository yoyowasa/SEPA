
"""
batch_backtest.py

S&P500 など数百ティッカーを並列にバックテストし、
結果を CSV にまとめるユーティリティ。

例)
    poetry run python scripts/batch_backtest.py \
        --tickers-file data/raw/sp500.csv \
        --years 5 --processes 8
"""

from __future__ import annotations

import argparse
import datetime as dt
import multiprocessing as mp
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf
from backtesting import Backtest, Strategy
from backtesting.lib import crossover

from sepa_trade.technical_weekly import WeeklyTrendTemplate
from sepa_trade.technical import TrendTemplate
from sepa_trade.rs import compute_rs_universe
from sepa_trade.strategy.vcp_breakout import VCPStrategy
from sepa_trade.strategy.exit_rules import ExitStrategy
# 既存 import 群の末尾あたり
from sepa_trade.utils.timeframe import load_daily       # ← 追加
from sepa_trade.utils.timeframe import daily_to_weekly
from sepa_trade.utils.timeframe import (
    load_daily, daily_to_weekly, debug_print_weekly_ma  # ← 追記
)
from sepa_trade.rs import compute_rs_universe
# 既存 import 群のあと
stage2_pass = 0        # 週足テンプレ合格
daily_pass  = 0        # 日足テンプレ合格
vcp_pass    = 0        # VCP ブレイク発生

# Strategy クラス（ティッカーごと再利用）
# ───────────────────────────────────────────
class VCPBacktestStrategy(Strategy):
    ATR_EXIT_MULT = 2.0

    def init(self) -> None:
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

        # キャッシュ用
        self.weekly_template_cache: Optional[WeeklyTrendTemplate] = None
        self.daily_template_cache: Optional[TrendTemplate] = None

    def next(self) -> None:
        price = self.data.Close[-1]
        df = self.data.df

        # Exit 条件
        if self.position:
            entry_price = self.position.avg_price
            exit_strat = ExitStrategy(df.tail(60), entry_price)
            if (
                price < entry_price - self.atr10[-1] * self.ATR_EXIT_MULT
                or crossover(self.ema10, self.data.Close)
                or exit_strat.ema_cross()
            ):
                self.position.close()
            return

        # 週足フィルター
        weekly = daily_to_weekly(self.close_series)   # ← これで OK

        if self.weekly_template_cache is None:
            self.weekly_template_cache = WeeklyTrendTemplate(weekly)
        if not self.weekly_template_cache.passes(rs_rating=80):
            return

        # 日足テンプレ
        d_template = self.daily_template_cache
        if d_template is None:
            d_template = TrendTemplate(df["Close"].to_frame(name="Close"))
            self.daily_template_cache = d_template

        W52 = 252
        pct_low = (price - df["Close"].rolling(W52).min().iloc[-1]) / df["Close"].rolling(
            W52
        ).min().iloc[-1] * 100
        pct_high = (
            df["Close"].rolling(W52).max().iloc[-1] - price
        ) / df["Close"].rolling(W52).max().iloc[-1] * 100

        if not d_template.passes(rs_rating=80, pct_from_low=pct_low, pct_from_high=pct_high):
            return

        # VCP ブレイク
        vcp = VCPStrategy(df)
        entry, sig = vcp.check_today()
        if entry and sig:
            risk_per_share = sig.atr * 1.5
            size = int(self.equity * 0.01 / risk_per_share)
            if size > 0:
                self.buy(size=size, sl=price - risk_per_share)


# ───────────────────────────────────────────
# CLI
# ───────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Batch VCP backtest")
    p.add_argument("--tickers-file", type=Path, required=True, help="1列CSV")
    p.add_argument("--years", type=int, default=5)
    p.add_argument("--processes", type=int, default=mp.cpu_count() - 1)
    return p.parse_args()


def load_tickers(path: Path) -> List[str]:
    return (
        pd.read_csv(path, header=None)
        .iloc[:, 0]
        .astype(str)
        .str.upper()
        .tolist()
    )


# ───────────────────────────────────────────
# バックテスト 1 銘柄
# ───────────────────────────────────────────
def run_backtest(ticker: str, years: int) -> Dict[str, float]:
    """
    1 銘柄の VCP バックテストを実行。
    フィルタをどこまで通過したかをカウントする。
    """
    try:
        df = load_daily(ticker, years)

        # Close 抽出 ― 小文字や Close_x も許容
        if "Close" in df.columns:
            close_series = df["Close"].squeeze()
        else:
            close_series = (
                df.filter(regex="close", case=False).iloc[:, 0].squeeze()
            )
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0] # 単一列に変換       

        # 週足 DataFrame
        weekly = daily_to_weekly(close_series)
        if ticker in ("AAPL", "NVDA"):          # ← 好きな銘柄で
            debug_print_weekly_ma(ticker, weekly)
        if ticker == "AAPL":                    # 見たい銘柄を指定
            rs = compute_rs_universe({"AAPL": close}, lookback=126)
            print("\nRS 分布概要\n", pd.Series(rs).describe())
    except Exception as e:
        print(f"{ticker:6}: データ取得失敗 → skip ({e})")
        return {"Ticker": ticker, "Trades": 0}

    # ── Stage-2 週足テンプレ（★ rs_rating を 80→70 に緩和して様子を見る）
    wt = WeeklyTrendTemplate(weekly)
    if not wt.passes(rs_rating=70):                       # --► 変更点
        return {"Ticker": ticker, "Trades": 0}

    global stage2_pass
    stage2_pass += 1

    # ── 日足テンプレ
    d_template = TrendTemplate(close_series.to_frame(name="Close"))


    # --- 52 週高値･安値との距離を計算するブロック ----
    W52 = 252
    pct_low  = (close_series.iloc[-1] - close_series.rolling(W52).min().iloc[-1]) \
            / close_series.rolling(W52).min().iloc[-1] * 100                 # ← close→close_series

    pct_high = (close_series.rolling(W52).max().iloc[-1] - close_series.iloc[-1]) \
            / close_series.rolling(W52).max().iloc[-1] * 100                 # ← close→close_series


    # ★ pct_from_high を −25 → −35 に緩和（25% 以内→35% 以内）
    if not d_template.passes(rs_rating=70,
                             pct_from_low=pct_low,
                             pct_from_high=min(pct_high, 35)):
        return {"Ticker": ticker, "Trades": 0}

    global daily_pass
    daily_pass += 1

    # ── VCP ブレイク
    vcp = VCPStrategy(df)
    entry, sig = vcp.check_today()
    if not (entry and sig):
        return {"Ticker": ticker, "Trades": 0}

    global vcp_pass
    vcp_pass += 1

    # ── Backtest 実行（省略なし）
    bt = Backtest(
        df[["Open", "High", "Low", "Close", "Volume"]],
        VCPBacktestStrategy,
        cash=100_000,
        commission=0.001,
        trade_on_close=True,
        exclusive_orders=True,
    )
    stats = bt.run()

    return {
        "Ticker":      ticker,
        "Return [%]":  stats["Return [%]"],
        "WinRate [%]": stats["Win Rate [%]"],
        "MaxDD [%]":   stats["Max. Drawdown [%]"],
        "Trades":      stats["# Trades"],
    }




# ───────────────────────────────────────────
# メイン
# ───────────────────────────────────────────
def main() -> None:
    args = parse_args()
    tickers = load_tickers(args.tickers_file)
    print(f"Backtesting {len(tickers)} tickers ...")

    with mp.Pool(processes=args.processes) as pool:
        results = pool.starmap(run_backtest, [(tic, args.years) for tic in tickers])

    df_res = pd.DataFrame(results).fillna(0)
    df_res = df_res[df_res["Trades"] > 0]
    if df_res.empty:
        print("▶ バックテスト成功銘柄が 0 件でした。")
        return
    today = dt.date.today().strftime("%Y%m%d")
    out_dir = Path("results")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"vcp_backtest_{today}.csv"
    df_res.to_csv(out_path, index=False)

    # 上位 20 を表示
    top20 = (
        df_res[df_res["Trades"] > 0]
        .sort_values("Return [%]", ascending=False)
        .head(20)
    )
    print("\n===== TOP 20 by Return [%] =====")
    print(top20.to_string(index=False))

    print(f"\nSaved full results to {out_path}")
    print("\n---- フィルタ通過数 ----")
    print(f"Stage-2   : {stage2_pass}")
    print(f"日足テンプレ: {daily_pass}")
    print(f"VCP       : {vcp_pass}")


if __name__ == "__main__":
    main()
