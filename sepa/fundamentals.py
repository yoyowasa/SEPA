"""
sepa.fundamentals
==================================================
■ 目的
   - EPS / Revenue の YoY 伸び率を取得し +25 % 基準で合否判定
■ 対応プロバイダー
   1) finnhub : 無料枠で四半期データ可（推奨）
   2) fmp     : 無料枠は年次のみ（fallback 用）
※ config.yaml → .env（python-dotenv）→ OS 環境変数 の順で API キーを解決
==================================================
config.yaml 例
--------------------------------------------------
fundamentals:
  provider: finnhub          # finnhub / fmp
  api_key:  "${FUNDAMENTALS_API_KEY}"
  timeout:  10               # 秒
"""
from __future__ import annotations

import os
import time
import yaml
import requests
from pathlib import Path
from typing import Dict, Any

# ---------------------------------------------------------------
# .env を読み込む  ★修正ここから
# ---------------------------------------------------------------
try:
    from dotenv import load_dotenv

    ROOT_DIR = Path(__file__).resolve().parents[1]   # プロジェクトルート = sepa_project
    DOTENV   = ROOT_DIR / ".env"
    load_dotenv(dotenv_path=DOTENV, override=False)  # 明示パスで読み込む
except ModuleNotFoundError:
    pass  # python-dotenv 未導入でも致命的ではない
# ---------------------------------------------------------------

# ──────────────────────────────────────────────
# 設定読込
# ──────────────────────────────────────────────
CFG_PATH = Path("configs/config.yaml")
CFG: Dict[str, Any] = {}
if CFG_PATH.exists():
    with CFG_PATH.open(encoding="utf-8") as f:
        CFG = yaml.safe_load(f) or {}

F_CFG = CFG.get("fundamentals", {})

PROVIDER = F_CFG.get("provider", "fmp").lower()

# config.yaml → 旧キー名 → .env の順で API キーを解決
API_KEY = (
    F_CFG.get("api_key")              # 推奨キー名
    or F_CFG.get("apikey")            # 旧キー名との互換
    or os.getenv("FUNDAMENTALS_API_KEY")
)

TIMEOUT = F_CFG.get("timeout", 10)

if not API_KEY:
    raise ValueError(
        "fundamentals.api_key が未設定です (config.yaml または .env)。"
    )

# ──────────────────────────────────────────────
# Provider 別内部関数
# --- sepa/fundamentals.py 既存 import の下あたりに貼り付け ---------
def _fetch_finnhub_q(ticker: str) -> dict | None:
    """
    Finnhub 四半期インカムステートメント → EPS／Revenue YoY 伸び率(%)
    戻り値例: {"EPS_G%": 22.3, "REV_G%": 18.7}
    欠損や計算不可なら None
    """
    key = (
        API_KEY if isinstance(API_KEY, str) else API_KEY.get("finnhub")
        or os.getenv("FINNHUB_KEY")
    )
    if not key:
        return None

    url = (
        "https://finnhub.io/api/v1/stock/financials"
        f"?symbol={ticker}&statement=ic&freq=quarter&token={key}"
    )
    try:
        js = requests.get(url, timeout=TIMEOUT).json()
        q = js.get("data", [])
        if len(q) < 5:
            return None
        new, old = q[0], q[4]          # 最新Q と 1年前Q

        def _eps(rec):
            if rec.get("eps") not in (None, 0):
                return rec["eps"]
            ni, sh = rec.get("netIncome"), rec.get("weightedAverageShsOut")
            return ni / sh if ni and sh else None

        eps_new, eps_old = _eps(new), _eps(old)
        rev_new, rev_old = new.get("revenue"), old.get("revenue")

        if None in (eps_new, eps_old, rev_new, rev_old) or 0 in (eps_old, rev_old):
            return None

        eps_g = (eps_new / eps_old - 1) * 100
        rev_g = (rev_new / rev_old - 1) * 100
        return {"EPS_G%": round(eps_g, 1), "REV_G%": round(rev_g, 1)}
    except Exception:
        return None
