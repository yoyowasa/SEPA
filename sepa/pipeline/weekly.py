"""
sepa.pipeline.weekly
====================
週次 SEPA フィルタ（Trend / Fundamentals / 流動性）

Flow
-----
1. 流動性フィルタ（平均出来高 & 株価）
2. Trend Template 判定
3. Fundamentals 判定（EPS/Sales Growth）
4. 合格銘柄は指標 dict を返す
"""

from __future__ import annotations
from datetime import timedelta
from collections import Counter
from typing import Dict, Any, List

import pandas as pd
import yfinance as yf

from sepa.trend import trend_template_ok
from sepa.fundamentals import fetch_growth
from sepa.utils.config import get_config

# ───────────────────────────── デバッグ用フラグ ─────────────────────────────
DEBUG_TREND = False         # Trend テンプレートの詳細ログ
DEBUG_DROP  = True          # NG 理由をすべて print
STEP_MODE   = "all"         # "trend"/"fund"/"all" で途中 return

# ───────────────────────────── パラメータ定数 ─────────────────────────────
LOOKBACK       = 12         # Volume breakout 用（未使用）
MIN_WEEKS      = 52         # 52 週未満の銘柄は除外
VOL_MULTIPLIER = 1.4        # Volume breakout 用（未使用）

counter: Counter = Counter()  # NG/OK カウンタ

# ───────────────────────────── 設定ローダ ─────────────────────────────
def _sepa_cfg() -> dict:
    g = get_config()
    cfg = g.get("sepa", {}).copy()
    if "fundamentals" not in cfg and "fundamentals" in g:
        cfg["fundamentals"] = g["fundamentals"]
    return cfg

# ──────────────────────────── ファンダメンタル判定 ─────────────────────────
def is_growth_ok(metrics: dict | None, cfg: dict) -> bool:
    fd = cfg.get("fundamentals", {})
    if not fd.get("enabled", True):
        return True
    if not metrics:
        return True

    eps, rev = metrics.get("EPS_G%"), metrics.get("REV_G%")
    eps_min  = fd.get("eps_g_min", 20)
    rev_min  = fd.get("rev_g_min", 20)

    if pd.isna(eps) or pd.isna(rev):
        return True
    return (eps >= eps_min) and (rev >= rev_min)

# ────────────────────────── 週足 DataFrame → 指標 dict ─────────────────────
def _analyze_one_from_df(tic: str, df: pd.DataFrame) -> Dict[str, Any]:
    cfg    = _sepa_cfg()
    close  = df["Close"].iat[-1]
    rs_26w = (df["Close"].iloc[-26:] / df["Close"].iloc[-26]).iat[-1]

    entry      = round(close * 1.01, 2)
    stop_price = round(entry * (1 - cfg["stop_pct"]), 2)
    tp_price   = round(entry * (1 + cfg["tp1_pct"]), 2)
    risk_pct   = round((entry - stop_price) / entry * 100, 2)

    metrics = fetch_growth(tic) or {}
    high_52 = df["High"].rolling(52, 1).max().iat[-1]
    low_52  = df["Low"].rolling(52, 1).min().iat[-1]

    return {
        "date": df.index[-1].date(),
        "symbol": tic,
        "entry": entry,
        "stop_price": stop_price,
        "tp_price": tp_price,
        "risk_pct": risk_pct,
        "exit": pd.NA,
        "Close": close,
        "High52w": high_52,
        "Low52w": low_52,
        "RS_26w": rs_26w,
        "EPS_G%": metrics.get("EPS_G%", pd.NA),
        "REV_G%": metrics.get("REV_G%", pd.NA),
    }

# ───────────────────────────── asof 週次解析 ──────────────────────────────
def analyze_one_asof(tic: str, asof: pd.Timestamp) -> Dict[str, Any] | None:
    cfg = _sepa_cfg()

    # 1) 過去 2 年の日足取得
    df_daily = yf.download(
        tic, period="2y", interval="1d",
        progress=False, threads=False, auto_adjust=True
    )
    if df_daily.empty:
        counter["no_data"] += 1
        if DEBUG_DROP: print(f"[NO_DATA] {tic}")
        return None

    # 列名正規化
    if isinstance(df_daily.columns, pd.MultiIndex):
        df_daily.columns = df_daily.columns.get_level_values(0)
    df_daily.columns = [c.capitalize() for c in df_daily.columns]
    if "Adj close" in df_daily.columns and "Close" not in df_daily.columns:
        df_daily = df_daily.rename(columns={"Adj close": "Close"})

    # 必須列チェック
    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(df_daily.columns):
        counter["no_data"] += 1
        if DEBUG_DROP:
            miss = required.difference(df_daily.columns)
            print(f"[MISSING_COL] {tic}: {sorted(miss)}")
        return None

    # 2) 週足リサンプリ（タイムゾーンをすべて tz-naive に統一）
    df_week = (
        df_daily[["Open", "High", "Low", "Close", "Volume"]]
        .resample("W-FRI")
        .agg({"Open": "first",
              "High": "max",
              "Low": "min",
              "Close": "last",
              "Volume": "sum"})
        .dropna()
    )
    if df_week.index.tz is not None:
        df_week.index = df_week.index.tz_localize(None)

    asof_naive = asof.tz_localize(None) if asof.tzinfo else asof
    df_week = df_week.loc[:asof_naive]

    if len(df_week) < MIN_WEEKS:
        counter["short_history"] += 1
        if DEBUG_DROP: print(f"[SHORT_HISTORY] {tic}")
        return None

    # 3) 流動性フィルタ
    if df_daily["Volume"].tail(20).mean() < cfg["min_avg_volume"]:
        counter["liquidity"] += 1
        if DEBUG_DROP: print(f"[LIQUIDITY NG] {tic}: vol < min")
        return None
    if df_week["Close"].iat[-1] < cfg["min_price"]:
        counter["liquidity"] += 1
        if DEBUG_DROP: print(f"[LIQUIDITY NG] {tic}: price < min")
        return None

    # 4) Trend Template
    if not trend_template_ok(df_week, debug=DEBUG_TREND).iat[-1]:
        counter["trend"] += 1
        if DEBUG_DROP: print(f"[TREND NG] {tic}")
        return None
    if STEP_MODE == "trend":
        return _analyze_one_from_df(tic, df_week)

    # 5) Fundamentals
    metrics = fetch_growth(tic)
    if not isinstance(metrics, dict) or not is_growth_ok(metrics, cfg):
        counter["fund"] += 1
        if DEBUG_DROP:
            eps = metrics.get("EPS_G%", 'NA') if metrics else 'NA'
            rev = metrics.get("REV_G%", 'NA') if metrics else 'NA'
            print(f"[FUND NG] {tic}: EPS_G={eps}, REV_G={rev}")
        return None

    counter["pass"] += 1
    return _analyze_one_from_df(tic, df_week)

# ───────────────────────────── 週次スクリーナ API ──────────────────────────
def screen(
    top_n: int | None = 10,
    tickers: List[str] | None = None,
    asof: pd.Timestamp | None = None,
) -> pd.DataFrame:

    if tickers is None:
        tickers = ["AAPL", "MSFT"]

    if asof is None:
        asof = (
            pd.Timestamp.utcnow().normalize()
            - pd.tseries.offsets.Week(weekday=4)
        )

    rows: List[dict] = []
    for t in tickers:
        res = analyze_one_asof(t, asof)
        if res is not None:
            rows.append(res)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values("RS_26w", ascending=False)
    return df if not top_n else df.head(top_n)
