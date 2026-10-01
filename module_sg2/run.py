"""Run SG-2 Eye State & Blink Analysis standalone.

    python module_sg2/run.py
    python module_sg2/run.py --dump module_sg2/results/run01.json
    python module_sg2/run.py --config module_sg2/configs/experiment_a.yaml
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.module_runner import run_module  # noqa: E402
from module_sg2.src.eye_state import EyeStateAnalyser  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run_module(
        name="SG-2 Eye State & Blink Analysis (EAR baseline)",
        build=EyeStateAnalyser,
        mock_input="mock_face.json",
        call=lambda m, face, i: m.process(face),
        default_config=Path(__file__).parent / "configs" / "default.yaml",
    ))
