"""
screener.py

週足フィルター → 日足トレンドテンプレート → RS → ファンダメンタル
の順で SEPA 条件を判定し、合格ティッカーを返す統合スクリーナー。
"""

from __future__ import annotations

import logging
from typing import List, Dict

import pandas as pd
from tqdm import tqdm

from sepa_trade.data_fetcher import get_daily, to_weekly
from sepa_trade.fundamentals import FundamentalFilter
from sepa_trade.rs import compute_rs_universe
from sepa_trade.technical import TrendTemplate
from sepa_trade.technical_weekly import WeeklyTrendTemplate

logger = logging.getLogger(__name__)

class SepaScreener:
    """
    Parameters
    ----------
    tickers : list[str]
        スクリーニング対象のティッカーリスト
    config : dict
        スクリーニングの各種パラメータを格納した辞書
    """

    def __init__(
        self,
        tickers: List[str],
        config: Dict,
    ) -> None:
        self.tickers = [t.upper() for t in tickers]
        self.config = config
        self.price_data: Dict[str, pd.DataFrame] = {}
        self.rs_scores: Dict[str, float] = {}

    # ──────────────────────────────
    # パブリック API
    # ──────────────────────────────
    def screen(self) -> List[str]:
        """SEPA 基準を満たす銘柄ティッカーを返す"""
        self._prepare_data()  # 実際の処理の直前に重い処理を実行

        winners: List[str] = []
        logger.info(f"Screening {len(self.tickers)} tickers...")

        for tic in tqdm(self.tickers, desc="Screening Tickers"):
            try:
                # データやRSスコアがない場合はスキップ
                if tic not in self.price_data or tic not in self.rs_scores or pd.isna(self.rs_scores[tic]):
                    logger.debug(f"[{tic}] Skipping due to missing data or RS score.")
                    continue

                daily_df = self.price_data[tic]
                rs_rating = self.rs_scores[tic]

                # ── 0. RSレーティング フィルター ──────────
                min_rs = self.config.get("min_rs_rating", 70)
                if rs_rating < min_rs:
                    continue

                # ── 1. 週足フィルター ─────────────────────
                weekly_df = to_weekly(daily_df)
                if not WeeklyTrendTemplate(weekly_df).passes():
                    logger.debug(f"[{tic}] Failed weekly filter.")
                    continue

                # ── 2. 日足トレンドテンプレート ─────────────
                if len(daily_df) < 252:
                    logger.debug(f"[{tic}] Insufficient daily data for TrendTemplate.")
                    continue

                tech_filters = self.config.get("technical_filters", {})
                if not TrendTemplate(daily_df).passes(
                    ma200_lookback=tech_filters.get("ma200_lookback", 30)
                ):
                    logger.debug(f"[{tic}] Failed daily trend template.")
                    continue

                # ── 3. ファンダメンタル ──────────────────
                funda_filters = self.config.get("fundamental_filters", {})
                if not FundamentalFilter(tic).passes(**funda_filters):
                    logger.debug(f"[{tic}] Failed fundamental filter.")
                    continue

                logger.info(
                    f"✅ [{tic}] Passed all filters with RS Rating: {rs_rating:.0f}"
                )
                winners.append(tic)

            except Exception as e:
                logger.error(f"Error screening {tic}: {e}", exc_info=True)
                continue

        return winners

    # ──────────────────────────────
    # 内部ヘルパ
    # ──────────────────────────────
    def _prepare_data(self) -> None:
        """
        データ取得とRS計算を実行する。既にデータがあれば何もしない。
        """
        if self.price_data and self.rs_scores:
            return
        self.price_data = self._fetch_all_prices(self.config.get("years_back", 2))
        close_dict = {tic: df["Close"] for tic, df in self.price_data.items()}
        self.rs_scores = compute_rs_universe(close_dict, lookback=self.config.get("rs_lookback", 126))

    def _fetch_all_prices(self, years_back: int) -> Dict[str, pd.DataFrame]:
        """data_fetcher を使って全ティッカーの OHLCV を取得"""
        data = {}
        logger.info(f"Fetching price data for {len(self.tickers)} tickers...")
        for tic in tqdm(self.tickers, desc="Fetching Prices"):
            df = get_daily(tic, years_back=years_back)
            if df is not None and not df.empty:
                data[tic] = df
        return data
