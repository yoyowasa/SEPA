"""
screener.py

週足フィルター → 日足トレンドテンプレート → RS → ファンダメンタル
の順で SEPA 条件を判定し、合格ティッカーを返す統合スクリーナー。
"""

from __future__ import annotations

import datetime as dt
from typing import List, Dict

import pandas as pd
import yfinance as yf

from sepa_trade.technical_weekly import WeeklyTrendTemplate   # ← 追加
from sepa_trade.technical import TrendTemplate
from sepa_trade.rs import compute_rs_universe
from sepa_trade.fundamentals import FundamentalFilter


class SepaScreener:
    """
    Parameters
    ----------
    tickers : list[str]
        対象ティッカー
    years_back : int, default 2
        取得年数（日足）
    rs_lookback : int, default 126
        RS レーティング用リターン日数
    """

    def __init__(
        self,
        tickers: List[str],
        years_back: int = 2,
        rs_lookback: int = 126,
    ) -> None:
        self.tickers = [t.upper() for t in tickers]
        self.years_back = years_back
        self.rs_lookback = rs_lookback
        self.price_data: Dict[str, pd.Series] = self._download_prices()

        # 52 週統計に使う
        self.W52 = 252

        # RS 計算
        self.rs_scores = compute_rs_universe(self.price_data, lookback=rs_lookback)

    # ──────────────────────────────
    # パブリック API
    # ──────────────────────────────
    def screen(self) -> List[str]:
        """SEPA 基準を満たす銘柄ティッカーを返す"""
        winners: List[str] = []

        for tic, daily_series in self.price_data.items():
            # ── 週足フィルター ─────────────────────
            week_series = (
                daily_series.to_frame(name="Close")
                .resample("W-FRI")
                .last()["Close"]
                .dropna()
            )
            w_template = WeeklyTrendTemplate(week_series.to_frame(name="Close"))
            if not w_template.passes(rs_rating=self.rs_scores[tic]):
                continue  # 週足で NG

            # ── 日足トレンドテンプレート ─────────────
            if len(daily_series) < self.W52 + 1:
                continue

            pct_from_low = (daily_series.iloc[-1] - daily_series.rolling(self.W52).min().iloc[-1]) / daily_series.rolling(self.W52).min().iloc[-1] * 100
            pct_from_high = (daily_series.rolling(self.W52).max().iloc[-1] - daily_series.iloc[-1]) / daily_series.rolling(self.W52).max().iloc[-1] * 100

            d_template = TrendTemplate(daily_series.to_frame(name="Close"))
            tech_ok = d_template.passes(
                rs_rating=self.rs_scores[tic],
                pct_from_low=pct_from_low,
                pct_from_high=pct_from_high,
            )
            if not tech_ok:
                continue  # 日足で NG

            # ── ファンダメンタル ──────────────────
            fund_filter = FundamentalFilter(tic)
            if not fund_filter.passes():
                continue

            winners.append(tic)

        return winners

    # ──────────────────────────────
    # 内部ヘルパ
    # ──────────────────────────────
    def _download_prices(self) -> Dict[str, pd.Series]:
        """yfinance で終値を取得し dict[ticker] = pd.Series を返す"""
        start = (dt.date.today() - dt.timedelta(days=self.years_back * 365)).isoformat()
        raw = yf.download(self.tickers, start=start, progress=False)
        close_df = raw["Adj Close"] if "Adj Close" in raw.columns else raw["Close"]

        # 列 MultiIndex の場合を平坦化
        if isinstance(close_df.columns, pd.MultiIndex):
            close_df.columns = close_df.columns.get_level_values(0)

        return {tic: close_df[tic].dropna() for tic in self.tickers}
