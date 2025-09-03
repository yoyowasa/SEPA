"""
trade_manager.py

Alpaca API を用いて自動エントリー／エグジットを行う。
・エントリー時にブラケット注文（OTO）を使い、成行エントリーと同時にストップロス注文を設定
・エグジットシグナル受信時にポジションを成行クローズ

環境変数
---------
ALPACA_API_KEY
ALPACA_API_SECRET
ALPACA_BASE_URL   # 例: https://paper-api.alpaca.markets
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import alpaca_trade_api as tradeapi

logger = logging.getLogger(__name__)


@dataclass
class OrderInfo:
    symbol: str
    qty: int
    entry_price: float
    stop_price: float
    limit_price: Optional[float] = None
    order_id: Optional[str] = None


class TradeManager:
    """
    Parameters
    ----------
    paper : bool, default True
        True ならペーパー口座接続
    """

    def __init__(self, paper: bool = True) -> None:
        key = os.getenv("ALPACA_API_KEY")
        secret = os.getenv("ALPACA_API_SECRET")
        base_url = os.getenv("ALPACA_BASE_URL") or (
            "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
        )
        if not key or not secret:
            raise EnvironmentError("ALPACA_API_KEY / ALPACA_API_SECRET が未設定です。")

        self.paper = paper
        self.api = tradeapi.REST(key, secret, base_url, api_version="v2")

    # ──────────────────────────────
    # エントリー（ブラケット注文）
    # ──────────────────────────────
    def enter_trade(self, info: OrderInfo) -> Optional[str]:
        """
        ブラケット注文（OTO）を使い、成行エントリーと同時にストップロス注文を出す。
        これにより、エントリーと同時にポジションが保護される。

        Returns
        -------
        entry_order_id : str or None
            発注に成功した場合はエントリー注文のID、失敗した場合はNoneを返す。
        """
        try:
            entry_order = self.api.submit_order(
                symbol=info.symbol,
                qty=info.qty,
                side="buy",
                type="market",
                time_in_force="day",
                order_class="oto",  # One-Triggers-the-Other
                stop_loss={"stop_price": round(info.stop_price, 2)},
            )
            info.order_id = entry_order.id
            logger.info(
                "SUBMITTED OTO entry for %s: Qty=%d, Stop=%s",
                info.symbol, info.qty, info.stop_price
            )
            return entry_order.id
        except tradeapi.rest.APIError as e:
            logger.error("Failed to submit OTO entry for %s: %s", info.symbol, e)
            return None

    # ──────────────────────────────
    # エグジット（成行クローズ）
    # ──────────────────────────────
    def exit_trade(self, symbol: str) -> None:
        """保有ポジションを成行で全量手仕舞いし、関連注文をキャンセル"""
        try:
            # 1. この銘柄に関連するオープンな注文をすべてキャンセルする
            open_orders = self.api.list_orders(status="open", symbols=[symbol])
            for order in open_orders:
                self.api.cancel_order(order.id)
                logger.info("Cancelled open order %s for %s.", order.id, symbol)

            # 2. ポジションを成行でクローズする
            closed_position = self.api.close_position(symbol)
            logger.info(
                "Submitted market order to close position in %s. Qty=%s",
                symbol, closed_position.qty
            )
        except tradeapi.rest.APIError as e:
            # APIErrorはポジションが存在しない場合や注文キャンセル失敗時などに発生
            logger.warning("Could not exit trade for %s: %s", symbol, e)
