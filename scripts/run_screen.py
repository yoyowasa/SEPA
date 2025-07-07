#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
run_screen.py
=============

NASDAQ / NYSE / S&P500 全銘柄を SEPA 公式基準で週次スクリーニングし、
ヒットがあれば紙トレ発注 → Streamlit ダッシュボードを自動起動し、
Discord へ結果＋ダッシュボード URL を通知する。

出力:
    data/screening_results.csv
        date,symbol,entry,stop_price,tp_price,risk_pct,exit,
        Close,High52w,Low52w,RS_26w,EPS_G%,REV_G%
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import argparse
import sys
import warnings
import os
import json
import logging
import socket
import subprocess

import pandas as pd
import yfinance as yf
import requests
from dotenv import load_dotenv

from sepa import pipeline as pp
from sepa.utils.universe import get_universe
from sepa.broker.webull_client import WebullClient

# ──────────────────────────── 共通設定 ────────────────────────────
warnings.filterwarnings("ignore", category=UserWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
OUT_CSV = DATA_DIR / "screening_results.csv"

MAX_CHECK_CHUNK = 20
SPECIAL_MAP = {"BRK.B": "BRK-B", "BF.B": "BF-B"}
DEFAULT_VOL_MULTIPLIER = 1.5

# ---------- ダッシュボード設定 (env で上書き可) ----------
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "localhost")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8501"))
DASHBOARD_URL  = f"http://{DASHBOARD_HOST}:{DASHBOARD_PORT}"

# ---------- Discord 通知ユーティリティ ---------- #
load_dotenv()  # .env → os.environ


def send_discord(
    hits: int,
    drop_sum: int,
    duration_str: str,
    dashboard_url: str | None = None,
) -> None:
    """
    Discord Webhook へ Embed 形式で通知を送信する。

    Parameters
    ----------
    hits : int
        ヒット銘柄数
    drop_sum : int
        途中でドロップされた銘柄数
    duration_str : str
        実行所要時間の文字列（例 "3m 42s"）
    dashboard_url : str | None
        ダッシュボード URL（ヒット >0 のときに添付）
    """
    webhook = os.getenv("SEPA_DISCORD_WEBHOOK")
    if not webhook:
        print("[WARN] Discord WEBHOOK 未設定 (.env または環境変数)")
        return

    # Embed カラー: ヒット>0 → 緑 / 0 → 赤
    color = 0x22C55E if hits > 0 else 0xEF4444

    desc_lines = [
        f"**ヒット** : {hits:,}",
        f"**DROP**   : {drop_sum:,}",
        f"**Duration** : {duration_str}",
    ]
    if dashboard_url and hits > 0:
        desc_lines.append(f"[📊 Dashboard]({dashboard_url})")

    embed = {
        "title": "run_screen 完了 ✅" if hits > 0 else "run_screen 完了 ⚠️ ヒット0",
        "description": "\n".join(desc_lines),
        "color": color,
    }
    payload = {"username": "SEPA Bot", "embeds": [embed]}

    try:
        res = requests.post(webhook, json=payload, timeout=10)
        if res.status_code >= 400:
            print(f"[WARN] Discord 通知失敗 status={res.status_code}")
    except Exception as e:
        print(f"[WARN] Discord 通知例外: {e}")



# ──────────────────────────── yfinance 可用チェック ────────────────────────────
def filter_available_tickers(tickers: list[str]) -> list[str]:
    yf_tickers = [SPECIAL_MAP.get(t, t) for t in tickers]
    good, bad = [], []

    for i in range(0, len(yf_tickers), MAX_CHECK_CHUNK):
        chunk = yf_tickers[i : i + MAX_CHECK_CHUNK]
        try:
            df = yf.download(chunk, period="1d", progress=False, threads=True, auto_adjust=False)["Close"]
            if isinstance(df, pd.Series):
                df = df.to_frame(chunk[0])
            for orig, yf_sym in zip(tickers[i : i + MAX_CHECK_CHUNK], chunk):
                (
                    good
                    if yf_sym in df.columns and pd.notna(df[yf_sym]).any()
                    else bad
                ).append(orig)
        except Exception:
            for orig, yf_sym in zip(tickers[i : i + MAX_CHECK_CHUNK], chunk):
                try:
                    s = yf.download(
                        yf_sym, period="1d", progress=False, threads=False, auto_adjust=False
                    )["Close"]
                    (good if pd.notna(s).any() else bad).append(orig)
                except Exception:
                    bad.append(orig)

    if bad:
        print(f"[WARN] データ取得失敗 → 除外: {bad}")
    return good


# ──────────────────────────── ポート使用可否 ────────────────────────────
def is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex((host, port)) == 0


