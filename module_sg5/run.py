"""Run SG-5 Drowsiness Decision & Alert Logic standalone.

    python module_sg5/run.py
    python module_sg5/run.py --dump module_sg5/results/run01.json
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.module_runner import run_module  # noqa: E402
from module_sg5.src.decision import DrowsinessDecider  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run_module(
        name="SG-5 Drowsiness Decision & Alert Logic",
        build=DrowsinessDecider,
        mock_input="mock_temporal.json",
        call=lambda m, temporal, i: m.process(temporal),
        default_config=Path(__file__).parent / "configs" / "default.yaml",
    ))
