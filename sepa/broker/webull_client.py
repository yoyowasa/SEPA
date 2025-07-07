"""WebullClient — screening_results.csv を紙トレ発注する薄ラッパー
------------------------------------------------------------------
使い方:
    >>> from sepa.broker.webull_client import WebullClient
    >>> client = WebullClient(paper=True)          # 紙トレ限定
    >>> res = client.place_orders_from_csv(
    ...     "data/screening_results.csv",
    ...     capital=1_000_000,         # ポジションサイズ計算用
    ... )
    >>> print(res)
依存: pandas, httpx (実注文時に使用), logging
------------------------------------------------------------------
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

try:
    import httpx  # 実注文 API 用（紙トレ時は未使用）
except ModuleNotFoundError:  # pytest だけなら入っていなくても構わない
    httpx = None  # type: ignore


class WebullClient:
    """
    Webull の紙トレード注文をサポートするクライアント。

    Parameters
    ----------
    paper : bool, default True
        True なら紙トレモード。False（＝実注文）は未実装。
    logger : logging.Logger | None
        ロガーを外から注入したい場合に指定。
    """

    ENDPOINT_PAPER = "https://localhost/mock-webull/paper"  # 実装時に適宜変更

    def __init__(self, *, paper: bool = True, logger: Optional[logging.Logger] = None) -> None:
        self.paper = paper
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        # 実注文時のみ httpx クライアントを生成
        self._http = httpx.Client(timeout=10.0) if (httpx and not paper) else None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def place_orders_from_csv(
        self,
        csv_path: str | Path,
        *,
        account_id: Optional[str] = None,
        dry_run: bool = True,
        capital: float = 1_000_000.0,
        risk_perc_default: float = 1.0,
    ) -> List[Dict[str, Any]]:
        """
        screening_results.csv を読み込み、各行の銘柄を紙トレ注文する
        （または dry-run シミュレーション）。

        Parameters
        ----------
        csv_path : str | Path
            screening_results.csv のパス
        account_id : str | None, default None
            将来の実注文用アカウント ID（紙トレ時は無視）
        dry_run : bool, default True
            True なら API 送信せずペイロードだけ生成
        capital : float, default 1_000_000
            ポジションサイズ計算に使う総資金（円 または USD）
        risk_perc_default : float, default 1.0
            CSV に risk_pct が無い場合に用いる 1 トレード当たりのリスク％

        Returns
        -------
        list[dict]
            各注文のシミュレーション結果 or API レスポンス
        """
        # --- CSV 読み込み（空ファイルも許容） --------------------------
        try:
            df = pd.read_csv(csv_path)
        except pd.errors.EmptyDataError:
            self.logger.info("CSV %s is empty — nothing to place.", csv_path)
            return []
        # ---------------------------------------------------------------

        results: List[Dict[str, Any]] = []

        if df.empty:
            self.logger.info("No rows in %s — nothing to place.", csv_path)
            return results

        for _, row in df.iterrows():
            payload = self._build_order_payload(
                row,
                account_id=account_id,
                capital=capital,
                risk_perc_default=risk_perc_default,
            )

            if dry_run or self.paper:
                result = self._simulate_order(payload)
                self.logger.info("[PAPER] %s", result)
            else:
                result = self._send_order(payload)
                self.logger.info("[LIVE ] %s", result)

            results.append(result)

        return results

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _build_order_payload(
        self,
        row: pd.Series,
        *,
        account_id: Optional[str] = None,
        capital: float = 1_000_000.0,
        risk_perc_default: float = 1.0,
    ) -> Dict[str, Any]:
        """
        DataFrame の 1 行から Webull 注文ペイロードを構築する。

        期待カラム:
            - symbol
            - Qty (優先) あるいは entry/stop_price/risk_pct で計算
            - entry / stop_price / tp_price
        """

        # -------- 必須フィールド取得 -------- #
        symbol = str(row.get("symbol") or row.get("Symbol"))

        # ★ 価格系カラムが無ければ即 ValueError
        if not any(col in row.index for col in ("Entry", "entry")):
            raise ValueError(f"Missing 'Entry' column: {row.to_dict()}")
        if not any(col in row.index for col in ("Stop", "stop_price")):
            raise ValueError(f"Missing 'Stop/stop_price' column: {row.to_dict()}")
        if not any(col in row.index for col in ("TP", "tp_price")):
            raise ValueError(f"Missing 'TP/tp_price' column: {row.to_dict()}")

        entry      = float(row.get("Entry") or row.get("entry"))
        stop_price = float(row.get("Stop")  or row.get("stop_price"))
        tp_price   = float(row.get("TP")    or row.get("tp_price"))
        # ------------------------------------ #


        # Qty 優先、なければ計算
        qty_val = row.get("Qty") or row.get("qty")
        if qty_val and not pd.isna(qty_val):
            qty = int(qty_val)
        else:
            risk_pct_row = float(
                row.get("risk_pct")
                or row.get("Risk_pct")
                or row.get("risk_pct%")
                or risk_perc_default
            )
            risk_amount = capital * (risk_pct_row / 100.0)
            diff = abs(entry - stop_price)
            if diff <= 0:
                raise ValueError(f"Invalid stop/entry for {symbol}: entry={entry}, stop={stop_price}")
            qty = max(1, int(risk_amount / diff))

        payload: Dict[str, Any] = {
            "account_id": account_id,
            "symbol": symbol,
            "qty": qty,
            "price": entry,
            "order_type": "LMT",
            "side": "BUY",
            "stop_loss": stop_price,
            "take_profit": tp_price,
            "time_in_force": "GTC",
        }
        return payload

    def _simulate_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """API を呼ばずに結果をモックする。ユニットテスト用。"""
        return {
            "symbol": payload["symbol"],
            "qty": payload["qty"],
            "side": payload["side"],
            "entry": payload["price"],
            "status": "SIMULATED",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    def _send_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """実注文 API 呼び出し（未実装）。"""
        if self.paper:
            raise RuntimeError("_send_order should not be called in paper mode.")

        if self._http is None:
            raise RuntimeError("httpx is not available or paper mode is True.")

        endpoint = f"{self.ENDPOINT_PAPER}/orders"
        resp = self._http.post(endpoint, json=payload, timeout=10.0)
        resp.raise_for_status()
        return resp.json()
