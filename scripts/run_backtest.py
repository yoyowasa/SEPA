"""
SEPAトレード – VectorBT バックテストスクリプト
================================================
ファイル : C:\\sepa_project\\scripts\\run_backtest.py
期間   : 2009-01-01 〜 2024-12-31
対象   : 週足スクリーニング済み銘柄（CSV）
前提   :
    1. スクリーニング結果を
         C:/sepa_project/data/screening_results.csv
       に保存していること
       必須列 : date, symbol, entry, exit, risk_pct, stop_price
    2. 価格は yfinance から自動取得
    3. Python 3.10+ / vectorbt==0.25 / yfinance>=0.2
使い方:
    > cd C:\sepa_project
    > python scripts\run_backtest.py
      └─ stats と資産曲線 PNG が reports/ に出力
------------------------------------------------
"""

from __future__ import annotations

# --- 標準ライブラリ ---
from pathlib import Path
from datetime import datetime
import warnings

# --- 外部ライブラリ ---
import pandas as pd
import numpy as np
import yfinance as yf
import vectorbt as vbt

warnings.filterwarnings("ignore", category=UserWarning)
# =========================================================
# ★ ここにグローバル関数として配置 ★
def save_png(path: str, figure):
    import plotly.io as pio
    try:
        figure.write_image(path)
    except Exception as err:
        print("❌ 子プロセス PNG 失敗:", err, flush=True)
# =========================================================