# --------------------------------------------------------------------

# ------------------------------------------------------------------



def _fetch_fmp_annual(ticker: str) -> Dict[str, float] | None:
    key = (
        API_KEY if isinstance(API_KEY, str) else API_KEY.get("fmp")
        or os.getenv("FMP_API_KEY")
    )
    if not key:
        return None

    url = (
        f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}"
        f"?period=annual&limit=2&apikey={key}"
    )
    try:
        data = requests.get(url, timeout=TIMEOUT).json()
        if len(data) < 2:
            return None
        new, old = data[0], data[1]
        eps_g = (new["eps"] / old["eps"] - 1) * 100
        rev_g = (new["revenue"] / old["revenue"] - 1) * 100
        return {"EPS_G%": round(eps_g, 1), "REV_G%": round(rev_g, 1)}
    except Exception:
        return None


def _fetch_alphav_q(ticker: str) -> dict | None:
    key = (
        API_KEY if isinstance(API_KEY, str) else API_KEY.get("alphav")
        or os.getenv("ALPHAV_KEY")
    )
    if not key:
        return None

    url = (
        f"https://www.alphavantage.co/query?"
        f"function=INCOME_STATEMENT&symbol={ticker}&apikey={key}"
    )
    js = requests.get(url, timeout=TIMEOUT).json()
    q = js.get("quarterlyReports", [])
    if len(q) < 5:
        return None

    new, old = q[0], q[4]           # 最新Q vs 1年前Q
    try:
        eps_g = (float(new["eps"]) / float(old["eps"]) - 1) * 100
        rev_g = (
            float(new["totalRevenue"]) / float(old["totalRevenue"]) - 1
        ) * 100
        return {"EPS_G%": round(eps_g, 1), "REV_G%": round(rev_g, 1)}
    except (ValueError, ZeroDivisionError):
        return None


def _fetch_eod_q(ticker: str) -> dict | None:
    key = (
        API_KEY if isinstance(API_KEY, str) else API_KEY.get("eod")
        or os.getenv("EOD_KEY")
    )
    if not key:
        return None

    url = (
        "https://eodhistoricaldata.com/api/fundamentals/"
        f"{ticker}.US?api_token={key}&filter=Financials::Quarterly::income"
    )
    js = requests.get(url, timeout=TIMEOUT).json()
    if not isinstance(js, dict) or len(js) < 5:
        return None

    items = sorted(js.items(), reverse=True)       # 日付降順
    new, old = items[0][1], items[4][1]
    try:
        eps_g = (new["eps"] / old["eps"] - 1) * 100
        rev_g = (new["totalRevenue"] / old["totalRevenue"] - 1) * 100
        return {"EPS_G%": round(eps_g, 1), "REV_G%": round(rev_g, 1)}
    except (TypeError, ZeroDivisionError):
        return None

# ──────────────────────────────────────────────
# 公開 API
# ──────────────────────────────────────────────
# --- sepa/fundamentals.py 末尾付近 fetch_growth の定義 -------
def fetch_growth(ticker: str) -> dict | None:
    """
    プロバイダ名に応じて成長率を取得して返す。
    """
    if PROVIDER == "finnhub":
        fin = _fetch_finnhub_q(ticker)
        if fin:                               # 取れたらそのまま返す
            return fin
        # 取れなければ FMP 年次でフォールバック
        return _fetch_fmp_annual(ticker)

    # provider が "fmp" などそれ以外の場合
    return _fetch_fmp_annual(ticker)
# -----------------------------------------------------------------



def is_growth_ok(growth: dict | None) -> bool:
    """EPS と Revenue の YoY 伸び率がともに 25 以上なら合格."""
    if not growth:
        return False
    return growth.get("EPS_G%", 0) >= 25 and growth.get("REV_G%") >= 25


# ──────────────────────────────────────────────
# CLI テスト
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys, pprint

    tic = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    m = fetch_growth(tic)
    pprint.pprint({tic: m, "OK": is_growth_ok(m)})
