import numpy as np
import pandas as pd
from sepa_trade.strategy.vcp_breakout import VCPStrategy


def build_dummy_vcp_df() -> pd.DataFrame:
    """
    25 営業日分のダミー日足 OHLCV を生成。

    ・レンジ幅 (High−Low) を毎日 30 % 縮小させ、段階的収縮を保証
    ・最終日はピボット価格を 1 % 上抜け、出来高 2 倍
    """
    rng = pd.date_range(end="2025-07-11", periods=25, freq="B")

    data = {"High": [], "Low": [], "Close": [], "Volume": []}
    base_high = 100.0
    base_range = 10.0
    volume_base = 1_000

    # 0–23 日目: レンジ幅を毎日 0.7 倍に
    for i in range(24):
        hi = base_high + i * 0.2
        rng_width = base_range * (0.7 ** i)
        lo = hi - rng_width
        data["High"].append(hi)
        data["Low"].append(lo)
        data["Close"].append((hi + lo) / 2)
        data["Volume"].append(volume_base)

    # 24 日目（最終日）: ブレイクアウト
    pivot = max(data["High"][-20:])           # 前日までの 20 日高値
    last_high = pivot * 1.02
    last_low = pivot * 1.00
    last_close = pivot * 1.015

    data["High"].append(last_high)
    data["Low"].append(last_low)
    data["Close"].append(last_close)
    data["Volume"].append(volume_base * 2)    # 出来高急増

    return pd.DataFrame(data, index=rng)


def test_vcp_breakout_detects_entry():
    """ダミー VCP データで check_today がエントリー True を返すか"""
    df = build_dummy_vcp_df()
    strat = VCPStrategy(df, shrink_ratio=0.9)
    flag, signal = strat.check_today()
    assert flag is True
    assert signal is not None
    assert np.isclose(signal.breakout_price, df["Close"].iloc[-1])
