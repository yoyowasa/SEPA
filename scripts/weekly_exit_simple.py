"""Entry に 10w-SMA ブレイクで Exit を付ける簡易版"""
import pandas as pd, yfinance as yf, warnings, pathlib
warnings.filterwarnings("ignore")

IN_CSV  = pathlib.Path("data/screening_results_weekly.csv")
OUT_CSV = pathlib.Path("data/screening_results_with_exit.csv")

df = pd.read_csv(IN_CSV, parse_dates=["date"])
records = []

for _, row in df.query("entry").iterrows():
    tic, e_dt = row["symbol"], row["date"]

    px = yf.download(tic, start=e_dt, interval="1wk",
                     progress=False)["Adj Close"]
    if px.empty:                     # データ無しはパス
        continue

    sma10 = px.rolling(10, min_periods=1).mean()
    exit_dt = (px < sma10).loc[e_dt:].idxmax()   # 初めて割れた週
    if exit_dt == 0:                # 最後まで割れなければスキップ
        continue

    records.append({
        "symbol": tic,
        "entry_date": e_dt,          "entry_price": px.loc[e_dt],
        "exit_date":  exit_dt,       "exit_price":  px.loc[exit_dt],
    })

pd.DataFrame(records).to_csv(OUT_CSV, index=False)
print("📝  Exit 付き CSV →", OUT_CSV)
