"""
rs.py

相対強度 (RS: Relative Strength) レーティングを計算するユーティリティ。

- まず各銘柄の「指定期間リターン (%)」を計算
- そのリターンをユニバース内でパーセンタイル化 (0–100)
  → 70 以上なら SEPA のテクニカル条件をクリアしやすい
"""

from __future__ import annotations

from typing import Dict

import pandas as pd


def calc_percent_return(close: pd.Series, lookback: int = 126) -> float:
    """
    指定 lookback 期間の株価リターン (％) を算出。

    Parameters
    ----------
    close : pd.Series
        日次終値。インデックスは日付順に並んでいること。
    lookback : int
        何営業日前からのリターンを測るか。126 ≒ 半年。

    Returns
    -------
    float
        % で表した期間リターン。例: 0.25 → +25%
    """
    if len(close) < lookback + 1:
        raise ValueError("データ不足: close の長さが lookback+1 未満です。")

    past_price = close.iloc[-lookback - 1]
    latest_price = close.iloc[-1]

    if past_price <= 0:
        return float("nan")  # ゼロ除算を防止

    return (latest_price / past_price - 1) * 100


def calc_rs_rating(percent_returns: pd.Series) -> pd.Series:
    """
    ユニバース内の % リターンをパーセンタイル化して RS レーティング (0–100) を返す。

    Parameters
    ----------
    percent_returns : pd.Series
        index=ティッカー、values=lookback リターン (%)

    Returns
    -------
    pd.Series
        index=ティッカー、values=RS レーティング (0–100)
    """
    # NaN を落としてランク
    valid = percent_returns.dropna()
    # rank(pct=True) は 0–1.0、小数を 0–100 にスケール
    rs = valid.rank(pct=True) * 100
    return rs.reindex(percent_returns.index)  # 欠損を保持して元の形に揃える


def compute_rs_universe(
    close_dict: Dict[str, pd.Series], lookback: int = 126
) -> pd.Series:
    """
    ユニバース複数銘柄の終値 Series 辞書を受け取り、
    各銘柄の RS レーティングを一括計算するヘルパー。

    Parameters
    ----------
    close_dict : dict[str, pd.Series]
        key=ticker, value=終値 Series（十分な期間長を持つ）
    lookback : int
        期間リターンの参照営業日数

    Returns
    -------
    pd.Series
        index=ティッカー、values=RS レーティング (0–100)
    """
    # 1. 辞書から DataFrame を作成
    # 銘柄ごとに日付インデックスが異なる場合があるため、
    # pd.DataFrame() よりも pd.concat() の方が堅牢。
    # 各 Series を列として連結し、インデックスの和集合を自動的に作成する。
    all_closes = pd.concat(close_dict, axis=1)

    # 2. lookback 期間に対してデータが不足している銘柄を除外
    #    (各列で非NaN値が lookback+1 個未満のものを削除)
    valid_closes = all_closes.dropna(axis="columns", thresh=lookback + 1)
    if valid_closes.empty:
        return pd.Series(dtype=float).reindex(all_closes.columns)

    # 3. 期間リターンをベクトル演算で一括計算
    past_prices = valid_closes.iloc[-lookback - 1]
    latest_prices = valid_closes.iloc[-1]

    # ゼロ除算を防止
    past_prices[past_prices <= 0] = float("nan")

    pct_returns = (latest_prices / past_prices - 1) * 100

    # 4. RS レーティングを計算し、元のユニバースの形に戻す
    rs = calc_rs_rating(pct_returns)
    return rs.reindex(all_closes.columns)
