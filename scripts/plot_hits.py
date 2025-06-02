"""
scripts/plot_hits.py
-------------------------------------------------
hits.csv（run_screen.py が生成）を読み込み、
各ティッカーの週足チャートを PNG へ保存するユーティリティ。

追加機能
--------
・出来高ブレイク週を緑 ▲ でマーキング
・52週高値ラインを赤点線で重ね表示
・出来高をサブプロットで表示
・出力先: charts/<TICKER>.png
"""

from pathlib import Path
from typing import List

import pandas as pd
import yfinance as yf
import mplfinance as mpf
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# --- SEPA メソッド共通ロジック --------------------
from sepa.patterns import volume_breakout, vcp_mask, cup_mask 

# ================== 設定 ==================
LOOKBACK_YEARS = 3            # 描画期間（年）
INTERVAL = "1wk"              # 週足
IMG_DIR = Path("charts")      # 出力フォルダ
CSV_PATH = Path("hits.csv")   # run_screen.py が生成
STYLE = "yahoo"               # mplfinance スタイル

# 出来高ブレイク判定パラメータ（pipeline と揃える）
HIGH_WINDOW = 10
VOL_WINDOW = 10
VOL_MULTIPLIER = 1.1
# ==========================================


def load_hits(csv_path: Path = CSV_PATH) -> List[str]:
    """hits.csv からティッカー列を抽出"""
    if not csv_path.exists():
        raise FileNotFoundError(
            f"{csv_path} が見つかりません。先に run_screen.py を実行してください。"
        )
    df = pd.read_csv(csv_path)
    return df["Ticker"].tolist()


def fetch_weekly(ticker: str, years: int = LOOKBACK_YEARS) -> pd.DataFrame:
    """週足データを取得し MultiIndex を単層化"""
    df = yf.download(
        ticker,
        period=f"{years}y",
        interval=INTERVAL,
        auto_adjust=False,
        group_by=None,
        progress=False,
    )
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)
    return df


# ------------------------------------------------------------------
# plot_chart —— チャートを描画し、凡例を付けて保存
# ------------------------------------------------------------------
def plot_chart(df: pd.DataFrame, ticker: str) -> None:
    """
    週足チャートを PNG 保存
      • 赤点線   : 52週高値
      • 緑 ▲    : 出来高ブレイク週
      • 紫 ●    : VCP 完成週（該当がある場合のみ）
      • 水色 ●  : Cup-w/Handle 完成週（該当がある場合のみ）
      • 10 w / 30 w SMA
    """

    # -------------------------------------------------
    # ① 52週高値ライン
    # -------------------------------------------------
    high_52w = df["High"].rolling(window=52).max()
    add_high = mpf.make_addplot(high_52w,
                                color="red",
                                linestyle="dotted",
                                width=1)

    # -------------------------------------------------
    # ② 出来高ブレイク週
    # -------------------------------------------------
    brk_mask = volume_breakout(df,
                               high_window=HIGH_WINDOW,
                               vol_window=VOL_WINDOW,
                               vol_multiplier=VOL_MULTIPLIER)
    brk_y = df["High"].where(brk_mask) * 1.01
    add_break = mpf.make_addplot(brk_y,
                                 type="scatter",
                                 marker="^",
                                 color="green",
                                 markersize=60)
    add_plots = [add_high, add_break]

    # ---------- VCP 完成週（紫） ----------------------------
    vcp_series = vcp_mask(df)
    vcp_y = df["Low"].where(vcp_series) * 0.99
    if vcp_y.notna().any():
        add_vcp = mpf.make_addplot(
            vcp_y,
            type="scatter",
            marker="o",
            color="purple",     # 塗りつぶし円
            markersize=25,      # 小さめ
            linewidths=0.8,
        )
        add_plots.append(add_vcp)
    # ---------- Cup-with-Handle 完成週（水色） --------------
    cup_series = cup_mask(df)
    cup_y = df["Low"].where(cup_series) * 0.97
    if cup_y.notna().any():
        add_cup = mpf.make_addplot(
            cup_y,
            type="scatter",
            marker="o",
            color="skyblue",    # 塗りつぶし円
            markersize=25,
            linewidths=0.8,
        )
        add_plots.append(add_cup)
    # -------------------------------------------------
    # ⑤ addplot & legend を動的に構築
    # -------------------------------------------------
    add_plots = [add_high, add_break]
    legend_elems: list[Line2D] = [
        Line2D([0], [0], color="red", linestyle="dotted", label="52w High"),
        Line2D([0], [0], marker="^", color="green",
               linestyle="None", markersize=8, label="Breakout"),
        Line2D([0], [0], color="C0", label="10w SMA"),
        Line2D([0], [0], color="C1", label="30w SMA"),
    ]

    if vcp_y.notna().any():
        add_plots.append(
            mpf.make_addplot(vcp_y,
                             type="scatter",
                             marker="o",
                             color="purple",
                             markersize=50))
        legend_elems.append(
            Line2D([0], [0], marker="o", color="purple",
                   linestyle="None", markersize=8, label="VCP")
        )

    if cup_y.notna().any():
        add_plots.append(
            mpf.make_addplot(cup_y,
                             type="scatter",
                             marker="o",
                             color="skyblue",
                             markersize=50))
        legend_elems.append(
            Line2D([0], [0], marker="o", color="skyblue",
                   linestyle="None", markersize=8, label="Cup w/ Handle")
        )

    # ---------- 描画 --------------------------------------
    fig, axlist = mpf.plot(
        df,
        type="candle",
        mav=(10, 30),
        volume=True,
        addplot=add_plots,
        title=f"{ticker} (Weekly • {LOOKBACK_YEARS}Y)",
        style=STYLE,
        returnfig=True,
    )
        # ---------- 描画（mpf.plot）が終わった直後に配置 ----------
    legend_elems = [
        Line2D([0], [0], color="red", linestyle="dotted", label="52w High"),
        Line2D([0], [0], marker="^", color="green",
            linestyle="None", markersize=8, label="Breakout"),
        Line2D([0], [0], marker="o", color="purple",
            linestyle="None", markersize=6, label="VCP"),
        Line2D([0], [0], marker="o", color="skyblue",
            linestyle="None", markersize=6, label="Cup w/ Handle"),
        Line2D([0], [0], color="C0", label="10w SMA"),
        Line2D([0], [0], color="C1", label="30w SMA"),
    ]

    axlist[0].legend(handles=legend_elems,
                    loc="upper left",
                    fontsize="small",
                    frameon=True)
    # -------------------------------------------------
    # ⑦ 保存
    # -------------------------------------------------
    outfile = IMG_DIR / f"{ticker}.png"
    fig.savefig(outfile, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {outfile.resolve()}")

# ------------------------------------------------------------------
def main() -> None:
    IMG_DIR.mkdir(exist_ok=True)
    tickers = load_hits()

    for tic in tickers:
        df = fetch_weekly(tic)
        if df.empty:
            print(f"Skip {tic}: no data")
            continue
        plot_chart(df, tic)


if __name__ == "__main__":
    main()
