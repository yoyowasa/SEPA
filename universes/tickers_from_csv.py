import pandas as pd
from pathlib import Path

def load_tickers_from_csv(csv_path: str | Path) -> list[str]:
    """
    任意の CSV から 'Symbol' 列（大小無視）を見つけて
    ティッカー一覧を返すユーティリティ
    """
    df = pd.read_csv(csv_path)
    # 'symbol' / 'Symbol' / 'SYMBOL' などを許容
    col = next(c for c in df.columns if c.lower() == "symbol")
    return (
        df[col]
        .astype(str)
        .str.strip()
        .str.upper()
        .dropna()
        .unique()
        .tolist()
    )
