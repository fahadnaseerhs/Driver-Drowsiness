"""Run the whole system. The command you demo with, and the command CI runs.

    # Day one. No camera, no models, no SG-1. Replays the mock driver.
    python integration/run_pipeline.py --source mock

    # Same, and check the alarm fires when the mock scenario says it should.
    python integration/run_pipeline.py --source mock --check-scenario

    # A recorded clip through the real SG-1.
    python integration/run_pipeline.py --source datasets/samples/clip01.mp4

    # Live camera, with the debug overlay (the demo path).
    python integration/run_pipeline.py --source 0 --display

Exit codes, so this is usable as a CI gate:
    0  ran, no contract violations, scenario check passed (if requested)
    1  contract violations, or the scenario check failed
    2  could not run at all (missing source, no modules)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.config import load_config  # noqa: E402
from common.jsonio import write_sequence  # noqa: E402
from common.video import MockFaceSource, make_source  # noqa: E402
from integration.src.pipeline import build_default_pipeline  # noqa: E402
from interfaces.contracts import DrowsinessState  # noqa: E402

MOCK_DIR = ROOT / "interfaces" / "mock"


def load_module_configs() -> dict[str, dict]:
    """Load every module's default.yaml. A missing file is not fatal -- the module
    falls back to the defaults baked into its class."""
    cfgs: dict[str, dict] = {}
    for sg, folder in (("sg1", "module_sg1"), ("sg2", "module_sg2"), ("sg3", "module_sg3"),
                       ("sg4", "module_sg4"), ("sg5", "module_sg5")):
        path = ROOT / folder / "configs" / "default.yaml"
        if path.exists():
            try:
                cfgs[sg] = load_config(path)
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] bad config {path}: {exc}", file=sys.stderr)
    return cfgs


def intervals_from_states(outputs) -> dict[str, list[list[float]]]:
    """Collapse the per-frame state track into [start, end] runs per state."""
    runs: dict[str, list[list[float]]] = {"OK": [], "WARN": [], "ALERT": []}
    if not outputs:
        return runs
    cur = outputs[0].decision.state.value
    start = outputs[0].decision.timestamp
    prev = start
    for fo in outputs[1:]:
        s = fo.decision.state.value
        if s != cur:
            runs[cur].append([round(start, 3), round(prev, 3)])
            cur, start = s, fo.decision.timestamp
        prev = fo.decision.timestamp
    runs[cur].append([round(start, 3), round(prev, 3)])
    return runs


def check_scenario(outputs) -> tuple[bool, list[str]]:
    """Compare the ALERT track against interfaces/mock/scenario.json ground truth.

    The test is deliberately not "match the expected window exactly" -- thresholds
    are meant to be tuned. It asks the two questions that actually matter:
      1. did an alarm fire during the sustained closure?           (no miss)
      2. did any alarm fire while the driver was demonstrably awake? (no false alarm)
    """
    msgs: list[str] = []
    scen_path = MOCK_DIR / "scenario.json"
    if not scen_path.exists():
        return False, ["scenario.json missing -- run interfaces/mock/generate_mocks.py"]

    scen = json.loads(scen_path.read_text(encoding="utf-8"))
    closures = scen["ground_truth"]["eyes_closed_s"]
    sustained = [c for c in closures if (c[1] - c[0]) >= 1.0]
    alert_ts = [fo.decision.timestamp for fo in outputs
                if fo.decision.state is DrowsinessState.ALERT]

    ok = True
    for a, b in sustained:
        # The alarm may legitimately lag the start of the closure -- it has to
        # accumulate evidence. It must fire before the closure ends, plus a little.
        fired = [t for t in alert_ts if a <= t <= b + 0.5]
        if fired:
            msgs.append(f"PASS  alarm fired at {min(fired):.2f}s "
                        f"during the {b - a:.2f}s closure starting {a:.2f}s "
                        f"(lag {min(fired) - a:.2f}s)")
        else:
            ok = False
            msgs.append(f"FAIL  MISS: no alarm during the {b - a:.2f}s closure at {a:.2f}-{b:.2f}s")

    # "Demonstrably awake": the first two seconds, which contain only normal blinks.
    awake_end = 2.0
    false_alarms = [t for t in alert_ts if t < awake_end]
    if false_alarms:
        ok = False
        msgs.append(f"FAIL  FALSE ALARM: {len(false_alarms)} alert frames before "
                    f"{awake_end:.1f}s, first at {min(false_alarms):.2f}s")
    else:
        msgs.append(f"PASS  no false alarm in the alert driver's first {awake_end:.1f}s")

    return ok, msgs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the drowsiness pipeline end to end.")
    ap.add_argument("--source", default="mock",
                    help='"mock" (replay mock_face.json), a camera index like "0", '
                         "or a path to a video file")
    ap.add_argument("--limit", type=int, default=None, help="stop after N frames")
    ap.add_argument("--display", action="store_true",
                    help="show the debug overlay window (needs OpenCV and a screen)")
    ap.add_argument("--dump", type=Path, default=None,
                    help="write the per-frame decisions to this JSON file")
    ap.add_argument("--report", type=Path, default=None,
                    help="write the timing/violation report to this JSON file")
    ap.add_argument("--check-scenario", action="store_true",
                    help="assert the alarm fires where mock scenario.json says it should")
    ap.add_argument("--no-contract-check", action="store_true",
                    help="skip per-frame contract validation (slightly faster)")
    args = ap.parse_args(argv)

    using_mock = args.source == "mock"
    if args.check_scenario and not using_mock:
        print("--check-scenario only means anything with --source mock", file=sys.stderr)
        return 2

    pipe = build_default_pipeline(need_sg1=not using_mock, configs=load_module_configs())
    pipe.check_contracts = not args.no_contract_check

    if pipe.sg2 is None and pipe.sg3 is None and pipe.sg4 is None and pipe.sg5 is None:
        print("no modules could be loaded -- nothing to run", file=sys.stderr)
        return 2

    # Mock mode feeds SG-1's output straight in, bypassing SG-1 entirely.
    faces = None
    if using_mock:
        src = MockFaceSource()
        try:
            faces = src.load()
        except FileNotFoundError:
            print("mock data missing -- run: python interfaces/mock/generate_mocks.py",
                  file=sys.stderr)
            return 2
    else:
        try:
            src = make_source(args.source)
        except Exception as exc:  # noqa: BLE001
            print(f"cannot open source {args.source!r}: {exc}", file=sys.stderr)
            return 2

    renderer = None
    if args.display:
        try:
            from integration.src.overlay import OverlayRenderer
            renderer = OverlayRenderer()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] overlay unavailable ({exc}); continuing without display",
                  file=sys.stderr)

    pipe.reset()
    outputs = pipe.run(src, faces=faces, limit=args.limit,
                       on_frame=(renderer.show if renderer else None))
    if renderer:
        renderer.close()

    if not outputs:
        print("source produced no frames", file=sys.stderr)
        return 2

    # ---- summary ---------------------------------------------------------- #
    rep = pipe.stats.report()
    states = intervals_from_states(outputs)
    n_alert = sum(1 for fo in outputs if fo.decision.state is DrowsinessState.ALERT)
    n_warn = sum(1 for fo in outputs if fo.decision.state is DrowsinessState.WARN)
    peak = max(fo.temporal.drowsy_score for fo in outputs)

    print(f"source            : {args.source}")
    print(f"frames            : {rep['frames']}")
    print(f"states            : OK {rep['frames'] - n_warn - n_alert}  "
          f"WARN {n_warn}  ALERT {n_alert}")
    print(f"peak drowsy_score : {peak:.3f}")
    print(f"end-to-end        : mean {rep['end_to_end'].get('mean_ms', 0):.3f} ms  "
          f"p95 {rep['end_to_end'].get('p95_ms', 0):.3f} ms  "
          f"ceiling {rep['end_to_end'].get('fps_ceiling', 0):.0f} FPS")
    for stage, s in rep["per_stage_ms"].items():
        if s.get("n"):
            print(f"  {stage:<14} mean {s['mean_ms']:.3f} ms  p95 {s['p95_ms']:.3f} ms")
    if rep["module_errors"]:
        print(f"module errors     : {rep['module_errors']}")
    print(f"contract violations: {rep['contract_violation_count']}")
    for v in rep["contract_violations"][:10]:
        print(f"  ! {v}")
    print("state track       :")
    for name in ("OK", "WARN", "ALERT"):
        for a, b in states[name]:
            print(f"  {name:<5} {a:6.2f} -> {b:6.2f} s")

    rc = 1 if rep["contract_violation_count"] else 0

    if args.check_scenario:
        print("scenario check    :")
        passed, msgs = check_scenario(outputs)
        for m in msgs:
            print(f"  {m}")
        if not passed:
            rc = 1

    if args.dump:
        write_sequence(args.dump, [fo.decision for fo in outputs])
        print(f"decisions -> {args.dump}")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        rep["state_intervals"] = states
        rep["peak_drowsy_score"] = round(peak, 4)
        args.report.write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
        print(f"report    -> {args.report}")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
