"""Real-data evaluation harness: run the pipeline on labelled clips and report
the Week-3 episode-level metrics against ground truth.

    # The methodology sample -- runs today with no real clips (replays the mock).
    python evaluation/run_eval.py --manifest datasets/manifests/sample_mock.json

    # A real test set, writing the table into a sub-group's results/ folder.
    python evaluation/run_eval.py --manifest datasets/manifests/dusk_glasses_v1.json \
        --out module_sg5/results/dusk_glasses_v1_eval.json

What it does
------------
For every clip in a manifest it runs the SAME pipeline as
``integration/run_pipeline.py`` (SG-2..SG-5 on the mock, or SG-1..SG-5 on a real
video), collapses the per-frame ALERT track into alarm intervals, and scores those
against the clip's ``drowsy_episodes_s`` ground truth using
``evaluation/src/metrics.py`` -- the one shared metric implementation, so every
report in the repo is comparable.

Episode-level, not frame-level: see evaluation/README.md for why. The headline
numbers are recall (missed alarms are the safety-critical failure), precision +
false-alarms-per-hour (R6: a driver disables a nuisance alarm), and alert latency.

Methodology vs graded accuracy
------------------------------
The sample manifest replays ``interfaces/mock`` so the harness is testable before
any real clips exist. The mock is synthetic and geometrically perfect: it proves
the *methodology* runs end to end, NOT accuracy. No graded figure may come from it
(datasets/README.md). Runs on synthetic input are flagged ``graded_accuracy: false``.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.video import MockFaceSource, make_source  # noqa: E402
from evaluation.src.metrics import (  # noqa: E402
    false_alarms_per_hour,
    score_events,
    to_intervals,
)
from integration.run_pipeline import load_module_configs  # noqa: E402
from integration.src.pipeline import build_default_pipeline  # noqa: E402
from interfaces.contracts import DrowsinessState  # noqa: E402

SYNTHETIC_FILES = {"mock"}          # manifest "file" values that mean "replay the mock"


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=5, check=True)
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001 -- a report without a commit is still useful
        return None


def run_clip(file: str, limit: int | None = None):
    """Run the pipeline over one clip source and return its FrameOutput list.

    ``file == "mock"`` replays interfaces/mock (no SG-1, no pixels, no model
    weights) so the harness runs with nothing installed. Any other value is a path
    to a recorded video, which goes through the real SG-1.
    """
    synthetic = file in SYNTHETIC_FILES
    pipe = build_default_pipeline(need_sg1=not synthetic, configs=load_module_configs())
    faces = None
    if synthetic:
        src = MockFaceSource()
        faces = src.load()
    else:
        src = make_source(str((ROOT / file) if not Path(file).is_absolute() else file))
    pipe.reset()
    outputs = pipe.run(src, faces=faces, limit=limit)
    return outputs, pipe


def evaluate_clip(outputs, ground_truth: dict, *, tolerance_s: float = 1.0,
                  max_gap_s: float = 0.2) -> dict[str, Any]:
    """Score one clip's decisions against its ground-truth drowsy episodes."""
    timestamps = [fo.decision.timestamp for fo in outputs]
    alert_flags = [fo.decision.state is DrowsinessState.ALERT for fo in outputs]
    alarms = to_intervals(timestamps, alert_flags, max_gap_s=max_gap_s)

    episodes = [(float(a), float(b)) for a, b in ground_truth.get("drowsy_episodes_s", [])]
    m = score_events(episodes, alarms, tolerance_s=tolerance_s)

    duration_s = (timestamps[-1] - timestamps[0]) if len(timestamps) > 1 else 0.0
    # Per-frame processing latency (the SG-6 KPI) -- distinct from alert latency
    # (time from a drowsy episode starting to the alarm firing), which is in `m`.
    proc = [fo.decision.latency_ms for fo in outputs if fo.decision.latency_ms is not None]
    proc_mean = round(sum(proc) / len(proc), 3) if proc else None
    proc_max = round(max(proc), 3) if proc else None

    out = m.as_dict()
    out.update({
        "frames": len(outputs),
        "duration_s": round(duration_s, 3),
        "drowsy_episodes": [[round(a, 3), round(b, 3)] for a, b in episodes],
        "alarm_intervals": [[round(a, 3), round(b, 3)] for a, b in alarms],
        "false_alarms_per_hour": round(false_alarms_per_hour(m.false_positives, duration_s), 3),
        "proc_latency_ms_mean": proc_mean,
        "proc_latency_ms_max": proc_max,
    })
    return out


def _aggregate(per_clip: list[dict[str, Any]]) -> dict[str, Any]:
    """Pool episode counts across clips into one honest headline."""
    tp = sum(c["true_positives"] for c in per_clip)
    fn = sum(c["false_negatives"] for c in per_clip)
    fp = sum(c["false_positives"] for c in per_clip)
    total_s = sum(c["duration_s"] for c in per_clip)
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "clips": len(per_clip),
        "true_positives": tp,
        "false_negatives": fn,
        "false_positives": fp,
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "f1": round(f1, 4),
        "total_duration_s": round(total_s, 3),
        "false_alarms_per_hour": round(false_alarms_per_hour(fp, total_s), 3),
    }


