# sepa/utils/config.py
# --------------------
"""Global project configuration loader.

Usage
-----
from sepa.utils.config import get_config

cfg = get_config()                     # デフォルトパスで読込
sepa_cfg = cfg.get("sepa", {})         # 'sepa:' セクション取得

Notes
-----
- YAML は最初の呼び出し時に 1 度だけロードされ、以降はキャッシュを返す。
- プロジェクトルートからの相対パスで `configs/config.yaml` を探索。
- 別の場所に配置したい場合は `get_config(path="...")` で明示指定。
"""

from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()    
import yaml
from pathlib import Path
from functools import lru_cache

# プロジェクトルート/ configs/config.yaml
_DEFAULT_CFG_PATH = Path(__file__).resolve().parents[2] / "configs" / "config.yaml"


@lru_cache(maxsize=1)
def get_config(path: str | Path | None = None) -> dict:
    """
    Load YAML config as dict (singleton-like).

    Parameters
    ----------
    path : str | Path, optional
        Path to YAML file. If None, `_DEFAULT_CFG_PATH` is used.

    Returns
    -------
    dict
        Parsed configuration.
    """
    cfg_path = Path(path) if path else _DEFAULT_CFG_PATH
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")

    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    return cfg
