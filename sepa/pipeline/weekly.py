"""週次 SEPA フィルタ（Trend / Volume / Fundamentals）

Flow
-----
1. 流動性フィルタ（出来高 ≥1M株/日 & 株価 ≥10USD）
2. Trend Template 判定
3. Volume Breakout 判定
4. Fundamentals 判定（EPS / Sales Growth）
5. 合格銘柄は指標 dict を返す
"""

from __future__ import annotations

from datetime import timedelta
from collections import Counter
from typing import Dict, Any, List

import pandas as pd
import yfinance as yf

from sepa.trend import trend_template_ok
from sepa.fundamentals import fetch_growth
from sepa.patterns import volume_breakout as breakout_signal
from sepa.utils.config import get_config

# ──────────────────────────────────────────────
# デバッグ用フラグ
# ──────────────────────────────────────────────
DEBUG_TREND = True        # True で詳細ログ
STEP_MODE   = "all"       # "trend"/"volume"/"fund" で途中 return
LOOKBACK    = 12          # Volume breakout を過去 n 週で判定
MIN_WEEKS   = 52          # 52 週 (< 約 1 年) 未満は対象外

# Volume breakout パラメータ
HIGH_WINDOW     = 20      # 高値ブレイク判定 look-back 週数
VOL_WINDOW      = 20      # 出来高平均を取る週数
VOL_MULTIPLIER  = 1.4     # 出来高急増判定 (volume > SMA * N)

# ヘッダ用カウンタ（他モジュール共有）
counter: Counter = Counter()

# ──────────────────────────────────────────────
# 公式最小基準 & 閾値を config から取得
# ──────────────────────────────────────────────
def _sepa_cfg() -> dict:
    """configs/config.yaml の `sepa:` セクションを返す"""
    return get_config().get("sepa", {})


# ──────────────────────────────────────────────
# Fundamentals 判定
# ──────────────────────────────────────────────
def is_growth_ok(metrics: dict | None, cfg: dict) -> bool:
    # ←▼▼ 追加ここから ▼▼
    if not cfg.get("fundamentals", {}).get("enabled", True):
        return True            # ファンダメンタルズ判定をスキップ
    """
    EPS/Sales Growth が閾値以上なら True。
    どちらかが欠損(NaN)の場合は合格扱いにして様子を見る。
    """
    if not metrics:                 # fetch_growth が None の場合
        return True

    f_cfg   = cfg.get("fundamentals", {})
    eps_min = f_cfg.get("eps_g_min", 20)
    rev_min = f_cfg.get("rev_g_min", 20)

    eps_g = metrics.get("EPS_G%")
    rev_g = metrics.get("REV_G%")

    # ★ここを変更★ 片方が NaN なら通す
    if pd.isna(eps_g) or pd.isna(rev_g):
        return True

    return (eps_g >= eps_min) and (rev_g >= rev_min)


# ------------------------------------------------------------
# 1) 週足 DataFrame → 指標ディクショナリに変換
# ------------------------------------------------------------
def _analyze_one_from_df(tic: str, df: pd.DataFrame) -> Dict[str, Any]:
    """週足 DataFrame から各種指標を算出し dict を返す"""
    cfg   = _sepa_cfg()
    close = df["Close"].iloc[-1]
    high_52w = df["High"].rolling(52, min_periods=1).max().iloc[-1]
    low_52w = df["Low"].rolling(52, min_periods=1).min().iloc[-1]
    rs_26w = (df["Close"].iloc[-26:] / df["Close"].iloc[-26]).iloc[-1]

    # ─ Growth metrics ─
    metrics = fetch_growth(tic)
    if not isinstance(metrics, dict):
        metrics = {"EPS_G%": pd.NA, "REV_G%": pd.NA}

    # ─ Dummy trade columns (仮置き) ─
    entry       = round(close * 1.01, 2)   # 終値 +1 %
    stop_price  = round(entry * (1 - cfg["stop_pct"]), 2)    # エントリー　-5％
    tp_price   = round(entry * (1 + cfg["tp1_pct"]), 2)      # エントリー　+10％
    risk_pct    = round((entry - stop_price) / entry * 100, 2)
    exit_price  = pd.NA
    trade_date  = df.index[-1].date()

    return {
        "date": trade_date,
        "symbol": tic,
        "entry": entry,
        "stop_price": stop_price,
        "tp_price": tp_price,
        "risk_pct": risk_pct,
        "exit": exit_price,
        "Close": close,
        "High52w": high_52w,
        "Low52w": low_52w,
        "RS_26w": rs_26w,
        "EPS_G%": metrics.get("EPS_G%", pd.NA),
        "REV_G%": metrics.get("REV_G%", pd.NA),
    }