# --- 自作モジュール ---
def main() -> None:   
    # ----------------------------------------------------------------------
    # 0. 設定
    # ----------------------------------------------------------------------
    PROJECT_ROOT = Path(__file__).resolve().parents[1]         # C:\sepa_project
    DATA_CSV     = PROJECT_ROOT / "data" / "screening_results.csv"
    OUT_DIR      = PROJECT_ROOT / "reports"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    START_DATE = "2009-01-01"
    END_DATE   = "2024-12-31"
    INIT_CASH  = 1_000_000.0          # JPY 想定
    FEE_RATE   = 0.001                # 片道 0.1%

    # ----------------------------------------------------------------------
    # 1. スクリーニング結果読み込み
    # ----------------------------------------------------------------------
    if not DATA_CSV.exists():
        raise FileNotFoundError(
            f"'{DATA_CSV}' が見つかりません。週足スクリーニング結果を先に保存してください。"
        )

    df_sig = (
        pd.read_csv(DATA_CSV, parse_dates=["date"])
        .loc[lambda d: (d["date"] >= START_DATE) & (d["date"] <= END_DATE)]
        .sort_values(["symbol", "date"])
        .reset_index(drop=True)
    )

    required_cols = {"date", "symbol", "entry", "exit", "risk_pct"}
    missing = required_cols.difference(df_sig.columns)
    if missing:
        raise ValueError(f"CSV 必須列 {missing} が不足しています。列名を確認してください。")

    symbols = df_sig["symbol"].unique().tolist()
    print(f"バックテスト対象ティッカー数: {len(symbols)} → {symbols}")

    # ----------------------------------------------------------------------
    # 2. 価格データ取得（日足, adjust=True）
    # ----------------------------------------------------------------------
    price_data = (
        yf.download(
            tickers=symbols,
            start=START_DATE,
            end=END_DATE,
            auto_adjust=True,
            progress=False,
            threads=True,
        )["Close"]
        .dropna(how="all")
    )

    if price_data.empty:
        raise RuntimeError("価格データが取得できません。ティッカー名を確認してください。")

    # ----------------------------------------------------------------------
    # 3. シグナル（日次インデックスへマッピング）
    # ----------------------------------------------------------------------
    entries = pd.DataFrame(False, index=price_data.index, columns=symbols)
    exits   = pd.DataFrame(False, index=price_data.index, columns=symbols)
    size_df = pd.DataFrame(np.nan, index=price_data.index, columns=symbols)

    for sym, group in df_sig.groupby("symbol"):
        for _, row in group.iterrows():
            if not row["entry"]:
                continue

            base_date = row["date"]
            try:
                entry_idx = price_data.loc[:base_date].index[-1]
            except IndexError:
                continue

            entries.at[entry_idx, sym] = True

            close_px = price_data.at[entry_idx, sym]
            stop_px  = row.get("stop_price", np.nan)
            risk_pct = row.get("risk_pct", 0.01)

            if pd.notna(stop_px) and stop_px > 0:
                per_unit_loss = abs(close_px - stop_px)
                pos_size = np.floor((INIT_CASH * risk_pct) / per_unit_loss) if per_unit_loss else 0
            else:
                pos_size = np.floor((INIT_CASH * risk_pct) / close_px)

            size_df.at[entry_idx, sym] = pos_size

            if row["exit"]:
                try:
                    exit_idx = price_data.loc[:base_date].index[-1]
                    exits.at[exit_idx, sym] = True
                except IndexError:
                    pass

    size_df = size_df.fillna(0)

    # ----------------------------------------------------------------------
    # 4. VectorBT ポートフォリオ
    # ----------------------------------------------------------------------
    portfolio = vbt.Portfolio.from_signals(
        price_data,
        entries,
        exits,
        size=size_df,
        init_cash=INIT_CASH,
        fees=FEE_RATE,
        slippage=0.0,
        freq="1D",
        call_seq="auto",
    )
     # --- stats 追加項目 ------------------------------------------
    trades = portfolio.trades.records_readable
    trades.to_csv(OUT_DIR / "trades.csv", index=False, encoding="utf-8-sig")
    print(f"📝 trades.csv 保存 → {OUT_DIR/'trades.csv'}")

    # ===== 損益率 [%] 列を付与 =====
    if "Return" in trades.columns:
        trades["Return [%]"] = trades["Return"] * 100
    else:
        pnl_col = "PnL" if "PnL" in trades.columns else "Pnl"
        if "Entry Value" in trades.columns:
            entry_val = trades["Entry Value"]
        elif {"Entry Price", "Size"}.issubset(trades.columns):
            entry_val = trades["Entry Price"] * trades["Size"]
        else:
            raise KeyError("Entry Value/Price 列が見つかりません")
        trades["Return [%]"] = trades[pnl_col] / entry_val * 100

    # ===== 保有日数 [D] 列を付与 =====
    if "Duration" in trades.columns:
        duration = trades["Duration"]
    else:
        duration = (
            pd.to_datetime(trades["Exit Timestamp"]) -
            pd.to_datetime(trades["Entry Timestamp"])
        ).dt.days.clip(lower=1)        # 最低 1 日
        trades["Duration"] = duration

    # -------- stats 追加指標 --------
    stats = portfolio.stats()
    stats.loc["Total Trades"]         = len(trades)
    stats.loc["Win Rate [%]"]         = (trades["Return [%]"] > 0).mean() * 100
    stats.loc["Avg Trade PnL [%]"]    = trades["Return [%]"].mean()
    stats.loc["Avg Hold Period [D]"]  = trades["Duration"].mean()
    
    if "CAGR [%]" not in stats.index:
        total_return = stats.loc["Total Return [%]"] / 100
        years = (pd.to_datetime(END_DATE) - pd.to_datetime(START_DATE)).days / 365.25
        stats.loc["CAGR [%]"] = (1 + total_return) ** (1 / years) * 100 - 100

    if "Sharpe" not in stats.index:
        # ① vectorbt のメソッド
        sharpe_val = portfolio.sharpe_ratio()
        # ② スカラー化（Series/ndarray→平均値）
        if not np.isscalar(sharpe_val):
            sharpe_val = np.nanmean(np.asarray(sharpe_val))
        # ③ Fallback: 手計算が必要ならここに入れる（今回不要）
        stats.loc["Sharpe"] = sharpe_val
    # --------------------------------------------------------
    # --------------------------------------------------------


    # --------------------------------------------------------

    stats.to_csv(OUT_DIR / "vectorbt_stats.csv", encoding="utf-8-sig")

    # 表示用に存在する列だけ抽出
    cols_show = [c for c in ["Total Return [%]", "CAGR [%]", "Max Drawdown [%]", "Sharpe", "Win Rate [%]", "Total Trades",
        "Avg Trade PnL [%]", "Avg Hold Period [D]"]
                if c in stats.index]
    print("\n========== バックテスト結果 (主要指標) ==========")
    print(stats.loc[cols_show])

    # ------------------------------------------------------------------
    # 6. 資産曲線保存 – 低負荷 PNG + タイムアウト（15 秒, Thread 版）
    # ------------------------------------------------------------------
    import plotly.io as pio, threading

    pio.kaleido.scope.default_format = "png"
    pio.kaleido.scope.default_width  = 800
    pio.kaleido.scope.default_height = 450
    pio.kaleido.scope.default_scale  = 1

    fig       = portfolio.value().vbt.plot(title="SEPA Backtest – Equity Curve")
    png_path  = OUT_DIR / "equity_curve.png"
    html_path = OUT_DIR / "equity_curve.html"
    # ---------- 見やすさ調整 ----------
    fig.update_layout(
        width=1920,
        height=720,
        legend=dict(orientation='h', yanchor='bottom', y=1.03,
                    xanchor='left',  x=0),
        margin=dict(l=60, r=30, t=40, b=40)
    )
    # 個別銘柄は非表示、線細く
    fig.for_each_trace(lambda tr: tr.update(line=dict(width=0.7), visible='legendonly'))
    # 合計曲線（最後の trace）だけ太線・黒で表示
    fig.data[-1].update(line=dict(width=3, color='black'), name='Total', visible=True)
    # 対数軸を使いたければ↓をアンコメント
    # fig.update_yaxes(type='log')
    # ----------------------------------

    # fig.update_yaxes(type='log')  # ← 対数軸にしたい場合はアンコメント
    # ----------------------------------


    def _save_png():
        try:
            fig.write_image(str(png_path))
        except Exception as e:
            print("❌ PNG 失敗:", e, flush=True)

    print(">> start save PNG (timeout 15 s)")
    t = threading.Thread(target=_save_png, daemon=True)
    t.start()
    t.join(timeout=15)

    if t.is_alive() or not png_path.exists():
        print("⚠️ PNG timeout / failed → HTML fallback")
        fig.write_html(str(html_path))
        print("✅ HTML saved:", html_path)
    else:
        print("✅ PNG saved:", png_path)

    print(">> end save")


    
if __name__ == "__main__":
    import multiprocessing as mp
    mp.freeze_support()
    main()
