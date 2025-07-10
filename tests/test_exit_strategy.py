import pandas as pd
from sepa_trade.strategy.exit_rules import ExitStrategy


def test_exit_strategy_ema_cross_true():
    """
    10EMA を終値で下抜けたケースで
    ExitStrategy.ema_cross() が True になることを確認。
    """
    dates = pd.date_range(end="2025-07-11", periods=15, freq="B")
    close = pd.Series(
        [100 + i for i in range(14)] + [105],
        index=dates,
        name="Close",
    )
    high = close * 1.01
    low = close * 0.99

    df = pd.DataFrame({"High": high, "Low": low, "Close": close})
    strat = ExitStrategy(df, entry_price=110)

    assert bool(strat.ema_cross()) is True
