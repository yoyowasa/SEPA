"""
scripts/test_vcp.py
----------------------------------------
VCP (Volatility Contraction Pattern) 判定の簡易テスト。
NVDA の週足 5 年分で VCP 完成週を抽出し、直近 10 件を表示する。
"""

import yfinance as yf
from sepa.patterns import vcp_mask

def main() -> None:
    df = yf.download("NVDA", period="5y", interval="1wk",
                     auto_adjust=False, group_by=None)
    mask = vcp_mask(df)
    hits = df[mask]
    print(f"VCP 完成週: {len(hits)} 本")
    print(hits.tail(10))   # 直近 10 件表示

if __name__ == "__main__":
    main()
