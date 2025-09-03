import pytest
import numpy as np
import pandas as pd
from sepa_trade.strategy.vcp_breakout import VCPStrategy, BreakoutSignal


def build_vcp_df(
    periods: int = 65,
    pivot: float = 100.0,
    initial_width: float = 12.0,
    contraction_rate: float = 0.4,
    breakout: bool = True,
    high_volume: bool = True,
) -> pd.DataFrame:
    """
    VCPパターンのDataFrameを生成するヘルパー関数。
    デフォルトでは、VCPStrategyのデフォルトパラメータを通過するデータを生成する。
    """
    idx = pd.date_range(end="2025-07-11", periods=periods, freq="B")
    vol_base = 1_000

    highs, lows, closes, vols = [], [], [], []
    width = initial_width
    # ブレイクアウト日を除く期間のデータを生成
    for _ in range(periods - 1):
        highs.append(pivot)
        lows.append(pivot - width)
        closes.append(pivot - width / 2)
        vols.append(vol_base)
        width *= contraction_rate

    # 最終日（判定日）のデータを生成
    if breakout:
        highs.append(pivot * 1.015)
        closes.append(pivot * 1.01)
    else:
        highs.append(pivot)
        closes.append(pivot - width / 2)

    lows.append(pivot)  # 最終日の安値はピボット価格

    if high_volume:
        vols.append(vol_base * 3)
    else:
        vols.append(vol_base)

    return pd.DataFrame(
        {"High": highs, "Low": lows, "Close": closes, "Volume": vols}, index=idx
    )


def test_vcp_strategy_passes_on_ideal_data():
    """理想的なVCPブレイクアウトデータが正しく検出されることを確認。"""
    df = build_vcp_df()
    # デフォルトパラメータでVCPStrategyをテスト
    strat = VCPStrategy(df, shrink_steps=2, shrink_ratio=0.5, volume_ratio=1.5)
    flag, signal = strat.check_today()

    assert flag is True
    assert isinstance(signal, BreakoutSignal)
    assert np.isclose(signal.breakout_price, df["Close"].iloc[-1])
    # ATRの計算も確認
    assert signal.atr > 0


def test_vcp_strategy_fails_on_insufficient_data():
    """データが60日未満の場合に不合格になることを確認。"""
    df = build_vcp_df(periods=59)
    strat = VCPStrategy(df)
    flag, signal = strat.check_today()
    assert flag is False
    assert signal is None


def test_vcp_strategy_fails_on_no_breakout():
    """価格がピボットをブレイクしない場合に不合格になることを確認。"""
    df = build_vcp_df(breakout=False)
    strat = VCPStrategy(df)
    flag, signal = strat.check_today()
    assert flag is False
    assert signal is None


def test_vcp_strategy_fails_on_low_volume():
    """出来高が不足している場合に不合格になることを確認。"""
    df = build_vcp_df(high_volume=False)
    strat = VCPStrategy(df)
    flag, signal = strat.check_today()
    assert flag is False
    assert signal is None


def test_vcp_strategy_fails_on_no_contraction():
    """ボラティリティが収縮しない場合に不合格になることを確認。"""
    # 収縮率をVCPStrategyのデフォルト(0.5)より大きい0.85に設定
    df = build_vcp_df(contraction_rate=0.85)
    strat = VCPStrategy(df)  # shrink_ratio=0.5
    flag, signal = strat.check_today()
    assert flag is False
    assert signal is None
