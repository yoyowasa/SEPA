"""
fundamentals.py

Mark Minervini の SEPA 戦略で要求される
「EPS・売上高の高成長」を機械判定するモジュール。

- Financial Modeling Prep (FMP) API もしくは
  Yahoo Finance (yfinance) のファンダ API を利用して四半期データを取得
- EPS 成長率、売上高成長率、利益率を算出
- ユーザーが定めた閾値をすべて満たせば True を返す

環境変数
---------
FMP_API_KEY : str
    FMP の API キー（例: ".env" に設定）
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

logger = logging.getLogger(__name__)

class FundamentalFilter:
    """
    Parameters
    ----------
    symbol : str
        ティッカー (例: "AAPL")
    provider : str, default "fmp"
        "fmp" or "yfinance"
    limit : int, default 5
        過去何四半期ぶん取得するか。YoY成長率の計算には最低5四半期が必要。
    """

    FMP_EPS_URL = (
        "https://financialmodelingprep.com/api/v3/"
        "income-statement/{symbol}?limit={limit}&apikey={key}"
    )

    FMP_MARGIN_URL = (
        "https://financialmodelingprep.com/api/v3/"
        "ratios/{symbol}?limit={limit}&apikey={key}"
    )

    def __init__(self, symbol: str, provider: str = "fmp", limit: int = 5) -> None:
        self.symbol = symbol.upper()
        self.provider = provider
        self.limit = limit

        if provider not in {"fmp"}:
            raise ValueError("現状 provider は 'fmp' のみサポート")

        self.api_key = os.getenv("FMP_API_KEY")
        if not self.api_key:
            raise EnvironmentError("環境変数 FMP_API_KEY が設定されていません。")

        # 内部キャッシュ
        self._eps_quarter: Optional[List[float]] = None
        self._sales_quarter: Optional[List[float]] = None
        self._gross_margin_history: Optional[List[float]] = None

    # ──────────────────────────────
    # 公開 API
    # ──────────────────────────────
    def passes(
        self,
        eps_growth_qtr_threshold: float = 25.0,
        sales_growth_qtr_threshold: float = 20.0,
        margin_improves_sequentially: bool = True,
    ) -> bool:
        """
        SEPA のファンダ条件を満たすか判定。

        Parameters
        ----------
        eps_growth_qtr_threshold : float
            最新四半期のEPSのYoY成長率(%)の下限値
        sales_growth_qtr_threshold : float
            最新四半期の売上高のYoY成長率(%)の下限値
        margin_improves_sequentially : bool
            利益率が前期比で改善していることを要求するか

        Returns
        -------
        bool
            すべての基準を満たせば True
        """
        eps_growth = self._calc_yoy_growth_rates(self.eps_quarter)
        if not eps_growth or pd.isna(eps_growth[-1]) or eps_growth[-1] < eps_growth_qtr_threshold:
            return False

        sales_growth = self._calc_yoy_growth_rates(self.sales_quarter)
        if not sales_growth or pd.isna(sales_growth[-1]) or sales_growth[-1] < sales_growth_qtr_threshold:
            return False

        if margin_improves_sequentially:
            if len(self.gross_margin_history) < 2 or self.gross_margin_history[0] <= self.gross_margin_history[1]:
                return False

        return True

    # ──────────────────────────────
    # プロパティ（API アクセス）
    # ──────────────────────────────
    @property
    def eps_quarter(self) -> List[float]:
        if self._eps_quarter is None:
            self._fetch_financials()
        return self._eps_quarter  # type: ignore

    @property
    def sales_quarter(self) -> List[float]:
        if self._sales_quarter is None:
            self._fetch_financials()
        return self._sales_quarter  # type: ignore

    @property
    def gross_margin_history(self) -> List[float]:
        if self._gross_margin_history is None:
            self._fetch_financials()
        return self._gross_margin_history  # type: ignore

    # ──────────────────────────────
    # 内部ユーティリティ
    # ──────────────────────────────
    def _fetch_financials(self) -> None:
        """FMP から四半期 EPS、売上高、粗利率を取得してキャッシュ"""
        # キャッシュを空リストで初期化
        self._eps_quarter = []
        self._sales_quarter = []
        self._gross_margin_history = []

        try:
            # --- 損益計算書 (EPS, 売上) ---
            url_income = self.FMP_EPS_URL.format(
                symbol=self.symbol, limit=self.limit, key=self.api_key
            )
            resp_income = requests.get(url_income, timeout=15)
            resp_income.raise_for_status()
            income_data = resp_income.json()

            if not isinstance(income_data, list):
                logger.warning("FMPから予期せぬ形式のデータ(income)を受信: %s", self.symbol)
                return

            self._eps_quarter = [q.get("eps") for q in income_data if q.get("eps") is not None]
            self._sales_quarter = [q.get("revenue") for q in income_data if q.get("revenue") is not None]

            # --- 利益率 ---
            url_margin = self.FMP_MARGIN_URL.format(
                symbol=self.symbol, limit=self.limit, key=self.api_key
            )
            resp_margin = requests.get(url_margin, timeout=15)
            resp_margin.raise_for_status()
            margin_data = resp_margin.json()

            if not isinstance(margin_data, list):
                logger.warning("FMPから予期せぬ形式のデータ(margin)を受信: %s", self.symbol)
                return

            self._gross_margin_history = [
                r.get("grossProfitMargin") for r in margin_data if r.get("grossProfitMargin") is not None
            ]

        except requests.exceptions.RequestException as e:
            logger.error("FMP APIへのリクエストに失敗: %s, %s", self.symbol, e)
        except (KeyError, IndexError, TypeError) as e:
            logger.error("FMP APIレスポンスの解析に失敗: %s, %s", self.symbol, e)

    @staticmethod
    def _calc_yoy_growth_rates(values: Optional[List[float]]) -> List[float]:
        """
        四半期データのリストから前年同期比 (YoY) 成長率のリストを計算する。
        入力リストは最新の四半期が先頭にあることを前提とする。
        出力リストは最新の成長率が末尾に来るように並べられる。
        """
        if not values or len(values) < 5:
            return []

        s = pd.Series(values, dtype=float)
        yoy_growth = (s / s.shift(-4) - 1) * 100
        return yoy_growth.dropna().tolist()[::-1]
