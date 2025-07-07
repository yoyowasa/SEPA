"""
WebullClient ユニットテスト

実行方法:
    $ pytest -q tests/test_webull_client.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pytest

from sepa.broker.webull_client import WebullClient


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------
def _make_csv(path: Path, rows: list[dict]) -> None:
    """渡された行データを CSV に書き出す"""
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)


# ---------------------------------------------------------------------------
# テストケース
# ---------------------------------------------------------------------------
def test_place_orders_basic(tmp_path: Path) -> None:
    """正常系: 2 行の注文を紙トレでシミュレーション"""
    csv_path = tmp_path / "screening_results.csv"
    _make_csv(
        csv_path,
        [
            {"symbol": "AAPL", "Qty": 10, "Entry": 150.0, "Stop": 145.0, "TP": 165.0},
            {"symbol": "MSFT", "Qty": 5, "Entry": 320.0, "Stop": 310.0, "TP": 350.0},
        ],
    )

    client = WebullClient(paper=True, logger=logging.getLogger("test"))
    results = client.place_orders_from_csv(csv_path, dry_run=True)

    assert len(results) == 2
    for res in results:
        assert res["status"] == "SIMULATED"
        assert res["qty"] > 0
        assert "timestamp" in res


def test_empty_csv(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """空 CSV → 例外なく空リストを返す & ログが出る"""
    csv_path = tmp_path / "screening_results.csv"
    _make_csv(csv_path, [])

    client = WebullClient(paper=True, logger=logging.getLogger("test"))
    with caplog.at_level(logging.INFO):
        results = client.place_orders_from_csv(csv_path, dry_run=True)

    assert results == []
    assert "nothing to place" in caplog.text.lower()


def test_invalid_schema(tmp_path: Path) -> None:
    """必須カラム欠如 → ValueError"""
    csv_path = tmp_path / "bad.csv"
    _make_csv(csv_path, [{"foo": 1, "bar": 2}])

    client = WebullClient(paper=True)
    with pytest.raises(ValueError):
        client.place_orders_from_csv(csv_path, dry_run=True)
