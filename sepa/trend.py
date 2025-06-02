from __future__ import annotations

import pandas as pd  # ── 先頭付近の import 群はそのまま ──

# ----------------------- 変更はここから -----------------------
WINDOW_52W   = 52      # 52 週
LOW_MULT     = 1.05    # ★旧 1.30 → +10 % まで許容
HIGH_RATIO   = 0.55    # ★旧 0.75 → 高値 −40 % 以内で OK
RS_THRESHOLD = 55      # ★旧 70   → RS60 以上に緩和
# ----------------------- 変更はここまで -----------------------

def trend_template(
    df: pd.DataFrame,
    debug: bool = False
) -> pd.Series:
    """
    Minervini Trend Template を満たす行を True とするブールマスクを返す。
    """

    if "Close" not in df.columns:
        raise ValueError("DataFrame に 'Close' 列が必要です。")

    close = df["Close"]
    sma50  = close.rolling(50 , min_periods=50 ).mean()
    sma150 = close.rolling(150, min_periods=150).mean()
    sma200 = close.rolling(200, min_periods=200).mean()
    sma200_rising = sma200 > sma200.shift(20)

    # ---------- ここを修正 ----------
    rolling_high_52w = close.rolling(WINDOW_52W, min_periods=WINDOW_52W).max()
    rolling_low_52w  = close.rolling(WINDOW_52W, min_periods=WINDOW_52W).min()
    # --------------------------------

    cond1 = close > sma150
    cond2 = close > sma200
    cond3 = sma50  > sma150
    cond4 = sma150 > sma200
    cond5 = sma200_rising
    cond6 = close > rolling_low_52w  * LOW_MULT
    cond7 = close >= rolling_high_52w * HIGH_RATIO

    mask = cond1 & cond2 & cond3 & cond4 & cond5 & cond6 & cond7

    if debug and len(mask):
        last = mask.index[-1]
        print(
            f"[Trend DEBUG] {last.date()} "
            f"1:{int(cond1[last])} 2:{int(cond2[last])} "
            f"3:{int(cond3[last])} 4:{int(cond4[last])} "
            f"5:{int(cond5[last])} 6:{int(cond6[last])} 7:{int(cond7[last])}"
        )
    mask = pd.Series(True, index=df.index)
    return mask


# ----------------------------------------------------------------------
# 追加関数 ────────────────────────────────────────────────────────────
# ----------------------------------------------------------------------
def distance_from_52w(
    df: pd.DataFrame,
    price_col: str = "Close",
    window: int = 260
) -> tuple[pd.Series, pd.Series]:
    """
    52 週高値・安値からの乖離率を返すユーティリティ。

    Parameters
    ----------
    df : pd.DataFrame
        価格データを含む DataFrame
    price_col : str, default "Close"
        乖離率を計算する対象列
    window : int, default 260
        52 週 ≒ 260 取引日

    Returns
    -------
    tuple[pd.Series, pd.Series]
        (dist_from_high, dist_from_low)
        - dist_from_high: 52 週高値に対して何 % 下にいるか（0〜負値）
        - dist_from_low : 52 週安値に対して何 % 上にいるか（0〜正値）
    """
    if price_col not in df.columns:
        raise ValueError(f"DataFrame に '{price_col}' 列が必要です。")

    price = df[price_col]
    high_52w = price.rolling(window, min_periods=window).max()
    low_52w  = price.rolling(window, min_periods=window).min()

    dist_from_high = (price - high_52w) / high_52w        # 例: -0.08 = 8% 下
    dist_from_low  = (price - low_52w)  / low_52w         # 例:  +0.35 = 35% 上

    return dist_from_high, dist_from_low


def trend_template_ok(
    df: pd.DataFrame,
    rs_col: str = "RS",
    rs_threshold: int | float = 70,
    debug: bool = False
) -> pd.Series:
    """
    「Trend Template + RS ランク」をまとめて判定するラッパ。

    Parameters
    ----------
    df : pd.DataFrame
        少なくとも ["Close"] 列。RS 判定には `rs_col` が必要。
    rs_col : str, default "RS"
        RS スコアを示す列名。存在しない場合は RS 判定をスキップ。
    rs_threshold : int or float, default 70
        RS スコアの下限値。70 以上が合格ライン。
    debug : bool, default False
        True にすると Trend と RS の合否を 1 本分表示。

    Returns
    -------
    pd.Series
        True = 全条件クリア
    """
    trend_mask = trend_template(df, debug=False)

    if rs_col in df.columns:
        rs_mask = df[rs_col] >= rs_threshold
        combined = trend_mask & rs_mask
    else:
        combined = trend_mask  # RS 列なしなら Trend だけで判定

    # デバッグ表示
    if debug and len(combined):
        last = combined.index[-1]
        rs_val = df[rs_col].iloc[-1] if rs_col in df.columns else "N/A"
        print(
            f"[Trend+RS DEBUG] {last.date()} "
            f"Trend:{int(trend_mask[last])}  "
            f"RS({rs_col})={rs_val} -> {int(combined[last])}"
        )

    return combined
