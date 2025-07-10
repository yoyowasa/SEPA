import numpy as np
import pandas as pd
from sepa_trade.strategy.vcp_breakout import VCPStrategy


def build_dummy_vcp_df() -> pd.DataFrame:
    """
    25 営業日分のダミー日足 OHLCV を生成。

    0‒4 日   : レンジ幅 10.0
    5‒9 日   : 5.0   （前ブロックの 50 %）
    10‒14 日 : 2.5   （さらに 50 %）
    15‒19 日 : 1.25  （さらに 50 %）
    24 日目  : ピボット 100 を 1 % 上抜け、出来高 2 倍
    """
    rng = pd.date_range(end="2025-07-11", periods=25, freq="B")

    data = {"High": [], "Low": [], "Close": [], "Volume": []}
    volume_base = 1_000
    pivot = 100.0  # 20 日高値になるよう固定

    # 4 ブロック × 5 日で段階収縮
    ranges = [10.0, 5.0, 2.5, 1.25]
    for block, rng_width in enumerate(ranges):
        for _ in range(5):
            hi = pivot
            lo = hi - rng_width
            data["High"].append(hi)
            data["Low"].append(lo)
            data["Close"].append((hi + lo) / 2)
            data["Volume"].append(volume_base)

    # 24 日目（インデックス 24）：ブレイクアウト
    data["High"].append(pivot * 1.02)
    data["Low"].append(pivot * 1.00)
    data["Close"].append(pivot * 1.015)
    data["Volume"].append(volume_base * 2)

    return pd.DataFrame(data, index=rng)


def test_vcp_breakout_detects_entry():
    """ダミー VCP データで check_today がエントリー True を返すか"""
    df = build_dummy_vcp_df()
    strat = VCPStrategy(df)  # shrink_ratio=0.5 デフォルトで通る
    flag, signal = strat.check_today()

    assert flag is True
    assert signal is not None
    # ブレイクアウト価格が終値と一致
    assert np.isclose(signal.breakout_price, df["Close"].iloc[-1])