def evaluate_manifest(manifest_path: Path, *, tolerance_s: float = 1.0,
                      max_gap_s: float = 0.2, limit: int | None = None) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    clips = manifest.get("clips", [])

    per_clip: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    any_synthetic = False

    for clip in clips:
        file = clip["file"]
        synthetic = file in SYNTHETIC_FILES
        any_synthetic = any_synthetic or synthetic
        # Real clips are gitignored and may be absent on this machine; skip them
        # cleanly rather than crash, so the harness still runs on the sample.
        if not synthetic and not (ROOT / file).exists() and not Path(file).is_absolute():
            skipped.append({"file": file, "reason": "clip file not present on this machine"})
            continue
        outputs, pipe = run_clip(file, limit=limit)
        row = {
            "file": file,
            "synthetic": synthetic,
            "subject": clip.get("subject"),
            "glasses": clip.get("glasses"),
            "lighting": clip.get("lighting"),
            "module_errors": dict(pipe.stats.module_errors),
            "contract_violations": pipe.stats.report()["contract_violation_count"],
        }
        row.update(evaluate_clip(outputs, clip.get("ground_truth", {}),
                                 tolerance_s=tolerance_s, max_gap_s=max_gap_s))
        per_clip.append(row)

    graded = (not any_synthetic) and manifest.get("split") not in (None, "sample")
    try:
        # POSIX slashes so a committed report is identical on Windows and Linux.
        manifest_file = manifest_path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        manifest_file = manifest_path.as_posix()  # a manifest outside the repo (e.g. a test tmp dir)
    report: dict[str, Any] = {
        "manifest": manifest.get("name", manifest_path.stem),
        "manifest_file": manifest_file,
        "split": manifest.get("split"),
        "git_commit": _git_commit(),
        "platform": platform.platform(),
        "tolerance_s": tolerance_s,
        "max_gap_s": max_gap_s,
        "config": "each module's configs/default.yaml",
        "graded_accuracy": graded,
        "note": (
            "Synthetic/sample input: proves the methodology runs end to end, NOT "
            "accuracy. No graded figure may come from the mock (datasets/README.md)."
            if not graded else
            "Real-clip evaluation. Confirm the hold-out split was untouched (R5)."
        ),
        "per_clip": per_clip,
        "aggregate": _aggregate(per_clip) if per_clip else {},
        "skipped": skipped,
    }
    return report


def _print_summary(report: dict[str, Any]) -> None:
    print(f"manifest        : {report['manifest']}  (split: {report['split']})")
    print(f"git commit      : {report['git_commit']}")
    print(f"graded accuracy : {report['graded_accuracy']}  -- {report['note']}")
    for c in report["per_clip"]:
        tag = "SYNTHETIC" if c["synthetic"] else "real"
        print(f"  [{tag}] {c['file']}: recall {c['recall']} precision {c['precision']} "
              f"f1 {c['f1']} FA/hr {c['false_alarms_per_hour']} "
              f"alert_latency {c['mean_alert_latency_s']}s "
              f"(TP {c['true_positives']} FN {c['false_negatives']} FP {c['false_positives']})")
        if c["module_errors"] or c["contract_violations"]:
            print(f"        module_errors={c['module_errors']} "
                  f"contract_violations={c['contract_violations']}")
    for s in report["skipped"]:
        print(f"  [SKIP] {s['file']}: {s['reason']}")
    agg = report.get("aggregate") or {}
    if agg:
        print(f"aggregate       : recall {agg['recall']} precision {agg['precision']} "
              f"f1 {agg['f1']} FA/hr {agg['false_alarms_per_hour']} "
              f"over {agg['clips']} clip(s), {agg['total_duration_s']}s")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate the pipeline against labelled clips.")
    ap.add_argument("--manifest", type=Path,
                    default=ROOT / "datasets" / "manifests" / "sample_mock.json",
                    help="dataset manifest (default: the runnable mock sample)")
    ap.add_argument("--out", type=Path, default=None,
                    help="where to write the metrics JSON "
                         "(default: evaluation/reports/<manifest>_eval.json)")
    ap.add_argument("--tolerance-s", type=float, default=1.0,
                    help="an alarm counts for an episode if it starts within this many "
                         "seconds after the episode ends (temporal methods need to "
                         "accumulate evidence)")
    ap.add_argument("--max-gap-s", type=float, default=0.2,
                    help="bridge ALERT dropouts shorter than this into one alarm")
    ap.add_argument("--limit", type=int, default=None, help="stop after N frames per clip")
    args = ap.parse_args(argv)

    if not args.manifest.exists():
        print(f"manifest not found: {args.manifest}", file=sys.stderr)
        return 2

    report = evaluate_manifest(args.manifest, tolerance_s=args.tolerance_s,
                               max_gap_s=args.max_gap_s, limit=args.limit)

    if not report["per_clip"] and not report["skipped"]:
        print("manifest lists no clips", file=sys.stderr)
        return 2

    out = args.out or (ROOT / "evaluation" / "reports" / f"{args.manifest.stem}_eval.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")

    _print_summary(report)
    print(f"metrics -> {out}")
    # Non-zero only on a real failure to produce metrics; a "bad" score is still a
    # successful measurement and must not fail CI.
    return 0 if report["per_clip"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
