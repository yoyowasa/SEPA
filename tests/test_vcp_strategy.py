import numpy as np
import pandas as pd
from sepa_trade.strategy.vcp_breakout import VCPStrategy


def build_dummy_vcp_df() -> pd.DataFrame:
    """
    25営業日のダミー日足 OHLCV を生成。

    • 高値は常に 100（ピボット）  
    • 安値レンジ幅は初日 10 から毎日 0.4 倍で指数的に縮小  
      → rolling(5).max() の連続値も 0.4 倍 (< shrink_ratio=0.5) で減少  
    • 最終日はピボットを 1% 上抜け & Volume 2倍
    """
    idx = pd.date_range(end="2025-07-11", periods=25, freq="B")
    pivot = 100.0
    vol_base = 1_000

    highs, lows, closes, vols = [], [], [], []

    # 0〜23 日：連続収縮
    width = 10.0
    for _ in range(24):
        highs.append(pivot)
        lows.append(pivot - width)
        closes.append(pivot - width / 2)
        vols.append(vol_base)
        width *= 0.4   # 毎日 60% 縮小

    # 24 日（最終日）：ブレイクアウト
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
    strat = VCPStrategy(df)  # shrink_ratio=0.5 デフォルト
    flag, signal = strat.check_today()

    assert flag is True, "VCPStrategy failed to detect breakout"
    assert signal is not None
    assert np.isclose(signal.breakout_price, df["Close"].iloc[-1])
