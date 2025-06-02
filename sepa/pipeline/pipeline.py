"""
sepa.pipeline
========================================
Minervini SEPA 週足スクリーニング版
Trend Template + 出来高ブレイク

2025-05-17 時点
"""

from __future__ import annotations

import time
from typing import List, Dict, Any

import pandas as pd
import yfinance as yf

from sepa.trend import trend_template
from sepa.patterns import volume_breakout
from sepa.fundamentals import fetch_growth, is_growth_ok
import sepa.risk as rk
# ----------------------------------------------------------------------
# 設定値
# ----------------------------------------------------------------------
DEFAULT_PERIOD = "5y"         # 週足なので 5年取得
INTERVAL = "1wk"              # ★週足へ
HIGH_WINDOW = 10              # 直近10週高値ブレイク
VOL_WINDOW = 10               # 出来高平均も10週
VOL_MULTIPLIER = 1.1          # ブレイク閾値を緩和
LOOKBACK = 4                  # ★直近4週内にブレイクしていればOK
REQUEST_GAP_SEC = 0.2         # 無料API対策

# ----------------------------------------------------------------------
# データ取得
# ----------------------------------------------------------------------
def _fetch_price(ticker: str, period: str = DEFAULT_PERIOD) -> pd.DataFrame:
    """週足OHLCV を取得し MultiIndex を単層化"""
    df = yf.download(
        ticker,
        period=period,
        interval=INTERVAL,
        auto_adjust=False,
        group_by=None,
        progress=False,
    )
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)
    return df

# ----------------------------------------------------------------------
# ティッカー1件を解析
# ----------------------------------------------------------------------
def _analyze_one(ticker: str) -> Dict[str, Any] | None:
    df = _fetch_price(ticker)
    if len(df) < 200:
        return None

    # 1) Trend Template（週足でもそのまま利用可）
    tmpl_mask = trend_template(df)
    last_idx = df.index[-1]
    if not tmpl_mask.loc[last_idx]:
        return None

    # 2) 出来高ブレイク
    brk_mask = volume_breakout(
        df,
        high_window=HIGH_WINDOW,
        vol_window=VOL_WINDOW,
        vol_multiplier=VOL_MULTIPLIER,
    )
    if not brk_mask.iloc[-LOOKBACK:].any():
        return None

    # 3) ファンダメンタル (+25 ％ 以上) --------------★ 追加ブロック
    metrics = fetch_growth(ticker)         # ← sepa.fundamentals
    if not is_growth_ok(metrics):    # 条件未達なら除外
        return None
    # -----------------------------------------------★ ここまで追加

    # --- 指標サマリー（既存カラムは変更しない）
    close = df["Close"].iloc[-1]
    volume = df["Volume"].iloc[-1]
    high_52w = df["High"].rolling(52).max().iloc[-1]   # 週足なので52=1年
    low_52w  = df["Low"].rolling(52).min().iloc[-1]
    rs_26w   = (df["Close"].iloc[-26:] / df["Close"].iloc[-26]).iloc[-1]

    return {
        "Ticker":   ticker,
        "Close":    round(close, 2),
        "Volume":   int(volume),
        "52w_High": round(high_52w, 2),
        "52w_Low":  round(low_52w, 2),
        "RS_26w":   round(rs_26w, 2),

        # ↓★★ 新規ファンダ列（末尾に追加）
        "EPS_G%":   metrics["EPS_G%"],
        "REV_G%":   metrics["REV_G%"],
    }


# ----------------------------------------------------------------------
# 公開関数
# ----------------------------------------------------------------------
def screen(tickers: List[str]) -> pd.DataFrame:
    results: List[Dict[str, Any]] = []
    for tic in tickers:
        hit = _analyze_one(tic)
        if hit:
            results.append(hit)
        time.sleep(REQUEST_GAP_SEC)
    df_hit = pd.DataFrame(results)
    if not df_hit.empty:
        df_hit = df_hit.sort_values("RS_26w", ascending=False).reset_index(drop=True)
    return df_hit

# ----------------------------------------------------------------------
# CLI テスト
# ----------------------------------------------------------------------
if __name__ == "__main__":
    nasdaq100 = pd.read_html(
        "https://en.wikipedia.org/wiki/Nasdaq-100"
    )[4]["Ticker"].tolist()
    df_candidates = screen(nasdaq100[:100])
    print(df_candidates if not df_candidates.empty else "該当なし")
