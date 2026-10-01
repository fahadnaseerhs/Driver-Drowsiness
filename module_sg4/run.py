"""Run SG-4 Temporal Behaviour Analysis standalone.

SG-4 needs TWO inputs (eye + yawn), so it reads mock_eye.json as its primary
sequence and pairs it frame-by-frame with mock_yawn.json.

    python module_sg4/run.py
    python module_sg4/run.py --dump module_sg4/results/run01.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.module_runner import MOCK_DIR, run_module  # noqa: E402
from interfaces.contracts import from_dict  # noqa: E402
from module_sg4.src.temporal import TemporalAnalyser  # noqa: E402

_YAWNS = [from_dict(x) for x in
          json.loads((MOCK_DIR / "mock_yawn.json").read_text(encoding="utf-8"))]

if __name__ == "__main__":
    raise SystemExit(run_module(
        name="SG-4 Temporal Behaviour Analysis (PERCLOS baseline)",
        build=TemporalAnalyser,
        mock_input="mock_eye.json",
        call=lambda m, eye, i: m.process(eye, _YAWNS[i] if i < len(_YAWNS) else None),
        default_config=Path(__file__).parent / "configs" / "default.yaml",
    ))
