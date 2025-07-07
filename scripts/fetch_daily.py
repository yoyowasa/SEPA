#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fetch_daily.py
==============
毎晩実行して「全ユニバースの最新日足 CSV」を data/raw/ 以下にキャッシュする。

1. get_universe("us_all") で NASDAQ / NYSE / S&P500 を取得
2. 既存 CSV があれば  “最終日＋1日〜今日” だけ追加入手
3. 価格 <10 USD or 平均出来高 <50 万株 はスキップ
4. ThreadPoolExecutor で並列取得（Ticker.history はスレッド安全）
"""

from __future__ import annotations

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import sys, traceback, warnings, io, os, json, socket, getpass

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

from sepa.utils.universe import get_universe

warnings.filterwarnings("ignore", category=UserWarning)
load_dotenv()  # .env から SEPA_DISCORD_WEBHOOK を読む

# ───────────────────────── 設定 ──────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR      = PROJECT_ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

PARALLEL_WORKERS   = 32
SKIP_PRICE_USD     = 10
SKIP_AVG_VOL_SHR   = 500_000
HISTORY_PERIOD     = "2y"        # 新規銘柄は過去 2 年
DATE_FMT           = "%Y-%m-%d"

# ─────────── Discord Webhook ───────────
import requests
def send_discord(msg: str) -> None:
    url = os.getenv("SEPA_DISCORD_WEBHOOK")
    if not url:
        print("[WARN] WEBHOOK URL 未設定")
        return
    payload = {
        "username": "SEPA Bot",
        "content": f"{msg}\n```\nHost: {socket.gethostname()}  User: {getpass.getuser()}\n```"
    }
    try:
        r = requests.post(url, data=json.dumps(payload),
                          headers={"Content-Type": "application/json"}, timeout=10)
        if r.status_code >= 400:
            print(f"[WARN] Discord 通知失敗 status={r.status_code}")
    except Exception as e:
        print(f"[WARN] Discord 通知例外: {e}")

# ─────────── 1 銘柄取得 ───────────
def download_one(tic: str) -> tuple[str, str]:
    """
    Returns
    -------
    (symbol, "OK"/"SKIP_xxx"/"ERR_xxx")
    """
    try:
        out_csv = RAW_DIR / f"{tic}.csv"
        today   = datetime.now(timezone.utc).date()

        # ―― 既存 CSV 読み込み ―――――――――――――――――――――――――――――――
        if out_csv.exists():
            df_exist = pd.read_csv(out_csv, parse_dates=["Date"])
            last_date = df_exist["Date"].iloc[-1].date()
            if last_date >= today - timedelta(days=1):
                return tic, "SKIP_UP_TO_DATE"
            start_str = (last_date + timedelta(days=1)).strftime(DATE_FMT)
        else:
            df_exist  = None
            start_str = None  # 新規は period 指定

        # ―― yfinance 取得（Ticker.history はスレッド安全） ―――――――――
        yf_tkr = yf.Ticker(tic)
        if start_str:
            df_new = yf_tkr.history(start=start_str, end=(today + timedelta(days=1)).strftime(DATE_FMT),
                                    interval="1d", auto_adjust=True)
        else:
            df_new = yf_tkr.history(period=HISTORY_PERIOD, interval="1d", auto_adjust=True)

        if df_new.empty:
            return tic, "ERR_EMPTY"

        # index → 列
        df_new.index.name = "Date"
        df_new = df_new.reset_index()

        # ―― 結合 & 整形 ―――――――――――――――――――――――――――――――――――
        df_all = df_new if df_exist is None else (
            pd.concat([df_exist, df_new]).drop_duplicates(subset="Date"))

        if isinstance(df_all.columns, pd.MultiIndex):
            df_all.columns = df_all.columns.get_level_values(0)
        df_all = df_all.loc[:, ~df_all.columns.duplicated(keep="first")]

        df_all.columns = [c.capitalize() for c in df_all.columns]
        if "Adj close" in df_all.columns and "Close" not in df_all.columns:
            df_all = df_all.rename(columns={"Adj close": "Close"})

        # ―― 一次フィルタ ―――――――――――――――――――――――――――――――――
        if df_all["Close"].iat[-1] < SKIP_PRICE_USD:
            return tic, "SKIP_PRICE"
        if df_all["Volume"].tail(20).mean() < SKIP_AVG_VOL_SHR:
            return tic, "SKIP_VOL"

        # ―― 保存 ――――――――――――――――――――――――――――――――――――――
        df_all[["Date", "Open", "High", "Low", "Close", "Volume"]].to_csv(
            out_csv, index=False, float_format="%.6f")
        return tic, "OK"

    except Exception:
        traceback.print_exc()
        return tic, "ERR_EXCEPTION"

# ─────────── main ───────────
def main() -> None:
    uni = get_universe("us_all", refresh=True)
    start_time = datetime.now(timezone.utc)

    print(f"ユニバース {len(uni):,} 件 → 並列 {PARALLEL_WORKERS} ワーカーで取得\n")

    stats: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futs = {ex.submit(download_one, t): t for t in uni}
        for fut in as_completed(futs):
            tic, st = fut.result()
            stats[st] = stats.get(st, 0) + 1
            if st.startswith(("ERR", "SKIP_")):
                print(f"{tic:6} {st}")

    print("\n── 結果 ──")
    for k, v in sorted(stats.items()):
        print(f"{k:15}: {v:,}")

    # ---------- Discord 通知 ----------
    ok   = stats.get("OK", 0)
    errs = sum(v for k, v in stats.items() if k.startswith("ERR"))
    skip_price = stats.get("SKIP_PRICE", 0)
    skip_vol   = stats.get("SKIP_VOL", 0)
    up_to_date = stats.get("SKIP_UP_TO_DATE", 0)

    # 実行時間
    duration = datetime.now(timezone.utc) - start_time  # ← main 冒頭で start_time = datetime.now(timezone.utc)
    dur_str  = f"{duration.seconds//60}m {duration.seconds%60}s"

    mention = "<@here> " if errs else ""
    msg = (
        f"{mention}[fetch_daily] 完了 ✅\n"
        f"OK={ok:,}  SKIP_UP={up_to_date:,}  SKIP_VOL={skip_vol:,}  "
        f"SKIP_PRICE={skip_price:,}  ERR={errs:,}\n"
        f"Duration {dur_str}"
    )
    send_discord(msg)

# ─────────── CLI ―──────────
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrupted.")
