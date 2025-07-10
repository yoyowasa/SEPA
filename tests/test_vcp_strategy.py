import numpy as np
import pandas as pd
from sepa_trade.strategy.vcp_breakout import VCPStrategy


def build_dummy_vcp_df() -> pd.DataFrame:
    """
    25 営業日分の日足 OHLCV を生成するテスト用データ。

    - 0–23 日目 : 5×4ブロック → 各ブロック 6 日で
        High 固定100、レンジ幅を 10 → 5 → 2.5 → 1.25 と 50%ずつ縮小
    - 24 日目   : High を 102 (ピボット 100 の 2 % 上) にし、
                  Close は 101.5、Volume を 2 倍にしてブレイクアウト
    """
    idx = pd.date_range(end="2025-07-11", periods=25, freq="B")
    vol_base = 1_000
    pivot = 100.0

    highs, lows, closes, vols = [], [], [], []

    # 4 ブロック × 6 日 = 24 日
    widths = [10, 5, 2.5, 1.25]
    for w in widths:
        for _ in range(6):
            highs.append(pivot)
            lows.append(pivot - w)
            closes.append(pivot - w / 2)
            vols.append(vol_base)

    # 25 日目（ブレイクアウト）
    highs.append(pivot * 1.02)
    lows.append(pivot)
    closes.append(pivot * 1.015)
    vols.append(vol_base * 2)

    return pd.DataFrame(
        {
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": vols,
        },
        index=idx,
    )


def test_vcp_breakout_detects_entry():
    """ダミー VCP データで check_today がエントリー True を返すか"""
    df = build_dummy_vcp_df()
    strat = VCPStrategy(df)  # デフォルト shrink_ratio=0.5 で通る
    flag, signal = strat.check_today()

    assert flag is True
    assert signal is not None
    assert np.isclose(signal.breakout_price, df["Close"].iloc[-1])
