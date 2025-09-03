import pytest
import numpy as np
import pandas as pd
from sepa_trade.technical_weekly import WeeklyTrendTemplate


def create_passing_df(periods=60, start_val=100, end_val=200) -> pd.DataFrame:
    """
    デフォルトで WeeklyTrendTemplate のチェックをすべて通過する、
    線形に上昇する株価の DataFrame を作成するヘルパー関数。
    """
    dates = pd.date_range(end="2025-07-11", periods=periods, freq="W-FRI")
    close = pd.Series(
        data=np.linspace(start_val, end_val, num=periods),
        index=dates,
        name="Close",
    )
    return close.to_frame()


def test_weekly_template_passes_on_ideal_data():
    """理想的な上昇トレンドのデータがテンプレートを通過することを確認。"""
    df_weekly = create_passing_df()
    template = WeeklyTrendTemplate(df_weekly)
    assert template.passes(rs_rating=80) is True


def test_weekly_template_fails_on_insufficient_data():
    """データが52週未満の場合にテンプレートが不合格になることを確認。"""
    df_weekly = create_passing_df(periods=51)
    template = WeeklyTrendTemplate(df_weekly)
    assert template.passes(rs_rating=80) is False


@pytest.mark.parametrize(
    "condition_to_fail, modification",
    [
        ("low_rs", {"rs_rating": 60}),
        ("price_below_ma", {"price_factor": 0.9}),
        ("ma_cross", {"dip_weeks": 20, "dip_factor": 0.7}),
        ("ma40_slope", {"stagnant_weeks": 5}),
        ("low_pct_from_low", {"start_val": 180, "end_val": 200}),
        ("high_pct_from_high", {"price_dip_factor": 0.7}),
    ],
    ids=[
        "fail_low_rs",
        "fail_price_below_ma10",
        "fail_ma10_below_ma30",
        "fail_ma40_not_rising",
        "fail_low_pct_from_low",
        "fail_high_pct_from_high",
    ],
)
def test_weekly_template_failure_conditions(condition_to_fail, modification):
    """テンプレートが不合格になるべき様々な条件をテストする。"""
    df_weekly = create_passing_df()
    rs_rating = 80  # デフォルトで合格するRSレーティング

    if condition_to_fail == "low_rs":
        rs_rating = modification["rs_rating"]

    elif condition_to_fail == "price_below_ma":
        # 最新の株価を10週MAより下に設定
        template = WeeklyTrendTemplate(df_weekly.copy())
        ma10_val = template.ma10.iloc[-1]
        df_weekly.iloc[-1, df_weekly.columns.get_loc("Close")] = ma10_val * modification["price_factor"]

    elif condition_to_fail == "ma_cross":
        # 短期MAが長期MAを下回るように、一時的な価格の落ち込みを発生させる
        df_weekly.iloc[-modification["dip_weeks"]:, df_weekly.columns.get_loc("Close")] *= modification["dip_factor"]

    elif condition_to_fail == "ma40_slope":
        # 40週MAの上昇を止めるために、数週間の価格を停滞させる
        last_val = df_weekly["Close"].iloc[-(modification["stagnant_weeks"] + 1)]
        df_weekly.iloc[-modification["stagnant_weeks"]:, df_weekly.columns.get_loc("Close")] = last_val

    elif condition_to_fail == "low_pct_from_low":
        # 52週安値からの上昇率が低いデータを作成
        df_weekly = create_passing_df(start_val=modification["start_val"], end_val=modification["end_val"])

    elif condition_to_fail == "high_pct_from_high":
        # 52週高値から大きく下落したデータを作成
        df_weekly.iloc[-1, df_weekly.columns.get_loc("Close")] *= modification["price_dip_factor"]

    template = WeeklyTrendTemplate(df_weekly)
    assert template.passes(rs_rating=rs_rating) is False
