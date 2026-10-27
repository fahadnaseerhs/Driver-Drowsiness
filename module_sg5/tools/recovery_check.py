"""End-to-end recovery check: does the alarm let go once the driver's eyes reopen?

    python module_sg5/tools/recovery_check.py
    python module_sg5/tools/recovery_check.py --out module_sg5/results/recovery_check.json

WHY THIS EXISTS
---------------
SG-4 README section 7 and SG-5 README section 7 both record the same symptom: on the
mock clip the state track is ``OK 0.00 -> 6.17 s`` then ``ALERT 6.20 -> 9.97 s``, running
to the end of the clip. The driver's eyes reopen at 7.03 s, so the alarm hangs on for
seconds into recovery -- on the demo that reads as an alarm you cannot switch off, which
is a worse failure mode than a late alarm (risk R6).

Commit 8c9c079 moved SG-5's sustained-closure override from ``longest_closure_s`` (a
backward-looking window MAX, which stays high for a whole window after the eyes reopen)
to ``current_closure_s`` (which drops to 0 the instant they reopen). That fix has unit
tests, but it had never been demonstrated on a run. This tool is that demonstration: it
replays the mock eye/yawn cues through the REAL SG-4 analyser and the REAL SG-5 decider,
both on their shipped default configs, and measures the one number the whole thing is
about -- the lag from the eyes reopening to the alarm clearing.

It measures TWO things separately, because they are not the same claim:

  1. ``override_released_on_reopen`` -- the fix's own mechanism. Did the sustained-closure
     override let go when ``current_closure_s`` fell to 0? To show this is the fix rather
     than a coincidence, the same replay is also run through a COUNTERFACTUAL decider fed
     ``current_closure_s := longest_closure_s``, which is behaviourally identical to the
     pre-8c9c079 code and needs no edit to module_sg5/src.
  2. ``alert_cleared_within_latch`` -- the end-to-end symptom. Once the override is gone,
     normal hysteresis plus ``alert_latch_s`` should drop the state out of ALERT within
     the latch. If the SCORE alone keeps the state up, the alarm is still stuck even
     though the override released, and the user-visible bug is not actually fixed.

The verdict is the AND of the two, so this can serve as a regression gate: exit code 1
when it fails, 0 when it passes.

A note on the tail. The mock clip is 10 s long and the 1.83 s closure only leaves SG-4's
3 s window at about 10.0 s, i.e. after the last mock frame. Measuring a clearing time at
all therefore needs a few more eyes-open frames than the mock provides, so the replay
appends synthetic ones (``--tail-s``, default 4.0). Every number taken from that stretch
is flagged ``synthetic_tail`` in the JSON, and ``cleared_during_mock_clip`` records
whether the clearing happened inside the real mock frames or not.

NOT AN ACCURACY MEASUREMENT. The input is interfaces/mock -- synthetic, geometrically
perfect, no camera noise. datasets/README.md is explicit that no graded accuracy figure
may come from it, so the report carries ``"graded_accuracy": false``. This proves the
mechanism, not the performance.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.config import load_config  # noqa: E402
from common.jsonio import read_sequence  # noqa: E402
from interfaces.contracts import (  # noqa: E402
    DecisionResult,
    DrowsinessState,
    EyeResult,
    EyeState,
    TemporalResult,
    YawnResult,
)
from module_sg4.src.temporal import TemporalAnalyser  # noqa: E402
from module_sg5.src.decision import DrowsinessDecider  # noqa: E402

MOCK_DIR = ROOT / "interfaces" / "mock"
DEFAULT_OUT = ROOT / "module_sg5" / "results" / "recovery_check.json"
FPS = 30.0

NOT_ACCURACY_NOTE = (
    "Synthetic mock input (interfaces/mock). This check proves the recovery MECHANISM "
    "-- that the sustained-closure override releases and the state leaves ALERT -- not "
    "accuracy. datasets/README.md forbids any graded accuracy figure from the mock."
)


# --------------------------------------------------------------------------- #
# Input
# --------------------------------------------------------------------------- #
def load_pairs(tail_s: float) -> tuple[list[tuple[EyeResult, YawnResult]], int]:
    """Mock eye/yawn cues paired BY INDEX (same frame), plus a synthetic open-eye tail.

    Pairing by index rather than by frame_id is what the pipeline does, and SG-4 fails
    loudly on a frame_id mismatch, so a bad pairing cannot pass silently here.

    Returns (pairs, n_mock) so callers can tell real frames from the appended tail.
    """
    eyes: list[EyeResult] = read_sequence(MOCK_DIR / "mock_eye.json")
    yawns: list[YawnResult] = read_sequence(MOCK_DIR / "mock_yawn.json")
    if len(eyes) != len(yawns):
        raise SystemExit(f"mock length mismatch: {len(eyes)} eye vs {len(yawns)} yawn frames")

    pairs = list(zip(eyes, yawns, strict=True))
    n_mock = len(pairs)
    if tail_s <= 0.0:
        return pairs, n_mock

    # The mock ends ~0.03 s before the long closure leaves SG-4's 3 s window, so without
    # a few more frames there is no clearing time to measure at all. These are flagged
    # as synthetic everywhere they influence a reported number.
    last_eye = eyes[-1]
    for k in range(1, int(round(tail_s * FPS)) + 1):
        fid = last_eye.frame_id + k
        ts = round(last_eye.timestamp + k / FPS, 4)
        pairs.append((
            EyeResult(frame_id=fid, timestamp=ts, valid=True, reason="",
                      ear_left=0.30, ear_right=0.30, ear=0.30,
                      eye_state=EyeState.OPEN, closure_duration_s=0.0, confidence=0.95),
            YawnResult(frame_id=fid, timestamp=ts, valid=True, reason="",
                       mar=0.20, confidence=0.95),
        ))
    return pairs, n_mock


def longest_closure_span(eyes: list[EyeResult]) -> tuple[float, float, float]:
    """(onset_s, reopen_s, duration_s) of the longest closure in the mock eye track.

    Derived from the EyeResult track itself rather than hard-coded, so this keeps working
    if interfaces/mock/generate_mocks.py changes the scenario. ``reopen_s`` is the
    timestamp of the first frame on which the eyes are observed open again -- that is the
    moment the driver has demonstrably recovered, and the moment the clearing lag is
    measured from.
    """
    best = (0.0, 0.0, 0.0)
    run_start: float | None = None
    for e in eyes:
        closed = e.valid and e.eye_state is EyeState.CLOSED
        if closed and run_start is None:
            run_start = e.timestamp
        elif not closed and run_start is not None:
            if e.timestamp - run_start > best[2]:
                best = (run_start, e.timestamp, e.timestamp - run_start)
            run_start = None
    if run_start is not None:                  # clip ends mid-closure: no reopen observed
        end = eyes[-1].timestamp
        if end - run_start > best[2]:
            best = (run_start, float("nan"), end - run_start)
    return best


# --------------------------------------------------------------------------- #
# Replay
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class Step:
    """One replayed frame: SG-4's view of the window and SG-5's answer to it."""

    temporal: TemporalResult
    decision: DecisionResult
    synthetic: bool


def replay(pairs: list[tuple[EyeResult, YawnResult]], n_mock: int,
           sg4_cfg: dict, sg5_cfg: dict, *, key_on_longest: bool = False) -> list[Step]:
    """Drive the real SG-4 -> SG-5 chain over the paired cues.

    ``key_on_longest`` reproduces the pre-8c9c079 behaviour without touching
    module_sg5/src: overwriting ``current_closure_s`` with ``longest_closure_s`` makes the
    override's test ``current_closure_s >= closure_override_s`` exactly the old
    ``longest_closure_s >= closure_override_s``. That is the counterfactual arm.
    """
    sg4 = TemporalAnalyser(sg4_cfg)
    sg5 = DrowsinessDecider(sg5_cfg)
    sg4.reset()
    sg5.reset()

    steps: list[Step] = []
    for i, (eye, yawn) in enumerate(pairs):
        temporal = sg4.process(eye, yawn)
        fed = temporal
        if key_on_longest and temporal.valid:
            fed = dataclasses.replace(temporal, current_closure_s=temporal.longest_closure_s)
        decision = sg5.process(fed)
        steps.append(Step(temporal=fed, decision=decision, synthetic=i >= n_mock))
    return steps


def transitions(steps: list[Step]) -> list[dict]:
    """Every state change as (timestamp, from_state, to_state, evidence)."""
    out: list[dict] = []
    prev = DrowsinessState.OK                  # DrowsinessDecider.reset() starts in OK
    for s in steps:
        if s.decision.state is not prev:
            out.append({
                "timestamp_s": round(s.decision.timestamp, 4),
                "frame_id": s.decision.frame_id,
                "from_state": prev.value,
                "to_state": s.decision.state.value,
                "evidence": s.decision.evidence,
                "synthetic_tail": s.synthetic,
            })
            prev = s.decision.state
    return out


def override_was_active(step: Step, threshold: float) -> bool:
    """Whether SG-5's sustained-closure override fired on this frame.

    Recomputed from the TemporalResult SG-5 was actually handed, using the same test
    decision.py applies, because the override is internal to process() and not reported
    on DecisionResult. ``evidence`` is cross-checked below so a drift between this
    reimplementation and the real one would show up rather than be assumed away.
    """
    return step.temporal.valid and step.temporal.current_closure_s >= threshold


def override_span(steps: list[Step], threshold: float) -> tuple[float | None, float | None]:
    """(first, last) timestamps on which the override was active; (None, None) if never."""
    active = [s.decision.timestamp for s in steps if override_was_active(s, threshold)]
    if not active:
        return None, None
    return round(min(active), 4), round(max(active), 4)


def first_alert_s(steps: list[Step]) -> float | None:
    for s in steps:
        if s.decision.state is DrowsinessState.ALERT:
            return round(s.decision.timestamp, 4)
    return None


def alert_cleared_s(steps: list[Step], after_s: float) -> float | None:
    """Timestamp of the first non-ALERT frame after the alarm last fired at/after ``after_s``.

    "Cleared" means the first frame on or after the reopen where the state is no longer
    ALERT AND it never returns to ALERT for the rest of the replay. Taking the first dip
    instead would let a one-frame flicker count as recovery.
    """
    tail = [s for s in steps if s.decision.timestamp >= after_s]
    if not tail:
        return None
    last_alert_i: int | None = None
    for i, s in enumerate(tail):
        if s.decision.state is DrowsinessState.ALERT:
            last_alert_i = i
    if last_alert_i is None:                   # already out of ALERT at the reopen
        return round(tail[0].decision.timestamp, 4)
    if last_alert_i + 1 >= len(tail):          # still ALERT on the final frame
        return None
    return round(tail[last_alert_i + 1].decision.timestamp, 4)


def window_around(steps: list[Step], centre_s: float, threshold: float,
                  before: int, after: int) -> list[dict]:
    """longest_closure_s and current_closure_s side by side around the reopening moment.

    This table is the point of the whole report: a reader should be able to see that
    longest_closure_s stays pinned at its window maximum while current_closure_s falls
    off a cliff to 0, and that the override follows the latter.
    """
    idx = next((i for i, s in enumerate(steps) if s.decision.timestamp >= centre_s), None)
    if idx is None:
        return []
    lo, hi = max(0, idx - before), min(len(steps), idx + after + 1)
    rows = []
    for s in steps[lo:hi]:
        t, d = s.temporal, s.decision
        rows.append({
            "frame_id": d.frame_id,
            "timestamp_s": round(d.timestamp, 4),
            "longest_closure_s": round(t.longest_closure_s, 4),
            "current_closure_s": round(t.current_closure_s, 4),
            "drowsy_score": round(t.drowsy_score, 4),
            "state": d.state.value,
            "override_active": override_was_active(s, threshold),
            "synthetic_tail": s.synthetic,
        })
    return rows


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def build_report(steps: list[Step], counterfactual: list[Step], n_mock: int,
                 eyes: list[EyeResult], sg4_cfg: dict, sg5_cfg: dict,
                 tail_s: float) -> dict:
    latch_s = float(sg5_cfg.get("alert_latch_s", 1.50))
    override_s = float(sg5_cfg.get("closure_override_s", 1.20))
    onset, reopen, closure_dur = longest_closure_span(eyes)
    mock_end = eyes[-1].timestamp

    alert_at = first_alert_s(steps)
    cleared_at = alert_cleared_s(steps, after_s=reopen)
    onset_lag = None if alert_at is None else round(alert_at - onset, 4)
    clear_lag = None if cleared_at is None else round(cleared_at - reopen, 4)

    # Mechanism arm: the override must stop firing once the eyes are open again.
    ov_from, ov_until = override_span(steps, override_s)
    cf_from, cf_until = override_span(counterfactual, override_s)
    released = ov_until is not None and ov_until < reopen
    release_lag = None if ov_until is None else round(reopen - ov_until, 4)

    # End-to-end arm: with the override gone, the latch should let the state fall.
    cleared_in_latch = clear_lag is not None and clear_lag <= latch_s

    # Does the fix change the USER-VISIBLE clearing time on this input, or only the
    # override? If the two arms clear at the same instant, the score path -- not the
    # override -- is what holds the alarm here, and 8c9c079 is necessary but not
    # sufficient. Worth stating explicitly rather than leaving a reader to diff tracks.
    cf_cleared_at = alert_cleared_s(counterfactual, after_s=reopen)
    fix_changes_clearing = cleared_at != cf_cleared_at

    verdict = bool(released and cleared_in_latch)
    if verdict:
        reason = (f"override released {release_lag:.4f}s before the reopen and ALERT cleared "
                  f"{clear_lag:.4f}s after it, inside alert_latch_s={latch_s:.2f}s")
    elif not released:
        reason = ("the sustained-closure override was still firing after the eyes reopened "
                  "-- the override is not keyed on current_closure_s")
    elif cleared_at is None:
        reason = (f"the override released on the reopen, but the state was STILL ALERT at the "
                  f"end of the replay ({steps[-1].decision.timestamp:.4f}s); the drowsy_score "
                  f"alone is holding the alarm on")
    else:
        reason = (f"the override released on the reopen, but ALERT took {clear_lag:.4f}s to "
                  f"clear, which is longer than alert_latch_s={latch_s:.2f}s; the alarm is "
                  f"being held by the drowsy_score, not by the override")

    return {
        "check": "sg5_recovery_after_sustained_closure",
        "what_it_proves": (
            "that SG-5's sustained-closure override releases when the eyes reopen "
            "(commit 8c9c079: override keyed on current_closure_s, not longest_closure_s) "
            "and whether the alarm then actually clears end to end"
        ),
        "graded_accuracy": False,
        "note": NOT_ACCURACY_NOTE,
        "input": {
            "eye": "interfaces/mock/mock_eye.json",
            "yawn": "interfaces/mock/mock_yawn.json",
            "paired_by": "index (same frame); SG-4 rejects a frame_id mismatch",
            "mock_frames": n_mock,
            "mock_duration_s": round(mock_end, 4),
            "synthetic_tail_s": round(tail_s, 4),
            "synthetic_tail_frames": len(steps) - n_mock,
            "synthetic_tail_why": (
                "the 1.83s closure only leaves SG-4's 3s window at ~10.0s, after the last "
                "mock frame, so eyes-open frames are appended to make a clearing time "
                "measurable at all; every number taken from them is flagged synthetic_tail"
            ),
        },
        "configs": {
            "sg4": "module_sg4/configs/default.yaml",
            "sg5": "module_sg5/configs/default.yaml",
            "window_s": float(sg4_cfg.get("window_s", 3.0)),
            "closure_ref_s": float(sg4_cfg.get("closure_ref_s", 1.50)),
            "alert_on": float(sg5_cfg.get("alert_on", 0.70)),
            "alert_off": float(sg5_cfg.get("alert_off", 0.55)),
            "alert_latch_s": latch_s,
            "closure_override_s": override_s,
        },
        "closure": {
            "onset_s": round(onset, 4),
            "reopen_s": round(reopen, 4),
            "duration_s": round(closure_dur, 4),
            "derived_from": "mock EyeResult eye_state / closure_duration_s track",
        },
        "alert": {
            "first_alert_s": alert_at,
            "onset_to_alert_lag_s": onset_lag,
            "cleared_s": cleared_at,
            "reopen_to_clear_lag_s": clear_lag,
            "cleared_during_mock_clip": bool(cleared_at is not None and cleared_at <= mock_end),
            "state_at_end_of_mock_clip": next(
                (s.decision.state.value for s in reversed(steps) if not s.synthetic), None),
        },
        "override": {
            "fixed_keyed_on": "current_closure_s",
            "fixed_active_from_s": ov_from,
            "fixed_active_until_s": ov_until,
            "released_before_reopen": released,
            "release_lead_on_reopen_s": release_lag,
            "counterfactual_keyed_on": "longest_closure_s (pre-8c9c079 behaviour)",
            "counterfactual_active_from_s": cf_from,
            "counterfactual_active_until_s": cf_until,
            "counterfactual_still_firing_after_reopen_s": (
                None if cf_until is None else round(max(0.0, cf_until - reopen), 4)),
            "counterfactual_cleared_s": cf_cleared_at,
            "fix_changes_end_to_end_clearing": fix_changes_clearing,
            "fix_changes_end_to_end_clearing_note": (
                "False means both arms leave ALERT at the same instant: on this input the "
                "drowsy_score keeps the state up long after the override has let go, so "
                "8c9c079 fixes the override but not the stuck alarm the user sees"
            ),
        },
        "around_reopen": window_around(steps, centre_s=reopen, threshold=override_s,
                                       before=3, after=5),
        "transitions": transitions(steps),
        "counterfactual_transitions": transitions(counterfactual),
        "verdict": {
            "pass": verdict,
            "override_released_on_reopen": released,
            "alert_cleared_within_latch": cleared_in_latch,
            "reason": reason,
        },
    }


def print_summary(rep: dict) -> None:
    c, a, o, v = rep["closure"], rep["alert"], rep["override"], rep["verdict"]
    latch = rep["configs"]["alert_latch_s"]

    print("SG-5 recovery check -- does the alarm let go when the eyes reopen?")
    print(f"  input           : {rep['input']['eye']} + {rep['input']['yawn']} "
          f"({rep['input']['mock_frames']} mock frames"
          f" + {rep['input']['synthetic_tail_frames']} synthetic open-eye frames)")
    print(f"  eyes closed     : {c['onset_s']:.3f}s  ({c['duration_s']:.3f}s closure)")
    print(f"  eyes reopened   : {c['reopen_s']:.3f}s")
    print(f"  first ALERT     : {_fmt(a['first_alert_s'])}  "
          f"(lag from closure onset {_fmt(a['onset_to_alert_lag_s'])})")
    print(f"  ALERT cleared   : {_fmt(a['cleared_s'])}  "
          f"(lag from reopen {_fmt(a['reopen_to_clear_lag_s'])})  "
          f"<-- the number this check exists for")
    print(f"  within latch?   : {v['alert_cleared_within_latch']} "
          f"(alert_latch_s = {latch:.2f}s)")
    print(f"  cleared inside the real mock clip: {a['cleared_during_mock_clip']}")

    print("  override (sustained closure):")
    print(f"    keyed on current_closure_s : active {_fmt(o['fixed_active_from_s'])} -> "
          f"{_fmt(o['fixed_active_until_s'])}, released "
          f"{_fmt(o['release_lead_on_reopen_s'])} before the reopen")
    print(f"    keyed on longest_closure_s : active {_fmt(o['counterfactual_active_from_s'])} -> "
          f"{_fmt(o['counterfactual_active_until_s'])}, still firing "
          f"{_fmt(o['counterfactual_still_firing_after_reopen_s'])} AFTER the reopen "
          f"(the stuck-alarm bug)")
    print(f"    fix changes the end-to-end clearing time: "
          f"{o['fix_changes_end_to_end_clearing']} "
          f"(counterfactual cleared {_fmt(o['counterfactual_cleared_s'])})")

    print("  closure values around the reopen (why current_closure_s is what releases it):")
    print("       t(s)  longest  current    score  state  override")
    for r in rep["around_reopen"]:
        mark = " *" if r["synthetic_tail"] else ""
        print(f"    {r['timestamp_s']:7.4f}  {r['longest_closure_s']:7.3f}  "
              f"{r['current_closure_s']:7.3f}  {r['drowsy_score']:7.4f}  "
              f"{r['state']:<5}  {str(r['override_active']):<5}{mark}")

    print("  state transitions:")
    for t in rep["transitions"]:
        mark = "  (synthetic tail)" if t["synthetic_tail"] else ""
        print(f"    {t['timestamp_s']:7.4f}s  {t['from_state']} -> {t['to_state']}"
              f"  [{t['evidence']}]{mark}")

    print(f"  VERDICT         : {'PASS' if v['pass'] else 'FAIL'}")
    print(f"    override released on reopen   : {v['override_released_on_reopen']}")
    print(f"    ALERT cleared within the latch: {v['alert_cleared_within_latch']}")
    print(f"    {v['reason']}")
    print(f"  graded_accuracy : False -- {rep['note']}")


def _fmt(v: float | None) -> str:
    return "never" if v is None else f"{v:.3f}s"


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help=f"where to write the report (default: {DEFAULT_OUT.name})")
    ap.add_argument("--tail-s", type=float, default=4.0,
                    help="seconds of synthetic eyes-open frames to append so a clearing "
                         "time is measurable past the end of the 10 s mock clip")
    args = ap.parse_args(argv)

    sg4_cfg = load_config(ROOT / "module_sg4" / "configs" / "default.yaml")
    sg5_cfg = load_config(ROOT / "module_sg5" / "configs" / "default.yaml")

    override_s = float(sg5_cfg.get("closure_override_s", 1.20))

    pairs, n_mock = load_pairs(args.tail_s)
    steps = replay(pairs, n_mock, sg4_cfg, sg5_cfg)
    counterfactual = replay(pairs, n_mock, sg4_cfg, sg5_cfg, key_on_longest=True)

    # Cross-check the recomputed override flag against what SG-5 itself reported, so a
    # drift between this tool's reimplementation and decision.py cannot pass unnoticed.
    for s in steps:
        said = "sustained closure" in s.decision.evidence
        if said != override_was_active(s, override_s):
            raise SystemExit(
                f"frame {s.decision.frame_id}: this tool's override flag disagrees with "
                f"SG-5's own evidence ({s.decision.evidence!r}) -- fix the tool, not the data")

    rep = build_report(steps, counterfactual, n_mock,
                       [e for e, _ in pairs[:n_mock]], sg4_cfg, sg5_cfg, args.tail_s)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
    print_summary(rep)
    print(f"  report          -> {args.out}")

    # Non-zero on failure so this doubles as a regression gate.
    return 0 if rep["verdict"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
