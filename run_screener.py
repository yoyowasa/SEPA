"""
run_screener.py

SEPA 戦略に基づき、有望な銘柄をスクリーニングするエントリーポイント。
"""

import logging

from dotenv import load_dotenv

from sepa_trade.pipeline.screener import SepaScreener

# ログ設定
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# .env ファイルから環境変数を読み込む (FMP_API_KEY など)
load_dotenv()

if __name__ == "__main__":
    # スクリーニング対象の銘柄リスト
    UNIVERSE = [
        "NVDA", "SMCI", "DELL", "TSLA", "AAPL", "MSFT", "GOOGL", "VRT",
        "AMD", "PLTR", "MDB", "CRWD", "CELH", "LULU", "ANF",
    ]

    # スクリーニング設定を一元管理
    SCREENING_CONFIG = {
        "years_back": 2,
        "rs_lookback": 126,
        "min_rs_rating": 70,  # RSレーティングの最低値をここに定義
        "fundamental_filters": {
            "eps_growth_qtr_threshold": 25.0,
            "sales_growth_qtr_threshold": 20.0,
            "margin_improves_sequentially": True,
        },
        "technical_filters": {
            "ma200_lookback": 30,
        },
    }

    # SepaScreenerクラスを使用してスクリーニングを実行
    screener = SepaScreener(
        tickers=UNIVERSE,
        config=SCREENING_CONFIG,
    )

    superperformers = screener.screen()

    print("\n" + "=" * 40)
    if superperformers:
        print("🎉 スクリーニングを通過した銘柄:")
        for stock in superperformers:
            print(f"  - {stock}")
    else:
        print("❌ 今回のスクリーニング条件に合致する銘柄はありませんでした。")
    print("=" * 40)