"""
sepa.pipeline
========================================
Minervini SEPA 週次スクリーニング用エントリポイント
"""

from __future__ import annotations

# -------------------------------------------------------------
# weekly サブモジュールから公開 API を再エクスポート
# -------------------------------------------------------------
from sepa.pipeline.weekly import screen  # ← TrendRSResult は存在しないため import しない

# パブリックシンボルを明示
__all__: list[str] = ["screen"]
