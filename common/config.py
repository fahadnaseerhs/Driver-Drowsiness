"""Tiny YAML config loader shared by every module.

Each module owns ``module_sgN/configs/default.yaml``. Thresholds live there, never
hard-coded in the algorithm, because Labs 5-7 are a parameter study and you want
to change a number without touching code or re-reading a diff.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path, overrides: dict[str, Any] | None = None) -> dict:
    """Load a YAML config, optionally shallow-merging ``overrides`` on top."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if v is not None})
    return cfg
