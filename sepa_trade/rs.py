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
    pct_returns = {
        ticker: calc_percent_return(series, lookback=lookback)
        for ticker, series in close_dict.items()
    }
    pct_series = pd.Series(pct_returns)
    return calc_rs_rating(pct_series)
