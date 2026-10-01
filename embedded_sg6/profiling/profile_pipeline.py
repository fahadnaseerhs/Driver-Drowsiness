"""SG-6: profile the pipeline and write a report.

    python embedded_sg6/profiling/profile_pipeline.py --source mock
    python embedded_sg6/profiling/profile_pipeline.py --source 0 --limit 900

On the Jetson, ALWAYS set max clocks first or the numbers mean nothing:
    sudo nvpmodel -m 0 && sudo jetson_clocks

Capture this alongside the script's output:
    tegrastats --interval 1000 --logfile tegrastats.log
This script measures latency and FPS; tegrastats gives GPU/CPU utilisation, memory
and power. Together they are the Figma KPI set. Neither is sufficient alone.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.video import MockFaceSource, make_source  # noqa: E402
from integration.run_pipeline import load_module_configs  # noqa: E402
from integration.src.pipeline import build_default_pipeline  # noqa: E402


def platform_info() -> dict:
    """Record WHERE a measurement was taken. A number without a platform is noise,
    and 'it ran at 40 FPS' means nothing without saying on what."""
    info = {
        "python": sys.version.split()[0],
        "machine": platform.machine(),
        "platform": platform.platform(),
    }
    tegra = Path("/etc/nv_tegra_release")
    if tegra.exists():
        info["l4t"] = tegra.read_text(encoding="utf-8").strip().splitlines()[0]
        try:
            info["power_mode"] = subprocess.run(
                ["nvpmodel", "-q"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
        except Exception:  # noqa: BLE001
            info["power_mode"] = "unknown"
    return info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Profile the pipeline end to end.")
    ap.add_argument("--source", default="mock",
                    help='"mock", a camera index, or a video path')
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "embedded_sg6" / "profiling" / "profile.json")
    args = ap.parse_args(argv)

    using_mock = args.source == "mock"
    pipe = build_default_pipeline(need_sg1=not using_mock, configs=load_module_configs())

    faces = None
    if using_mock:
        faces = MockFaceSource().load()
        source = MockFaceSource()
    else:
        source = make_source(args.source)

    pipe.reset()
    pipe.run(source, faces=faces, limit=args.limit)

    report = pipe.stats.report()
    report["platform"] = platform_info()
    report["source"] = args.source
    report["note"] = (
        "MOCK RUN: measures the pure-Python stages only. SG-1 and camera capture are "
        "excluded, so the FPS ceiling here is NOT a system FPS figure and must never "
        "be quoted as one."
        if using_mock else
        "Set max clocks before trusting these numbers: sudo nvpmodel -m 0 && sudo jetson_clocks"
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
