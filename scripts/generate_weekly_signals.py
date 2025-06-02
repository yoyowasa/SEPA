"""週次 SEPA スクリーニング結果を CSV に出力

・‐u/--universe で universes/*.csv から大量ティッカーを読み込み
・-t/--ticker で個別ティッカー（スペース/カンマ区切り両対応）
・指定が無ければ NASDAQ100 のデフォルト 10 銘柄

Usage examples:
    # S&P500 全銘柄
    python scripts/generate_weekly_signals.py -u sp500 --start 2020-01-01 --debug

    # 個別銘柄＋デバッグ
    python scripts/generate_weekly_signals.py -t NVDA TSLA,AMD --start 2022-01-01 --debug
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
from collections import Counter
import argparse
import sys
import pandas as pd

# ──────────────────────────────────────────────────────────────
# ① CLI オプション
# ──────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--start", type=str, default="2009-01-02",
                    help="バックテスト開始日 (YYYY-MM-DD)")
parser.add_argument("--end", type=str, default=None,
                    help="終了日 (省略で今日)")
parser.add_argument("--debug", action="store_true",
                    help="フィルタ別のドロップ件数を表示")
parser.add_argument("--universe", "-u",
                    choices=["sp500", "nasdaq", "nyse"],
                    help="調査対象ユニバースを指定（csv から読み込み）")
parser.add_argument("--ticker", "-t",
                    nargs="+",
                    help="テストしたいティッカーをスペースまたはカンマ区切りで指定")
args = parser.parse_args()

# ──────────────────────────────────────────────────────────────
# ② ティッカー取得ユーティリティ
# ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_DIR = PROJECT_ROOT / "universes"


def expand_ticker_cli(raw_tokens: list[str] | None) -> list[str]:
    """CLI から渡された -t/--ticker を正規化してリスト化"""
    if not raw_tokens:
        return []
    return [s.strip().upper()
            for token in raw_tokens
            for s in token.split(",")
            if s.strip()]


def load_universe(name: str) -> list[str]:
    """universes/<name>.csv から 'Symbol' 列を読み取ってリストで返す"""
    csv_path = UNIVERSE_DIR / f"{name}.csv"
    if not csv_path.exists():
        sys.exit(f"❌ Universe CSV が見つかりません: {csv_path}")

    df = pd.read_csv(csv_path)
    if "Symbol" not in df.columns:
        # ヘッダー無しで保存された場合に備え、一列目を Symbol 扱い
        df.columns = ["Symbol", *df.columns[1:]]
    return (df["Symbol"].astype(str).str.strip().str.upper()
            .dropna().unique().tolist())


# デフォルト NASDAQ100 上位 10 銘柄
DEFAULT_NASDAQ100 = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META",
    "TSLA", "NVDA", "NFLX", "ADBE", "INTC",
]

# ──────────────────────────────────────────────────────────────
# ③ 対象ティッカー決定
# ──────────────────────────────────────────────────────────────
if args.ticker:
    tickers = expand_ticker_cli(args.ticker)
elif args.universe:
    tickers = load_universe(args.universe)
else:
    tickers = DEFAULT_NASDAQ100

print(f"▼ テスト銘柄数: {len(tickers)}")

# ──────────────────────────────────────────────────────────────
# ④ SEPA パイプライン import & デバッグフラグ
# ──────────────────────────────────────────────────────────────
from sepa.pipeline import weekly  # noqa: E402  (after argparse)
weekly.DEBUG_TREND = args.debug
from sepa.pipeline.weekly import analyze_one_asof, counter  # noqa: E402

# ──────────────────────────────────────────────────────────────
# ⑤ 期間設定
# ──────────────────────────────────────────────────────────────
start_day = pd.to_datetime(args.start)
end_day = pd.to_datetime(args.end) if args.end else pd.Timestamp.today().floor("D")

# ──────────────────────────────────────────────────────────────
# ⑥ メインループ
# ──────────────────────────────────────────────────────────────
records: list[pd.DataFrame] = []
holding: set[str] = set()

for dt in pd.date_range(start_day, end_day, freq="W-FRI"):
    results: list[dict] = []
    for tic in tickers:
        rec = analyze_one_asof(tic, dt)
        if rec:
            results.append(rec)

    hits_df = pd.DataFrame(results)
    current = set(hits_df["symbol"]) if not hits_df.empty else set()

    new_entries = current - holding
    exits = holding - current

    if new_entries:
        records.append(
            hits_df.loc[hits_df["symbol"].isin(new_entries)]
                    .assign(date=dt, entry=True, exit=False)
        )
    if exits:
        records.append(
            pd.DataFrame({"symbol": list(exits)})
              .assign(date=dt, entry=False, exit=True,
                      risk_pct=0.01, stop_price=pd.NA)
        )

    holding = current

    # ログ表示
    print(f"{dt.date()}  Hit {len(current):3d}  Entry {len(new_entries):2d}  Exit {len(exits):2d}")
    if args.debug:
        print("   ▼ latest counter :", dict(counter))

# ──────────────────────────────────────────────────────────────
# ⑦ CSV 出力
# ──────────────────────────────────────────────────────────────
OUT_CSV = PROJECT_ROOT / "data" / "screening_results_weekly.csv"
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

if records:
    pd.concat(records, ignore_index=True).to_csv(OUT_CSV, index=False)
    print(f"\n📝 CSV saved → {OUT_CSV}")
else:
    print("\n⚠️  Hit が 1 件も無く、CSV 出力なし")

