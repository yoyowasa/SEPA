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

import os
import requests
from typing import Dict, List, Tuple, Optional


class FundamentalFilter:
    """
    Parameters
    ----------
    symbol : str
        ティッカー (例: "AAPL")
    provider : str, default "fmp"
        "fmp" or "yfinance"
    limit : int, default 4
        過去何四半期ぶん取得するか
    """

    FMP_EPS_URL = (
        "https://financialmodelingprep.com/api/v3/"
        "income-statement/{symbol}?limit={limit}&apikey={key}"
    )

    FMP_MARGIN_URL = (
        "https://financialmodelingprep.com/api/v3/"
        "ratios/{symbol}?limit={limit}&apikey={key}"
    )

    def __init__(self, symbol: str, provider: str = "fmp", limit: int = 4) -> None:
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
        self._gross_margin: Optional[float] = None

    # ──────────────────────────────
    # 公開 API
    # ──────────────────────────────
    def passes(
        self,
        eps_growth_qtr_threshold: float = 25.0,
        sales_growth_qtr_threshold: float = 20.0,
        margin_improve_required: bool = True,
    ) -> bool:
        """
        SEPA のファンダ条件を満たすか判定。

        Returns
        -------
        bool
            すべての基準を満たせば True
        """
        eps_growth = self._calc_growth_rates(self.eps_quarter)
        sales_growth = self._calc_growth_rates(self.sales_quarter)

        conditions = [
            eps_growth[-1] >= eps_growth_qtr_threshold,
            sales_growth[-1] >= sales_growth_qtr_threshold,
        ]

        if margin_improve_required and self.gross_margin is not None:
            # 最新四半期の粗利率が過去平均を上回るか
            past_avg = sum(self._gross_margin_history[:-1]) / (len(self._gross_margin_history) - 1)
            conditions.append(self.gross_margin >= past_avg)

        return all(conditions)

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
    def gross_margin(self) -> Optional[float]:
        if self._gross_margin is None:
            self._fetch_financials()
        return self._gross_margin  # type: ignore

    # ──────────────────────────────
    # 内部ユーティリティ
    # ──────────────────────────────
    def _fetch_financials(self) -> None:
        """FMP から四半期 EPS、売上高、粗利率を取得してキャッシュ"""
        url = self.FMP_EPS_URL.format(symbol=self.symbol, limit=self.limit, key=self.api_key)
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # EPS, 売上 (単位: USD), 最新が 0 番目
        self._eps_quarter = [q["eps"] for q in data][: self.limit]
        self._sales_quarter = [q["revenue"] for q in data][: self.limit]

        # マージン別 API
        url_margin = self.FMP_MARGIN_URL.format(symbol=self.symbol, limit=self.limit, key=self.api_key)
        resp_m = requests.get(url_margin, timeout=15)
        resp_m.raise_for_status()
        ratios = resp_m.json()
        self._gross_margin_history = [r["grossProfitMargin"] for r in ratios][: self.limit]
        self._gross_margin = self._gross_margin_history[0] if self._gross_margin_history else None

    @staticmethod
    def _calc_growth_rates(values: List[float]) -> List[float]:
        """連続する四半期の前年比成長率 (%) を返す（最新が末尾）"""
        growth = []
        for i in range(1, len(values)):
            if values[i - 1] == 0:
                growth.append(0.0)
            else:
                growth.append((values[i - 1] - values[i]) / abs(values[i]) * 100)
        return growth[::-1]  # 最新四半期を最後に
