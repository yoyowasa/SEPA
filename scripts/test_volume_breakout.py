from pathlib import Path
import yfinance as yf
from sepa.patterns import volume_breakout

def main():
    df = yf.download("NVDA", period="6mo")
    mask = volume_breakout(df)
    hits = df[mask]
    print(f"Hit rows: {len(hits)}")
    print(hits.tail())

if __name__ == "__main__":
    main()
