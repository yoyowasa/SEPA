#!/usr/bin/env python3
"""Download and refresh universe CSV files (S&P 500, NASDAQ‑listed, NYSE‑listed)
into the local *universes/* folder so that generate_weekly_signals.py can load
an up‑to‑date list of symbols without manual copy‑&‑paste.

Usage
-----
$ python universes/update_universe_csvs.py  # writes sp500.csv, nasdaq.csv, nyse.csv

The script hits only public static endpoints (Wikipedia + NASDAQTrader SymDir)
so it usually finishes in a second or two.
"""
from __future__ import annotations

import pandas as pd
from pathlib import Path
import sys
import urllib.error
import urllib.request

# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent  # /your/project/universes
CSV_DIR = BASE_DIR  # keep CSVs next to this script
CSV_DIR.mkdir(exist_ok=True)

# Wikipedia URL for the current S&P 500 table
URL_SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# NASDAQTrader symbol directory (pipe‑delimited ASCII)
URL_NASDAQ = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
# "otherlisted" covers NYSE / NYSE American / NYSE Arca …
URL_OTHER  = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
def _download_pipe_delimited(url: str) -> pd.DataFrame:
    """Fetch NASDAQTrader *.txt file and turn it into a DataFrame."""
    try:
        df = pd.read_csv(url, sep="|", dtype=str)
    except urllib.error.URLError as e:
        sys.exit(f"❌ Network error while fetching {url}: {e}")

    # The file ends with a footer row like: 'File Creation Time:…' → drop it
    return df.iloc[:-1]


def fetch_sp500() -> pd.Series:
    """Return the current S&P 500 ticker list as an upper‑case Series."""
    try:
        table = pd.read_html(URL_SP500, match="Symbol")[0]
    except ValueError as e:
        sys.exit("❌ Failed to parse the Wikipedia S&P 500 table – layout may have changed.")
    return table["Symbol"].str.upper().sort_values().reset_index(drop=True)


def fetch_nasdaq() -> pd.Series:
    df = _download_pipe_delimited(URL_NASDAQ)
    # Skip test issues, ETFs etc. if you wish; here we keep everything except test issues
    tickers = df.loc[df["Test Issue"] != "Y", "Symbol"]
    return tickers.str.upper().sort_values().reset_index(drop=True)


def fetch_nyse() -> pd.Series:
    df = _download_pipe_delimited(URL_OTHER)
    nyse = df.loc[df["Exchange"] == "N", "ACT Symbol"]  # 'N' stands for NYSE classic
    return nyse.str.upper().sort_values().reset_index(drop=True)


def save_series(series: pd.Series, name: str) -> None:
    path = CSV_DIR / f"{name}.csv"
    series.to_csv(path, index=False, header=False)
    print(f"📝  saved {len(series):>5d} symbols → {path.relative_to(Path.cwd())}")


# ──────────────────────────────────────────────────────────────
# Entry‑point
# ──────────────────────────────────────────────────────────────

def main() -> None:
    print("Fetching latest universe files …")
    save_series(fetch_sp500(), "sp500")
    save_series(fetch_nasdaq(), "nasdaq")
    save_series(fetch_nyse(), "nyse")
    print("Done!  You can now re‑run generate_weekly_signals.py with --universe sp500 (or nasdaq / nyse)")


if __name__ == "__main__":
    main()
