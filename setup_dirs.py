# setup_dirs.py
# --------------------------------------------
# SEPA プロジェクトのディレクトリひな型を自動生成するスクリプト
# --------------------------------------------
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 作成するディレクトリ
DIRS = [
    "data",
    "notebooks",
    "configs",
    "logs",
    "scripts",
    "tests",
    "sepa",
    "sepa/backtest",
    "sepa/utils",
]

# 作成するファイルと初期内容
FILES = {
    "README.md": "# SEPA Trading Bot\n\nMinervini SEPA メソッド実装プロジェクト\n",
    "requirements.txt": "",

    "configs/config.yaml": "# API キーや閾値設定を YAML で管理\n",

    # Python パッケージ
    "sepa/__init__.py": "__version__ = '0.1.0'\n",
    "sepa/data_fetcher.py": "",
    "sepa/fundamentals.py": "",
    "sepa/trend.py": "",
    "sepa/patterns.py": "",
    "sepa/risk.py": "",
    "sepa/pipeline.py": "",

    # Backtest モジュール
    "sepa/backtest/__init__.py": "",
    "sepa/backtest/backtest.py": "",

    # Utilities
    "sepa/utils/__init__.py": "",
    "sepa/utils/indicators.py": "",

    # CLI スクリプト（空ファイルを置く）
    "scripts/run_screen.py": "",
    "scripts/run_backtest.py": "",
    "scripts/run_live.py": "",

    # テスト
    "tests/__init__.py": "",
    "tests/test_trend.py": "",
}

def main() -> None:
    # ディレクトリ作成
    for d in DIRS:
        (ROOT / d).mkdir(parents=True, exist_ok=True)

    # ファイル作成（上書きはしない）
    for path, content in FILES.items():
        file_path = ROOT / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if not file_path.exists():
            file_path.write_text(content, encoding="utf-8")

    print("✅ ディレクトリ構造を作成しました。")

if __name__ == "__main__":
    main()
