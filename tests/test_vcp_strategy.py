import numpy as np
import pandas as pd
from sepa_trade.strategy.vcp_breakout import VCPStrategy


def build_dummy_vcp_df() -> pd.DataFrame:
    """
    25 営業日分の日足 OHLCV を生成：
    5 日ごとにレンジ幅を 50 % ずつ収縮し、
    最終日にピボット価格を 1 % 上抜け、出来高 2 倍とする。
    """
    rng = pd.date_range(end="2025-07-11", periods=25, freq="B")
    data = {"High": [], "Low": [], "Close": [], "Volume": []}

    high_start, low_start = 100.0, 90.0
    volume_base = 1_000

    for i in range(24):  # 0〜23 = 24営業日
        block = i // 5
        shrink = 0.5 ** block
        high = high_start * (1 + 0.01 * i) * shrink
        low = low_start * (1 + 0.005 * i) * shrink
        close = (high + low) / 2
        data["High"].append(high)
        data["Low"].append(low)
        data["Close"].append(close)
        data["Volume"].append(volume_base)

    # 最終日：ピボットブレイク
    pivot = max(data["High"][-20:])
    data["High"].append(pivot * 1.02)
    data["Low"].append(pivot * 1.00)
    data["Close"].append(pivot * 1.015)
    data["Volume"].append(volume_base * 2)

    return pd.DataFrame(data, index=rng)


def test_vcp_breakout_detects_entry():
    """ダミー VCP データで check_today がエントリー True を返すか"""
    df = build_dummy_vcp_df()
    strat = VCPStrategy(df, shrink_ratio=0.9)
    flag, signal = strat.check_today()
    assert flag is True
    assert signal is not None
    assert np.isclose(signal.breakout_price, df["Close"].iloc[-1])
