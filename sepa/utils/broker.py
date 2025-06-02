"""
sepa.utils.broker
================================================
フォワード運用用の発注ラッパ（暫定ダミー版）
- --paper モード: ログ出力のみ
- 実売買 API が完成したらここを差し替える
"""

from __future__ import annotations
import logging
import asyncio
from typing import Literal

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
#  メイン API: open_position_with_tpsl
# ------------------------------------------------------------
async def open_position_with_tpsl(
    symbol: str,
    qty: float,
    entry_price: float,
    take_profit: float,
    stop_loss: float,
    side: Literal["LONG", "SHORT"] = "LONG",
    paper: bool = True,
) -> None:
    """
    市場成行 or 指値で建玉し、同時に TP/SL を設定する。

    Parameters
    ----------
    symbol : str
    qty : float
    entry_price : float
    take_profit : float
    stop_loss : float
    side : "LONG" | "SHORT"
    paper : bool
        True なら実発注せずログだけ出力
    """
    if paper:
        logger.info(
            "[PAPER] %s %s qty=%.4f entry=%.2f tp=%.2f sl=%.2f",
            side, symbol, qty, entry_price, take_profit, stop_loss,
        )
        return

    # ここから下を実発注用に書き換える ------------------------
    raise NotImplementedError("リアル発注ラッパは未実装です")


# ------------------------------------------------------------------
# 仮実装: EMA10 トレーリング用クローズラッパ
# 本番では各ブローカー SDK の決済 API へ置き換えてください
# ------------------------------------------------------------------
import logging
import asyncio
logger = logging.getLogger(__name__)

async def close_position(symbol: str, qty: int, paper: bool = True) -> None:
    """
    保有ポジションを全決済するラッパ。
    - paper=True のときはログだけ出してスキップ
    - 実装例では Market 成行で一括決済を想定
    """
    if paper:
        logger.info("[PAPER] close_position skipped %s qty=%d", symbol, qty)
        return

    try:
        # ★ここをブローカー SDK に置換してください★
        # broker_sdk.market_close(symbol=symbol, quantity=qty)
        await asyncio.sleep(0)    # 非同期関数の形を保つダミー
        logger.info("[LIVE]  market close %s qty=%d", symbol, qty)
    except Exception as e:
        logger.exception("close_position failed: %s", e)
