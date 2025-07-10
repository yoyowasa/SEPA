"""
trade_manager.py

Alpaca API を用いて自動エントリー／エグジットを行う最小構成。
・エントリー時に成行（または指値）発注
・初期ストップを OCO で同時セット
・エグジットシグナル受信時にポジションを成行クローズ

環境変数
---------
ALPACA_API_KEY
ALPACA_API_SECRET
ALPACA_BASE_URL   # 例: https://paper-api.alpaca.markets
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import alpaca_trade_api as tradeapi


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

        self.api = tradeapi.REST(key, secret, base_url, api_version="v2")

    # ──────────────────────────────
    # エントリー（OCO 同時発注）
    # ──────────────────────────────
    def enter_trade(self, info: OrderInfo) -> str:
        """
        成行エントリー＋OCO ストップ注文を出す。

        Returns
        -------
        entry_order_id : str
        """
        # ① 成行エントリー
        entry_order = self.api.submit_order(
            symbol=info.symbol,
            qty=info.qty,
            side="buy",
            type="market",
            time_in_force="day",
        )
        info.order_id = entry_order.id

        # ② OCO ストップ（初期ストップ）
        self.api.submit_order(
            symbol=info.symbol,
            qty=info.qty,
            side="sell",
            type="stop",
            stop_price=round(info.stop_price, 2),
            time_in_force="gtc",
            order_class="oco",
        )

        print(f"ENTERED {info.symbol} x{info.qty} @ market  | stop={info.stop_price}")
        return entry_order.id

    # ──────────────────────────────
    # エグジット（成行クローズ）
    # ──────────────────────────────
    def exit_trade(self, symbol: str) -> None:
        """保有ポジションを成行で全量手仕舞いし、関連注文をキャンセル"""
        try:
            pos = self.api.get_position(symbol)
        except tradeapi.rest.APIError:
            print(f"No open position in {symbol}")
            return

        # 既存 OCO/Stop 注文をキャンセル
        open_orders = self.api.list_orders(status="open", symbols=[symbol])
        for o in open_orders:
            self.api.cancel_order(o.id)

        # 成行クローズ
        self.api.submit_order(
            symbol=symbol,
            qty=pos.qty,
            side="sell",
            type="market",
            time_in_force="day",
        )
        print(f"EXIT {symbol} @ market  | qty={pos.qty}")
