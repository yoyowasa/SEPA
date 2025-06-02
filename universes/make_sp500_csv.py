# make_sp500_csv.py
import pandas as pd

url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
df  = pd.read_html(url)[0]

# Yahoo に合わせて "." → "-" に変換
df["Symbol"] = df["Symbol"].str.replace(".", "-", regex=False)

df[["Symbol"]].to_csv("universes/SP500.csv", index=False)
print("✔ universes/SP500.csv を作成しました")
