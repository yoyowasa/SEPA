import numpy as np
import pandas as pd
from sepa_trade.strategy.vcp_breakout import VCPStrategy


def build_dummy_vcp_df() -> pd.DataFrame:
    """
    25 営業日分の日足 OHLCV を生成：
    - 5 日ごとにレンジ幅を 50 % ずつ収縮
    - 最終日はピボット価格を 1 % 上抜け、出来高 2 倍
    """
    rng = pd.date_range(end="2025-07-11", periods=25, freq="B")
    data = {"High": [], "Low": [], "Close": [], "Volume": []}

    high_start, low_start = 100.0, 90.0
    volume_base = 1_000

    for i, ts in enumerate(rng[:-1]):  # 最終日手前まで
        block = i // 5  # 0,1,2,3 で 4 ブロック
        shrink = 0.5 ** block
        high = high_start * (1 + 0.01 * i) * shrink
        low = low_start * (1 + 0.005 * i) * shrink
        close = (high + low) / 2
        data["High"].append(high)
        data["Low"].append(low)
        data["Close"].append(close)
        data["Volume"].append(volume_base)

    # ---- 最終日：ピボットブレイク ----
    pivot = max(data["High"][-20:])  # 昨日時点 20 日高値
    last_high = pivot * 1.02
    last_low = pivot * 1.00
    last_close = pivot * 1.015
    data["High"].append(last_high)
    data["Low"].append(last_low)
    data["Close"].append(last_close)
    data["Volume"].append(volume_base * 2)  # 出来高急増

    df = pd.DataFrame(data, index=rng)
    return df


def test_vcp_breakout_detects_entry():
    """ダミーVCPデータで check_today がエントリー True を返すか"""
    df = build_dummy_vcp_df()
    strat = VCPStrategy(df)
    flag, signal = strat.check_today()
    assert flag is True
    assert signal is not None
    # ブレイクアウト価格が最終日の終値と一致
    assert np.isclose(signal.breakout_price, df["Close"].iloc[-1])