# ------------------------------------------------------------
# 2) 上場日取得ヘルパー
# ------------------------------------------------------------
def first_trade_date(tic: str) -> pd.Timestamp | None:
    """yfinance から上場日らしき timestamp を取得"""
    try:
        info = yf.Ticker(tic).fast_info or {}
        ts = info.get("first_trade_date") or info.get("firstTradeDateEpochUtc")
        if ts and not pd.isna(ts):
            return pd.to_datetime(ts, unit="s", utc=True).tz_localize(None)
    except Exception:
        pass

    try:
        hist = yf.download(
            tic, period="max", interval="1d",
            auto_adjust=False, progress=False, threads=False
        )
        if not hist.empty:
            return hist.index[0].to_pydatetime()
    except Exception:
        pass

    return None


# ------------------------------------------------------------
# 3) 核心: asof 時点で 1 銘柄解析
# ------------------------------------------------------------
def analyze_one_asof(tic: str, asof: pd.Timestamp) -> Dict[str, Any] | None:
    """asof（金曜）時点で 1 銘柄をスクリーニングし合格なら指標 dict を返す"""

    cfg = _sepa_cfg()

    # ── 上場日チェック ───────────────────────
    first_date = first_trade_date(tic)
    if first_date is None:
        counter["no_first_date"] += 1
        return None

    first_date_naive = pd.Timestamp(first_date).tz_localize(None)
    asof_naive       = pd.Timestamp(asof).tz_localize(None)

    if first_date_naive > asof_naive:
        counter["pre_ipo"] += 1
        return None

    start = max(asof_naive - timedelta(weeks=220), first_date_naive)

    # ── 日足取得 → 週足リサンプリ ─────────────
    df_daily = yf.download(
        tic,
        start=start.strftime("%Y-%m-%d"),
        end=(asof + timedelta(days=1)).strftime("%Y-%m-%d"),
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if df_daily.empty:
        counter["no_data"] += 1
        return None

    if isinstance(df_daily.columns, pd.MultiIndex):
        df_daily.columns = df_daily.columns.get_level_values(0)
    df_daily.columns = [c.capitalize() for c in df_daily.columns]
    if "Adj close" in df_daily.columns and "Close" not in df_daily.columns:
        df_daily = df_daily.rename(columns={"Adj close": "Close"})

    df_week = (
        df_daily[["Open", "High", "Low", "Close", "Volume"]]
        .resample("W-FRI")
        .agg(
            {
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            }
        )
        .dropna()
    ).loc[:asof_naive]

    if len(df_week) < MIN_WEEKS:
        counter["short_history"] += 1
        return None

    # ── 1. 流動性フィルタ ─────────────────────
    avg_vol20 = df_daily["Volume"].tail(20).mean()
    last_close = df_week["Close"].iat[-1]

    if avg_vol20 < cfg.get("min_avg_volume", 0):
        counter["liquidity"] += 1
        return None
    if last_close < cfg.get("min_price", 0):
        counter["liquidity"] += 1
        return None

    # ── 2. Trend Template ─────────────────────
    if not trend_template_ok(df_week, debug=DEBUG_TREND).iloc[-1]:
        counter["trend"] += 1
        return None
    if STEP_MODE == "trend":
        return _analyze_one_from_df(tic, df_week)

    # ── 3. Volume Breakout ────────────────────
    # vb_mask = breakout_signal(
    #     df_week,
    #     high_window=HIGH_WINDOW,
    #     vol_window=VOL_WINDOW,
    #     vol_multiplier=VOL_MULTIPLIER,
    # )
    # if not vb_mask.iloc[-LOOKBACK:].any():
    #     counter["volume"] += 1
    #     return None
    # if STEP_MODE == "volume":
    #     return _analyze_one_from_df(tic, df_week)

    # ── 4. Fundamentals ───────────────────────
    metrics = fetch_growth(tic)
    if not isinstance(metrics, dict) or not is_growth_ok(metrics, cfg):
        counter["fund"] += 1
        return None
    if STEP_MODE == "fund":
        return _analyze_one_from_df(tic, df_week)

    # ── 5. All pass ───────────────────────────
    counter["pass"] += 1
    return _analyze_one_from_df(tic, df_week)


# ------------------------------------------------------------
# 4) 週次シグナル一括生成
# ------------------------------------------------------------
def screen(
    top_n: int = 10,
    tickers: List[str] | None = None,
    asof: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """週次 SEPA スクリーニングをまとめて走らせる互換 API"""
    if tickers is None:
        tickers = [
            "AAPL", "MSFT", "NVDA", "AMZN", "META",
            "GOOGL", "TSLA", "BRK-B", "JPM", "UNH",
            "QQQ", "SPY", "DIA", "VTI", "SMH",
        ]

    if asof is None:
        asof = (
            pd.Timestamp.utcnow().normalize()
            - pd.tseries.offsets.Week(weekday=4)
        ).replace(hour=0, minute=0, second=0, microsecond=0)

    rows: List[dict] = []
    for tic in tickers:
        res = analyze_one_asof(tic, asof)
        if res is not None:
            rows.append(res)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values("RS_26w", ascending=False)
    return df.head(top_n)
