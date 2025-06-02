import pandas as pd
from pathlib import Path

# ace_tools は ChatGPT 専用。ローカルでは読み込まない
try:
    import ace_tools as tools
except ModuleNotFoundError:
    tools = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRADES_CSV   = PROJECT_ROOT / "reports" / "trades.csv"   # ← 実際にある場所へ

def test_trades_exist():
    assert TRADES_CSV.exists(), "trades.csv が見つかりません"

def test_multiple_trades():
    df = pd.read_csv(TRADES_CSV)
    multi = df.groupby("symbol")["entry"].sum().gt(1).any()
    assert multi, "どの銘柄も複数回トレードしていません"

    # オプション: ChatGPT UI で表を見たいときだけ
    if tools:
        tools.display_dataframe_to_user(
            "複数回トレード銘柄",
            df.groupby("symbol")["entry"].sum().loc[lambda s: s > 1]
               .sort_values(ascending=False).to_frame("Entries")
        )
