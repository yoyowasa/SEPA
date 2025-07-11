import numpy as np
import pandas as pd
from sepa_trade.strategy.vcp_breakout import VCPStrategy


def build_dummy_vcp_df() -> pd.DataFrame:
    """段階的に 50% 未満へ収縮し、最終日に出来高ブレイクするダミー日足"""
    idx = pd.date_range(end="2025-07-11", periods=25, freq="B")
    vol_base = 1_000
    pivot = 100.0

    highs, lows, closes, vols = [], [], [], []

    widths = [10, 5, 2.4, 1.1]         # 50% より小さく収縮
    for w in widths:
        for _ in range(6):              # 6 日 × 4 ブロック = 24 日
            highs.append(pivot)
            lows.append(pivot - w)
            closes.append(pivot - w / 2)
            vols.append(vol_base)

    # 25 日目：ブレイクアウト
    highs.append(pivot * 1.02)
    lows.append(pivot)
    closes.append(pivot * 1.015)
    vols.append(vol_base * 2)

    return pd.DataFrame(
        {"High": highs, "Low": lows, "Close": closes, "Volume": vols},
        index=idx,
    )


def test_vcp_breakout_detects_entry():
    df = build_dummy_vcp_df()
    strat = VCPStrategy(df, shrink_ratio=0.6)   # 収縮判定を緩める
    flag, signal = strat.check_today()

    assert flag is True
    assert signal is not None
    assert np.isclose(signal.breakout_price, df["Close"].iloc[-1])
