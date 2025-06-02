r"""
NASDAQ-100 全銘柄を対象に Trend+Breakout スクリーニング
========================================================
使い方:
    (.venv) PS C:\sepa_project> python scripts\run_screen.py [-n 100] [--m 1.4]
      -n : 走査するティッカー数 (1–100, 既定 100 = 全銘柄)
      --m: 出来高倍率 vol_multiplier (既定 1.4)

出力:
    data/screening_results.csv  ← run_backtest.py がそのまま読み込む
        date, symbol, entry, exit, risk_pct, stop_price   の 6 列必須
"""

from __future__ import annotations

# --- 標準ライブラリ ---
from pathlib import Path
import argparse
import sys
import warnings
from typing import List

# --- 外部ライブラリ ---
import pandas as pd
import yfinance as yf

# --- 自作モジュール ---
from sepa import pipeline as pp  # pp.screen(DataFrame) を呼び出す
from sepa import pipeline as pp
pp.is_growth_ok = lambda _: True

warnings.filterwarnings("ignore", category=UserWarning)

# ----------------------------------------------------------------------
# 0. 定数
# ----------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR     = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

OUT_CSV = DATA_DIR / "screening_results.csv"

MAX_CHECK_CHUNK = 20     # yfinance 同時チェック数

# ----------------------------------------------------------------------
# 1. ティッカー取得
# ----------------------------------------------------------------------
def get_nasdaq100() -> list[str]:
    """Wikipedia から NASDAQ-100 ティッカー一覧を取得"""
    try:
        table = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")[4]
        return table["Ticker"].tolist()
    except Exception as e:
        sys.exit(f"[ERROR] NASDAQ-100 取得失敗: {e}")

# ----------------------------------------------------------------------
# 2. 利用可能ティッカーのフィルタ
# ----------------------------------------------------------------------
def filter_available_tickers(tickers: List[str]) -> List[str]:
    """
    yfinance で 1 日分ダウンロードできるティッカーだけ残す。
    タイムアウトや 404 を食らった銘柄は除外し、警告表示。
    """
    good, bad = [], []
    for i in range(0, len(tickers), MAX_CHECK_CHUNK):
        chunk = tickers[i : i + MAX_CHECK_CHUNK]
        try:
            df = yf.download(chunk, period="1d", progress=False, threads=True)["Close"]
            if isinstance(df, pd.Series):
                df = df.to_frame(chunk[0])   # 1 銘柄だけだと Series になる
            for sym in chunk:
                if sym in df.columns and pd.notna(df[sym]).any():
                    good.append(sym)
                else:
                    bad.append(sym)
        except Exception:
            # チャンク丸ごと失敗 → 個別に検証
            for sym in chunk:
                try:
                    tmp = yf.download(sym, period="1d", progress=False, threads=False)["Close"]
                    if pd.notna(tmp).any():
                        good.append(sym)
                    else:
                        bad.append(sym)
                except Exception:
                    bad.append(sym)

    if bad:
        print(f"[WARN] データ取得失敗 → 除外: {bad}")
    return good

# ----------------------------------------------------------------------
# 3. メイン
# ----------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--n", type=int, default=100,
                        help="走査ティッカー数 (1-100)")
    parser.add_argument("--m", type=float, default=1.5,
                        help="出来高倍率 vol_multiplier")
    parser.add_argument("--market", default="US",
                        help="対象市場 (将来拡張用、現状は US のみ)")
    parser.add_argument("--debug-trend", action="store_true",
                        help="Trend+RS 判定のデバッグログを表示する")
    parser.add_argument("--step", choices=["trend", "volume", "fund", "all"],
                        default="all", help="途中段階で停止するデバッグ用フラグ")
    parser.add_argument("--ticker", help="単一ティッカーだけを指定してデバッグ")   # ★追加

    args = parser.parse_args()
    
    if args.ticker:
        tickers_all = [args.ticker.upper()]
        args.n = 1                      # -n を上書き
    else:
        tickers_all = get_nasdaq100()[: args.n]

    # 週次パイプラインへのデバッグ・ステップ設定
    from sepa.pipeline import weekly as w
    w.DEBUG_TREND = args.debug_trend
    w.STEP_MODE   = args.step

    if not 1 <= args.n <= 100:
        sys.exit("[ERROR] -n は 1〜100 の整数で指定してください。")

    tickers_all = get_nasdaq100()[: args.n]
    print(f"▼ 初期ティッカー {len(tickers_all)} 件: {tickers_all}")

    # ――― yfinance ダウンロード可否チェック ―――
    tickers = filter_available_tickers(tickers_all)
    if not tickers:
        sys.exit("[ERROR] 全銘柄ダウンロード失敗。ネット接続または yfinance を確認してください。")
    print(f"▼ 有効ティッカー {len(tickers)} 件: {tickers}")

    # ――― 動的パラメータセット ―――
    pp.VOL_MULTIPLIER = args.m
    print(f"▼ VOL_MULTIPLIER = {pp.VOL_MULTIPLIER}")

    # ――― スクリーニング実行 ―――
    hits = pp.screen(tickers)
    from sepa.pipeline import weekly as w
    print("\n── フィルタ別ドロップ数 ──")
    for k, v in w.counter.items():
        print(f"{k:12}: {v}")
    if hits.empty:
        print("該当銘柄なし (条件を緩めるか、日付レンジを見直してください)")
        return

    # インデックスが日時なら列化
    if isinstance(hits.index, pd.DatetimeIndex) and "date" not in hits.columns:
        hits = hits.reset_index(names="date")

    # 列整形
    required = ["date", "symbol", "entry", "exit", "risk_pct", "stop_price"]
    for col in required:
        if col not in hits.columns:
            hits[col] = pd.NA
    hits = hits[required]

    # 保存
    hits.to_csv(OUT_CSV, index=False, date_format="%Y-%m-%d")
    print(f"\n✅ screening_results.csv に保存 → {OUT_CSV}")
    print(f"レコード数: {len(hits):,}")
    print(hits.head())

# ----------------------------------------------------------------------
if __name__ == "__main__":
    main()
