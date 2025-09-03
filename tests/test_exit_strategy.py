import pytest
import pandas as pd
from sepa_trade.strategy.exit_rules import ExitStrategy


def create_test_df(periods: int = 20) -> pd.DataFrame:
    """
    テスト用のOHLCV DataFrameを生成するヘルパー関数。
    デフォルトでは安定した上昇トレンドのデータを生成する。
    """
    dates = pd.date_range(end="2025-07-11", periods=periods, freq="B")
    close = pd.Series([100 + i for i in range(periods)], index=dates, name="Close")
    high = close * 1.01
    low = close * 0.99
    return pd.DataFrame({"High": high, "Low": low, "Close": close})


def test_exit_strategy_ema_cross_true():
    """終値が10EMAを下回った場合にema_cross()がTrueを返すことを確認。"""
    df = create_test_df()
    # 最終日の終値を急落させてEMAクロスを発生させる
    df.iloc[-1, df.columns.get_loc("Close")] = df["Close"].iloc[-2] * 0.9
    strat = ExitStrategy(df, entry_price=110)
    assert strat.ema_cross() is True


def test_exit_strategy_ema_cross_false():
    """終値が10EMAを上回っている場合にema_cross()がFalseを返すことを確認。"""
    df = create_test_df()  # 安定した上昇トレンド
    strat = ExitStrategy(df, entry_price=110)
    assert strat.ema_cross() is False


def test_exit_strategy_atr_trail_true():
    """安値がATR損切りラインを下回った場合にatr_trail()がTrueを返すことを確認。"""
    df = create_test_df()
    entry_price = 115.0

    # 損切りラインを計算するために一度インスタンス化
    temp_strat = ExitStrategy(df.copy(), entry_price)
    latest_atr = temp_strat.df["ATR10"].iloc[-1]
    stop_price = entry_price - latest_atr * 1.5

    # 最終日の安値を損切りラインより下に設定
    df.iloc[-1, df.columns.get_loc("Low")] = stop_price - 0.01

    strat = ExitStrategy(df, entry_price)
    assert strat.atr_trail() is True


def test_exit_strategy_atr_trail_false():
    """安値がATR損切りラインを上回っている場合にatr_trail()がFalseを返すことを確認。"""
    df = create_test_df()
    # エントリー価格が高くても、価格が下落しなければ損切りにはかからない
    strat = ExitStrategy(df, entry_price=118.0)
    assert strat.atr_trail() is False


def test_init_raises_error_on_short_data():
    """データが11日未満の場合にValueErrorが発生することを確認。"""
    df = create_test_df(periods=10)
    with pytest.raises(ValueError, match="ExitStrategyには最低11日分のデータが必要です。"):
        ExitStrategy(df, entry_price=100)
