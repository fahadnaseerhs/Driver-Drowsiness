"""Run SG-3 Yawn & Facial-Cue Analysis standalone.

    python module_sg3/run.py
    python module_sg3/run.py --dump module_sg3/results/run01.json
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.module_runner import run_module  # noqa: E402
from module_sg3.src.yawn_detect import YawnDetector  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run_module(
        name="SG-3 Yawn & Facial-Cue Analysis (MAR baseline)",
        build=YawnDetector,
        mock_input="mock_face.json",
        call=lambda m, face, i: m.process(face),
        default_config=Path(__file__).parent / "configs" / "default.yaml",
    ))