def start_dashboard_if_needed() -> None:
    if is_port_in_use(DASHBOARD_HOST, DASHBOARD_PORT):
        logging.info("Dashboard already running → %s", DASHBOARD_URL)
        return

    dashboard_script = PROJECT_ROOT / "scripts" / "dashboard.py"
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(dashboard_script),
        "--server.headless",
        "true",
        "--server.address",
        DASHBOARD_HOST,
        "--server.port",
        str(DASHBOARD_PORT),
    ]
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    logging.info("Dashboard started → %s", DASHBOARD_URL)


# ──────────────────────────── main ────────────────────────────
def main() -> None:
    start_time = datetime.now(timezone.utc)

    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=10, help="ヒット上位 N 件 (0 なら全件)")
    ap.add_argument(
        "--m", type=float, default=DEFAULT_VOL_MULTIPLIER, help="出来高倍率 vol_multiplier"
    )
    ap.add_argument("--debug-trend", action="store_true")
    ap.add_argument(
        "--step", choices=["trend", "volume", "fund", "all"], default="all"
    )
    ap.add_argument("--ticker", help="単一ティッカー指定")
    ap.add_argument(
        "--place-paper-order",
        action="store_true",
        help="screening_results.csv を Webull で紙トレ発注",
    )
    # ★ 追加ここ
    ap.add_argument(
        "--csv-only",
        action="store_true",
        help="ユニバース取得・スクリーニングをスキップして既存 CSV を使用",
    )
    args = ap.parse_args()

    if args.n < 0:
        sys.exit("[ERROR] -n は 0 以上で指定")

    # ─────────────────── ユニバース取得 ─────────────────── #
    # ─────────────────── スクリーニング or CSV‑ONLY ─────────────────── #
    if args.csv_only:
        # ★ CSV‑ONLY: 既存 CSV をそのまま使う
        print("[INFO] --csv-only モード: ユニバース取得・スクリーニングをスキップ")
        if not OUT_CSV.exists() or OUT_CSV.stat().st_size == 0:
            sys.exit("[ERROR] screening_results.csv が空か存在しません")
        hits = pd.read_csv(OUT_CSV)

    else:
        # ─────────────────── ユニバース取得 ─────────────────── #
        tickers_all = (
            [args.ticker.upper()] if args.ticker else get_universe("us_all", refresh=True)
        )
        tickers_all = [t for t in tickers_all if not t.endswith(("W", "R"))]

        import re
        valid_ticker = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")
        tickers_all = [t for t in tickers_all if valid_ticker.match(t)]

        print(f"▼ ユニバース {len(tickers_all):,} 件")

        tickers = filter_available_tickers(tickers_all)
        print(f"▼ 可用ティッカー {len(tickers):,} 件")

        # パラメータ設定
        pp.VOL_MULTIPLIER = args.m
        from sepa.pipeline import weekly as w
        w.DEBUG_TREND = args.debug_trend
        w.STEP_MODE   = args.step

        top_n = args.n if args.n > 0 else None
        hits  = pp.screen(top_n=top_n, tickers=tickers)

        print("\n── フィルタ別ドロップ数 ──")
        for k, v in w.counter.items():
            print(f"{k:12}: {v:,}")

        required = [
            "date","symbol","entry","stop_price","tp_price","risk_pct","exit",
            "Close","High52w","Low52w","RS_26w","EPS_G%","REV_G%",
        ]

        if hits.empty:
            pd.DataFrame(columns=required).to_csv(OUT_CSV, index=False)
            print("\n⚠️ 該当銘柄なし → 空 CSV 保存")
        else:
            if isinstance(hits.index, pd.DatetimeIndex):
                hits = hits.reset_index(names="date")
            for col in required:
                if col not in hits.columns:
                    hits[col] = pd.NA
            hits = hits[required]
            hits.to_csv(OUT_CSV, index=False, date_format="%Y-%m-%d")
            print(f"\n✅ {len(hits):,} 行を書き出し → {OUT_CSV}")
            print(hits.head())


    # ---------- 紙トレ発注処理 ---------- #
    if args.place_paper_order:
        print("\n── WebullClient 紙トレ発注 ──")
        client = WebullClient(paper=True, logger=logging.getLogger("Webull"))
        try:
            results = client.place_orders_from_csv(OUT_CSV, dry_run=False)
            print(f"✅ 発注完了 {len(results):,} 件")
        except Exception as e:
            print(f"[ERROR] 発注失敗: {e}")

    # ---------- ダッシュボード起動 & Discord 通知 ---------- #
    if not hits.empty:
        start_dashboard_if_needed()

    # ---------- Discord 通知 ---------- #
    duration = datetime.now(timezone.utc) - start_time
    dur_str  = f"{duration.seconds//60}m {duration.seconds%60}s"

    # csv‑only モードでは w.counter が無いので 0 にする
    drop_sum = 0 if args.csv_only else sum(v for k, v in w.counter.items() if k != "pass")


    send_discord(
        hits=len(hits),
        drop_sum=drop_sum,
        duration_str=dur_str,
        dashboard_url=DASHBOARD_URL if not hits.empty else None,
    )



# ────────────────────────────
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrupted.")
