#!/usr/bin/env python
"""
monitor_trailing.py
========================================
保有ポジションを毎日チェックし、
終値が EMA10 を割った銘柄は全決済するユーティリティ。

前提
-----
* run_live.py で発注した **open_positions.csv**（例）を監視対象とする
  └ 例: Symbol,Qty,Entry,Stop,TP,Opened
* 設定は configs/config.yaml の sepa.trailing_ema を参照
* 決済は open_position_with_tpsl() と同じブローカー SDK に委譲
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

import pandas as pd
import yfinance as yf
from sepa.utils.config import get_config
from sepa.utils.broker import close_position  # ← 実装済み想定

LOG_FMT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# 設定値の読み込み
# ------------------------------------------------------------
CFG: Dict[str, Any] = get_config()
SEPA_CFG: Dict[str, Any] = CFG.get("sepa", {})
EMA_PERIOD: int = SEPA_CFG.get("trailing_ema", 10)

# 監視対象 CSV
POSITIONS_CSV = Path("data/open_positions.csv")

# ------------------------------------------------------------
# EMA10 判定
# ------------------------------------------------------------
async def check_one(symbol: str, qty: int) -> bool:
    """
    終値が EMA10 を割ったら True を返す
    """
    df = yf.download(
        symbol,
        period=f"{EMA_PERIOD + 5}d",
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if df.empty or len(df) < EMA_PERIOD + 1:
        logger.warning("%s: price history insufficient", symbol)
        return False

    close = df["Close"]
    ema10 = close.ewm(span=EMA_PERIOD, adjust=False).mean()

    latest_close = close.iloc[-1]
    latest_ema = ema10.iloc[-1]
    logger.info(
        "%s Close=%.2f  EMA%d=%.2f", symbol, latest_close, EMA_PERIOD, latest_ema
    )
    return latest_close < latest_ema


# ------------------------------------------------------------
# メインループ
# ------------------------------------------------------------
async def monitor_loop() -> None:
    if not POSITIONS_CSV.exists():
        logger.info("No open_positions.csv — nothing to monitor.")
        return

    positions = pd.read_csv(POSITIONS_CSV)
    if positions.empty:
        logger.info("No open positions.")
        return

    logger.info("Monitoring %d open positions…", len(positions))

    for _, row in positions.iterrows():
        sym, qty = row["Symbol"], int(row["Qty"])
        if qty <= 0:
            continue

        try:
            should_exit = await check_one(sym, qty)
            if should_exit:
                logger.info("[EXIT] %s fails EMA%d — closing %d shares", sym, EMA_PERIOD, qty)
                # ---- ブローカー発注 ----
                await close_position(symbol=sym, qty=qty)
                # ローカル CSV 更新
                positions.loc[positions["Symbol"] == sym, "Qty"] = 0
        except Exception as e:
            logger.exception("Error on %s: %s", sym, e)

    # CSV を上書き保存（決済済みは Qty=0）
    positions.to_csv(POSITIONS_CSV, index=False)
    logger.info("Monitoring completed at %s", datetime.now().strftime("%Y-%m-%d"))

# ------------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(monitor_loop())

