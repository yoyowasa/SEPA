import pandas as pd
from sepa_trade.technical_weekly import WeeklyTrendTemplate


def test_weekly_template_passes_true():
    """
    連続上昇する週足データを与えたとき、
    WeeklyTrendTemplate.passes(rs_rating=80) が True を返すことを確認。
    """

    # ── ダミー週足終値（60 週分：100 → 200 に直線上昇） ──
    dates = pd.date_range(end="2025-07-11", periods=60, freq="W-FRI")
    closes = pd.Series(
        data=pd.np.linspace(100, 200, num=60),  # type: ignore
        index=dates,
        name="Close",
    )
    df_weekly = closes.to_frame()

    # ── テンプレート判定 ──
    template = WeeklyTrendTemplate(df_weekly)
    assert template.passes(rs_rating=80) is True

def test_weekly_template_passes_false_on_price_below_ma10():
    """
    株価が10週線を下回るよう改変したデータでは
    WeeklyTrendTemplate.passes(rs_rating=80) が False になることを確認。
    """

    # 先ほどと同じ基礎データを作成
    dates = pd.date_range(end="2025-07-11", periods=60, freq="W-FRI")
    closes = pd.Series(
        pd.np.linspace(100, 200, num=60),  # type: ignore
        index=dates,
        name="Close",
    )

    # 最終週だけ価格を大きく下げて10週線を割り込ませる
    closes.iloc[-1] = closes.iloc[-10] * 0.9  # 10週線より10%下

    df_weekly = closes.to_frame()
    template = WeeklyTrendTemplate(df_weekly)

    assert template.passes(rs_rating=80) is False
