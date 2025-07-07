#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
dashboard.py
============
screening_results.csv を可視化するダッシュボード。
日足／週足チャートをワンクリックで切替可能。

起動:
    $ streamlit run scripts/dashboard.py
Dependencies:
    streamlit>=1.30, pandas, yfinance, plotly>=5.0
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# ------------------------------------------------------------------ #
# 設定
# ------------------------------------------------------------------ #
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = PROJECT_ROOT / "data" / "screening_results.csv"

st.set_page_config(
    page_title="SEPA Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------------ #
# ユーティリティ
# ------------------------------------------------------------------ #
@st.cache_data(show_spinner=False)
def load_screening_csv(csv_path: Path | str) -> pd.DataFrame:
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        st.error(f"CSV が見つかりません: {csv_path}")
        return pd.DataFrame()
    if not df.empty and "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


@st.cache_data(show_spinner=False)
def fetch_price_history(symbol: str, period: str = "6mo") -> pd.DataFrame:
    """yfinance で日足データを取得し、MultiIndex→単層列へ整形"""
    df = yf.download(
        symbol,
        period=period,
        auto_adjust=False,
        progress=False,
        threads=False,
    )

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.columns = [c.title() for c in df.columns]
    return df


def plot_candlestick(
    df_price: pd.DataFrame,
    symbol: str,
    entry: float | None,
    tp: float | None,
    sl: float | None,
) -> None:
    fig = go.Figure()

    fig.add_trace(
        go.Candlestick(
            x=df_price.index,
            open=df_price["Open"],
            high=df_price["High"],
            low=df_price["Low"],
            close=df_price["Close"],
            name="OHLC",
            increasing_line_color="#16a34a",
            increasing_fillcolor="#16a34a",
            decreasing_line_color="#dc2626",
            decreasing_fillcolor="#dc2626",
            line_width=1.2,
            opacity=1.0,
        )
    )

    # Close ライン
    fig.add_trace(
        go.Scatter(
            x=df_price.index,
            y=df_price["Close"],
            name="Close",
            mode="lines",
            line=dict(color="#facc15", width=1),
            opacity=0.6,
        )
    )

    # SMA 20 / 50
    for win, col in ((20, "#0ea5e9"), (50, "#a855f7")):
        sma = df_price["Close"].rolling(window=win).mean()
        fig.add_trace(
            go.Scatter(
                x=sma.index,
                y=sma,
                name=f"SMA {win}",
                mode="lines",
                line=dict(color=col),
            )
        )

    # Entry / TP / SL
    for label, y_val, color in (
        ("Entry", entry, "#3b82f6"),
        ("TP", tp, "#22c55e"),
        ("SL", sl, "#ef4444"),
    ):
        if y_val and pd.notna(y_val):
            fig.add_hline(
                y=y_val,
                line_width=1,
                line_dash="dash",
                line_color=color,
                annotation_text=label,
                annotation_position="top right",
            )

    fig.update_layout(
        template="plotly_dark",
        height=600,
        title=f"{symbol} — {df_price.index.min().date()} ~ {df_price.index.max().date()}",
        xaxis_rangeslider_visible=False,
    )
    st.plotly_chart(fig, use_container_width=True)


# ------------------------------------------------------------------ #
# サイドバー
# ------------------------------------------------------------------ #
st.sidebar.header("Dashboard Settings")

csv_path_str = st.sidebar.text_input("CSV パス", value=str(DEFAULT_CSV))
csv_path = Path(csv_path_str)

top_n = st.sidebar.number_input("Top N 表示 (0 は全件)", min_value=0, value=50, step=10)

period_opt = st.sidebar.selectbox(
    "期間", ["1mo", "3mo", "6mo", "1y"], index=2  # default 6mo
)

# ★ 足種（日足 / 週足）切替
bar_opt = st.sidebar.radio("足種", ["日足", "週足"], index=0)

if st.sidebar.button("↻ リロード"):
    st.cache_data.clear()
    st.rerun()

# ------------------------------------------------------------------ #
# メイン
# ------------------------------------------------------------------ #
df = load_screening_csv(csv_path)
st.caption(
    f"Last update: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
)

if df.empty:
    st.warning("ヒット銘柄がありません。")
    st.stop()

df_disp = df.head(top_n) if top_n > 0 else df.copy()

st.subheader(f"📋 Screening Results ({len(df_disp):,} rows)")
st.dataframe(df_disp, use_container_width=True, height=300)

symbols = df_disp["symbol"].unique().tolist()
symbol = st.selectbox("銘柄を選択", symbols, index=0)

if symbol:
    row = df_disp[df_disp["symbol"] == symbol].iloc[0]
    entry = row.get("entry") or row.get("Entry")
    tp = row.get("tp_price") or row.get("Tp_price") or row.get("TP")
    sl = row.get("stop_price") or row.get("Stop_price") or row.get("Stop")

    st.markdown("---")
    st.subheader(f"📈 {symbol} Chart")

    with st.spinner("Loading price data…"):
        price_df = fetch_price_history(symbol, period=period_opt)

    # ★ 週足を選択したらリサンプリング
    if bar_opt == "週足" and not price_df.empty:
        price_df = (
            price_df.resample("W")
            .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
            .dropna()
        )

    if price_df.empty:
        st.error("価格データを取得できませんでした。")
    else:
        plot_candlestick(price_df, symbol, entry, tp, sl)
