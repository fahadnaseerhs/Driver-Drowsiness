"""Plot and analyse a per-frame log from ``alarm_demo.py --log``.

    python module_sg5/tools/plot_run.py --log module_sg5/results/live_01.csv
    python module_sg5/tools/plot_run.py --log ... --out module_sg5/results/live_01.png
    python module_sg5/tools/plot_run.py --log ... --from 6860 --to 6890   # zoom a window

WHY
---
A live run produces thousands of frames, and the interesting moments are a few
seconds long. Reading that as text means scrolling past the answer. Four stacked
panels on a shared clock show where the chain actually broke:

    1. EAR, with SG-2's Schmitt-trigger band drawn on it, shaded where SG-2 said
       CLOSED. If the EAR line sits inside the band during a long "closure", the
       closure is an artefact of the hysteresis rather than a shut eye.
    2. Closure duration, with SG-5's 1.20 s override line. Every crossing is an
       alarm SG-5 was obliged to raise.
    3. PERCLOS and drowsy_score, with the escalate/de-escalate thresholds. The
       gap between alert_on and alert_off is the hysteresis SG-5 relies on.
    4. The state track, so you can line an alarm up against its cause above.

The printed analysis is the part that goes in a report: OPEN/CLOSED EAR overlap,
closure-duration distribution, every ALERT episode with its trigger and its
clearing lag, and WARN occupancy.

This reads a log; it never re-runs the pipeline, so the numbers are exactly what
the system did at the time.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path
from typing import Any

MODULE = Path(__file__).resolve().parents[1]

# SG-2 (module_sg2/configs/default.yaml): Schmitt trigger on EAR.
EAR_THRESHOLD = 0.21
EAR_HYSTERESIS = 0.02
# SG-5 (module_sg5/configs/default.yaml).
WARN_ON, WARN_OFF = 0.45, 0.35
ALERT_ON, ALERT_OFF = 0.70, 0.55
CLOSURE_OVERRIDE_S = 1.20


def _f(row: dict, key: str) -> float | None:
    raw = row.get(key, "")
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def load(path: Path, t_from: float | None, t_to: float | None) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit(f"{path} has no rows")
    t0 = _f(rows[0], "t_s") or 0.0

    def as_relative(bound: float | None) -> float | None:
        """Accept either a time from the start of the run or a raw timestamp.
        A live run's clock is time.monotonic(), so its values are huge (6864.25s
        in the first run) -- anything at or above the first timestamp must have
        been copied from the log, and anything below it is relative."""
        if bound is None:
            return None
        return bound - t0 if bound >= t0 else bound

    lo, hi = as_relative(t_from), as_relative(t_to)
    out = []
    for row in rows:
        t = _f(row, "t_s")
        if t is None:
            continue
        rel = t - t0
        if lo is not None and rel < lo:
            continue
        if hi is not None and rel > hi:
            continue
        row["_t"] = t
        row["_rel"] = rel
        out.append(row)
    if not out:
        raise SystemExit("no rows in the requested time range")
    return out


def runs_of(rows: list[dict], key: str, value: str) -> list[tuple[float, float]]:
    """Contiguous [start, end] stretches where row[key] == value."""
    spans: list[tuple[float, float]] = []
    start = None
    prev_t = rows[0]["_rel"]
    for row in rows:
        if row.get(key) == value:
            if start is None:
                start = row["_rel"]
        elif start is not None:
            spans.append((start, prev_t))
            start = None
        prev_t = row["_rel"]
    if start is not None:
        spans.append((start, prev_t))
    return spans


# --------------------------------------------------------------------------- #
def analyse(rows: list[dict]) -> None:
    span = rows[-1]["_rel"] - rows[0]["_rel"]
    print(f"\n=== {len(rows)} frames, {span:.1f} s "
          f"({len(rows) / span:.1f} fps effective) ===")

    faces = sum(1 for r in rows if r.get("face_valid") == "1")
    print(f"face detected        : {faces}/{len(rows)} ({100.0 * faces / len(rows):.1f}%)")

    # --- SG-2: is the eye-state decision separable at all? ------------------ #
    open_ears = [e for r in rows if r.get("eye_state") == "OPEN"
                 and (e := _f(r, "ear")) is not None]
    closed_ears = [e for r in rows if r.get("eye_state") == "CLOSED"
                   and (e := _f(r, "ear")) is not None]
    lo, hi = EAR_THRESHOLD - EAR_HYSTERESIS, EAR_THRESHOLD + EAR_HYSTERESIS
    print(f"\nSG-2 eye state (Schmitt trigger: close below {lo:.2f}, reopen above {hi:.2f})")
    if open_ears:
        print(f"  OPEN   n={len(open_ears):5d}  EAR min/median/max "
              f"{min(open_ears):.3f} / {statistics.median(open_ears):.3f} / {max(open_ears):.3f}")
    if closed_ears:
        print(f"  CLOSED n={len(closed_ears):5d}  EAR min/median/max "
              f"{min(closed_ears):.3f} / {statistics.median(closed_ears):.3f} / "
              f"{max(closed_ears):.3f}")
    if open_ears and closed_ears:
        overlap = sum(1 for e in closed_ears if e >= min(open_ears))
        in_band = sum(1 for e in closed_ears if lo <= e <= hi)
        print(f"  CLOSED frames whose EAR is inside the hysteresis band : {in_band} "
              f"({100.0 * in_band / len(closed_ears):.1f}% of CLOSED)")
        print(f"  CLOSED frames above the lowest OPEN EAR               : {overlap} "
              f"({100.0 * overlap / len(closed_ears):.1f}% of CLOSED)")
        print("  (a high first number means closures are being HELD by the hysteresis "
              "rather than\n   by a shut eye -- that inflates closure_s and PERCLOS, which "
              "is what drives alarms)")

    # --- closures, and which of them were long enough to force an alarm ---- #
    closures = runs_of(rows, "eye_state", "CLOSED")
    durations = sorted((end - start for start, end in closures), reverse=True)
    if durations:
        forced = [d for d in durations if d >= CLOSURE_OVERRIDE_S]
        print(f"\nclosures             : {len(durations)}  "
              f"longest {durations[0]:.2f}s  median {statistics.median(durations):.2f}s")
        print(f"  >= {CLOSURE_OVERRIDE_S:.2f}s (forces ALERT) : {len(forced)}  "
              f"{[round(d, 2) for d in forced[:12]]}")

    blink_rates = [b for r in rows if (b := _f(r, "blink_rate_per_min")) is not None]
    if blink_rates:
        print(f"blink rate /min      : median {statistics.median(blink_rates):.0f}  "
              f"max {max(blink_rates):.0f}   (human resting rate is ~10-20)")

    # --- SG-5: every episode, its trigger, and its clearing lag ------------ #
    print("\nALERT episodes:")
    episodes = runs_of(rows, "state", "ALERT")
    if not episodes:
        print("  none")
    for i, (start, end) in enumerate(episodes, 1):
        trigger = next((r for r in rows if r["_rel"] >= start), None)
        by_override = trigger is not None and "sustained closure" in (
            trigger.get("evidence") or "")
        # When did the eyes reopen for good after the alarm started?
        reopen = None
        for row in rows:
            if row["_rel"] < start:
                continue
            if (_f(row, "current_closure_s") or 0.0) == 0.0 and row.get("eye_state") == "OPEN":
                reopen = row["_rel"]
                break
        lag = None if reopen is None else end - reopen
        kind = "override" if by_override else "score"
        line = (f"  {i}. {start:9.2f} -> {end:9.2f}s  ({end - start:5.2f}s)  "
                f"raised by {kind:8s}")
        if lag is not None:
            flag = "  <-- held LONG after the eyes reopened" if lag > 1.6 else ""
            line += f"  eyes reopened at {reopen:.2f}s, cleared {lag:+.2f}s later{flag}"
        print(line)

    warns = runs_of(rows, "state", "WARN")
    warn_frames = sum(1 for r in rows if r.get("state") == "WARN")
    print(f"\nWARN                 : {len(warns)} entries, {warn_frames} frames "
          f"({100.0 * warn_frames / len(rows):.1f}% of the run)")
    if warns:
        print(f"  longest WARN stretch: {max(e - s for s, e in warns):.2f}s")
        print("  WARN IS REACHABLE on real input -- unlike the synthetic mock, where the "
              "score\n  crosses both thresholds inside one dwell window. See README section 7.")


# --------------------------------------------------------------------------- #
def plot(rows: list[dict], out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")                   # no display needed; we write a file
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    t = [r["_rel"] for r in rows]
    fig, axes = plt.subplots(4, 1, figsize=(16, 11), sharex=True,
                             gridspec_kw={"height_ratios": [3, 2, 3, 1]})
    closed_spans = runs_of(rows, "eye_state", "CLOSED")

    def shade(ax: Any) -> None:
        for start, end in closed_spans:
            ax.axvspan(start, end, color="0.85", zorder=0)

    # 1. EAR and SG-2's trigger band.
    ax = axes[0]
    shade(ax)
    ear_t = [r["_rel"] for r in rows if _f(r, "ear") is not None]
    ear_v = [_f(r, "ear") for r in rows if _f(r, "ear") is not None]
    ax.plot(ear_t, ear_v, lw=0.8, color="#1f77b4", label="EAR")
    ax.axhspan(EAR_THRESHOLD - EAR_HYSTERESIS, EAR_THRESHOLD + EAR_HYSTERESIS,
               color="#ff7f0e", alpha=0.18, zorder=1)
    ax.axhline(EAR_THRESHOLD, color="#ff7f0e", lw=1.0, ls="--")
    ax.set_ylabel("EAR")
    ax.set_title(f"SG-5 live run -- {len(rows)} frames, "
                 f"{rows[-1]['_rel'] - rows[0]['_rel']:.0f} s "
                 "(grey = SG-2 says CLOSED, orange band = Schmitt trigger)")
    ax.legend(handles=[
        Patch(color="#1f77b4", label="EAR"),
        Patch(color="#ff7f0e", alpha=0.3,
              label=f"close < {EAR_THRESHOLD - EAR_HYSTERESIS:.2f} / "
                    f"reopen > {EAR_THRESHOLD + EAR_HYSTERESIS:.2f}"),
        Patch(color="0.85", label="SG-2: CLOSED"),
    ], loc="upper right", fontsize=8)
    ax.grid(alpha=0.3)

    # 2. Closure duration against the override.
    ax = axes[1]
    shade(ax)
    ax.plot(t, [_f(r, "current_closure_s") or 0.0 for r in rows], lw=0.9,
            color="#2ca02c", label="current_closure_s")
    ax.plot(t, [_f(r, "longest_closure_s") or 0.0 for r in rows], lw=0.8,
            color="#8c564b", ls=":", label="longest_closure_s (window max)")
    ax.axhline(CLOSURE_OVERRIDE_S, color="red", lw=1.0, ls="--",
               label=f"override {CLOSURE_OVERRIDE_S:.2f}s")
    ax.set_ylabel("closure (s)")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.3)

    # 3. PERCLOS, score and SG-5's thresholds.
    ax = axes[2]
    shade(ax)
    ax.plot(t, [_f(r, "drowsy_score") or 0.0 for r in rows], lw=1.1,
            color="#d62728", label="drowsy_score")
    ax.plot(t, [_f(r, "perclos") or 0.0 for r in rows], lw=0.9,
            color="#9467bd", label="PERCLOS")
    ax.plot(t, [_f(r, "confidence") or 0.0 for r in rows], lw=0.7,
            color="0.5", ls=":", label="confidence")
    for level, colour, label in ((ALERT_ON, "red", "alert_on 0.70"),
                                 (ALERT_OFF, "red", "alert_off 0.55"),
                                 (WARN_ON, "orange", "warn_on 0.45"),
                                 (WARN_OFF, "orange", "warn_off 0.35")):
        ax.axhline(level, color=colour, lw=0.8,
                   ls="--" if "on" in label else "-.", alpha=0.7, label=label)
    ax.set_ylabel("score / PERCLOS")
    ax.set_ylim(-0.02, 1.05)
    ax.legend(loc="upper right", fontsize=7, ncol=2)
    ax.grid(alpha=0.3)

    # 4. The decision.
    ax = axes[3]
    colours = {"OK": "#2ca02c", "WARN": "#ff7f0e", "ALERT": "#d62728"}
    for state, colour in colours.items():
        for start, end in runs_of(rows, "state", state):
            ax.axvspan(start, end, color=colour, alpha=0.85)
    ax.set_yticks([])
    ax.set_ylabel("state")
    ax.set_xlabel("seconds from the start of the run")
    ax.legend(handles=[Patch(color=c, label=s) for s, c in colours.items()],
              loc="upper right", fontsize=8, ncol=3)

    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    print(f"\nplot -> {out}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plot and analyse an alarm_demo --log CSV.")
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None, help="PNG path (default: next to the log)")
    ap.add_argument("--from", dest="t_from", type=float, default=None,
                    help="start time (seconds, relative or absolute)")
    ap.add_argument("--to", dest="t_to", type=float, default=None, help="end time")
    ap.add_argument("--no-plot", action="store_true", help="print the analysis only")
    args = ap.parse_args(argv)

    if not args.log.exists():
        print(f"error: {args.log} not found", file=sys.stderr)
        return 2
    rows = load(args.log, args.t_from, args.t_to)
    analyse(rows)
    if not args.no_plot:
        try:
            plot(rows, args.out or args.log.with_suffix(".png"))
        except ImportError:
            print("\n(matplotlib missing -- analysis only. pip install -r requirements.txt)",
                  file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
