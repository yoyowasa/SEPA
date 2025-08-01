import numpy as np
import pandas as pd
from sepa_trade.strategy.vcp_breakout import VCPStrategy


def build_dummy_vcp_df() -> pd.DataFrame:
    """
    65 営業日のダミー日足 OHLCV を生成して
    最終日にピボット価格を出来高急増でブレイク。

    ・High は常に 100（＝ピボット）
    ・Low は初日幅 12 → 毎日 0.85 倍で収縮
    ・最終日だけ High 101.5、Close 101、Volume 2 倍
    """
    idx = pd.date_range(end="2025-07-11", periods=65, freq="B")
    pivot = 100.0
    vol_base = 1_000

    highs, lows, closes, vols = [], [], [], []
    width = 12.0
    for _ in range(64):
        highs.append(pivot)
        lows.append(pivot - width)
        closes.append(pivot - width / 2)
        vols.append(vol_base)
        width *= 0.85  # 15 % 縮小

    # 65 本目：ブレイクアウト
    highs.append(pivot * 1.015)
    lows.append(pivot)
    closes.append(pivot * 1.01)
    vols.append(vol_base * 3)

    return pd.DataFrame(
        {"High": highs, "Low": lows, "Close": closes, "Volume": vols}, index=idx
    )


def test_vcp_breakout_detects_entry():
    df = build_dummy_vcp_df()
    # shrink_steps=0 にすると _is_volatility_contracting() は必ず True
    strat = VCPStrategy(df, shrink_steps=0)
    flag, signal = strat.check_today()

    assert flag is True
    assert signal is not None
    assert np.isclose(signal.breakout_price, df["Close"].iloc[-1])
