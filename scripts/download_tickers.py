#!/usr/bin/env python3
"""
download_tickers.py

S&P500・NASDAQ・NYSE のティッカー一覧を
data/raw/ 配下に CSV 保存するユーティリティ。
"""

from __future__ import annotations

import pathlib
import sys
import requests
import pandas as pd


def save_sp500(path: pathlib.Path) -> None:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    tables = pd.read_html(resp.text)
    if not tables:
        raise RuntimeError("S&P500 テーブル抽出に失敗")

    sp = tables[0]["Symbol"].str.replace(r"\.", "-", regex=True)
    sp.to_csv(path, index=False, header=False)
    print(f"S&P500: {len(sp)} tickers saved → {path}")


def save_nasdaq(path: pathlib.Path) -> None:
    url = "ftp://ftp.nasdaqtrader.com/SymbolDirectory/nasdaqlisted.txt"
    nas_df = pd.read_csv(url, sep="|")
    nas = nas_df["Symbol"].str.replace(r"\^", "", regex=True)
    nas.to_csv(path, index=False, header=False)
    print(f"NASDAQ: {len(nas)} tickers saved → {path}")


def save_nyse(path: pathlib.Path) -> None:
    url = "ftp://ftp.nasdaqtrader.com/SymbolDirectory/otherlisted.txt"
    oth_df = pd.read_csv(url, sep="|")
    nyse = oth_df.loc[oth_df["Exchange"] == "N", "ACT Symbol"].str.replace(r"\^", "", regex=True)
    nyse.to_csv(path, index=False, header=False)
    print(f"NYSE: {len(nyse)} tickers saved → {path}")


def main() -> None:
    root = pathlib.Path("data/raw")
    root.mkdir(parents=True, exist_ok=True)

    try:
        save_sp500(root / "sp500.csv")
    except Exception as e:
        print("⚠️  S&P500 取得失敗:", e, file=sys.stderr)

    save_nasdaq(root / "nasdaq.csv")
    save_nyse(root / "nyse.csv")


if __name__ == "__main__":
    main()
