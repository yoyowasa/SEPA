#!/usr/bin/env python
# ============================================================
#  SEPAトレード  フォワード運用エントリースクリプト
#  ・週次スクリーニング結果を取り込み、即日エントリー
#  ・bot.log / strategy.csv へ同時に記録
#  ・--paper オプションでペーパートレード切替
# ============================================================

from __future__ import annotations

import argparse
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import yaml
import pandas as pd
import yfinance as yf                     # ★追加

# --- SEPA 内部モジュール ------------------------------------
from sepa.pipeline import weekly as weekly_mod            # シグナル生成
from sepa.risk import position_size                       # ロット計算         # 2 系統ロガー
from sepa.utils.broker import open_position_with_tpsl                  # 発注ラッパ（要実装 or 既存）
print("### RUN_LIVE.PY RELOADED ###")
from sepa.breakout import is_breakout 
# ------------------------------------------------------------


async def run_live(cfg: Dict[str, Any], paper: bool) -> None:
    print(">>> ENTER run_live  <<<")
    logger = logging.getLogger(__name__)
    logger.info(">>> run_live() entered") 
    """
    週次シグナルを取得し、フォワード運用を行うコルーチン。
    paper=True なら発注せずログだけ出力。
    """
    logger.info(">>> run_live() entered (paper=%s)", paper)
    logger.info("cfg keys: %s", list(cfg.keys()))
    logger.info("cfg['live']: %s", cfg.get('live'))

    # ---------- 1) 今週のシグナル生成 ------------------------
    top_n = cfg["live"].get("top_n", 10)
    logger.info("Generating SEPA signals (top_n=%s)…", top_n)
    signals: pd.DataFrame = weekly_mod.screen(top_n=top_n)
    logger.info("screen() returned %d rows", len(signals))

    if signals.empty:
        logger.warning("No signals generated — abort.")
        return

    # ---------- 2) 1 銘柄ずつエントリー ----------------------
    # ---------- 2) 1 銘柄ずつエントリー ----------------------
    cap = cfg["live"]["capital"]

    # 現状: risk_frac は 0.002 などの小数           （例 0.002 = 0.2 %）
    risk_frac = (cfg["live"].get("risk_pct")             # live.risk_pct があれば
                or cfg.get("sepa", {}).get("risk_pct")  # 無ければ sepa.risk_pct
                or 0.002)                               # デフォルト 0.2 %

    # ここで “%” に換算して position_size に渡す
    risk_pct = risk_frac * 100        # 例 0.002 * 100 = 0.2 %

    delay_s = cfg["live"].get("throttle_sec", 0.2)

    for _, row in signals.iterrows():
        sym   = row["symbol"]
                # ─────────────────────────────────────────────
        # 日足ブレイクアウト判定 ★ここを追加
        # ─────────────────────────────────────────────
        # try:
        #     df = yf.download(
        #         sym,
        #         period="4mo",
        #         interval="1d",
        #         auto_adjust=True,
        #         progress=False,
        #         threads=False,
        #     )
        #     # ▼▼ 追加: MultiIndex → 1階層にしてから capitalize
        #     if isinstance(df.columns, pd.MultiIndex):
        #         df.columns = df.columns.get_level_values(0)

        #     df.columns = [c.capitalize() for c in df.columns]
        #     flag, pivot = is_breakout(
        #         df,
        #         lookback=20,   # ← 65 → 20 に短縮
        #         vol_ma=10,     # ← 出来高平均も短縮
        #         vol_mult=1.0,  # ← 「出来高 1 倍」で許可
        #     )
        # except Exception as e:
        #     logger.warning("[SKIP breakout] %s - data error: %s", sym, e)
        #     continue

        # if not flag:
        #     logger.info("[SKIP breakout] %s - pivot %.2f 未ブレイク", sym, pivot or 0)
        #     continue
        # logger.info("[PASS breakout] %s - pivot %.2f 上抜け", sym, pivot)
        
        
        entry = row["entry"]          # ← 列名を合わせる
        stop  = row["stop_price"]
        tp    = row["tp_price"]      # 無ければ NA

        size = position_size(          # ← 必要な3引数だけキーワード指定
            ticker=sym,                # 銘柄コード
            equity=cap,                # 元本（円）
            risk_pct=risk_frac * 100         # 1トレード損失割合
        )
        print("DEBUG size dict:", size)   # ← 追加

        qty = size.get("qty") or size.get("Shares")
        if qty is None:
            raise ValueError(f"position_size returned {size}, but no size key found")
        tp_val = f"{tp:.2f}" if pd.notna(tp) else "NA"
        logger.info("[SIGNAL] %s entry=%.2f sl=%.2f tp=%s qty=%d",
                    sym, entry, stop, tp_val, qty)
        
                # open_positions.csv へ保有ポジションを追記
        import csv, datetime, pathlib
        pos_path = pathlib.Path("data/open_positions.csv")
        pos_path.parent.mkdir(exist_ok=True)         # data/ が無ければ作成
        new_row = {
            "Symbol": sym,
            "Qty":    qty,
            "Entry":  entry,
            "Stop":   stop,
            "TP":     tp if pd.notna(tp) else "",
            "Opened": datetime.date.today().isoformat(),
        }
        write_header = not pos_path.exists()
        with pos_path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=new_row.keys())
            if write_header:
                writer.writeheader()
            writer.writerow(new_row)

        if paper:
            logger.info("[PAPER] Order skipped (dry-run mode)")
        else:
            try:
                await open_position_with_tpsl(
                    symbol=sym,
                    qty=qty,
                    entry_price=entry,
                    take_profit=tp,
                    stop_loss=stop,
                    paper=paper,
                )
            except Exception as e:
                logger.exception("Order failed: %s", e)

        await asyncio.sleep(delay_s)      # API スロットル


def main() -> None:
    parser = argparse.ArgumentParser(description="SEPA live trading runner")
    parser.add_argument("--config", default="configs/config.yaml",
                        help="YAML 設定ファイルパス")
    parser.add_argument("--paper", action="store_true",
                        help="ペーパートレード（発注しない）")
    args = parser.parse_args()

    # ---------- 設定読み込み ---------------------------------
    cfg_path = Path(args.config)
    if not cfg_path.exists():
        sys.exit(f"config file not found: {cfg_path}")

    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # ---------- ロガー初期化 ---------------------------------
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "bot.log"

    # --- ルートロガー設定（コンソール＋回転ファイル） --------
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, cfg.get("log_level", "INFO")))

    # コンソール
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    root_logger.addHandler(ch)

    # 回転ファイル（5 MB × 3 世代）
    fh = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(formatter)
    root_logger.addHandler(fh)

    logging.getLogger(__name__).info("Logger initialized — start live run")
    try:
        asyncio.run(run_live(cfg, args.paper))      # ★ フォワード本体を呼び出す
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Interrupted by user — exit")


if __name__ == "__main__":
    main()
