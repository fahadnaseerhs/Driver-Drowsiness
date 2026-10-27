"""Generate the SG-5 mechanism stress track -- a fixture that actually provokes the FSM.

    python module_sg5/fixtures/stress_track.py        # writes stress_track.json

WHY THIS FILE EXISTS
--------------------
``module_sg5/tools/ablation.py`` replays a fixed input through
``DrowsinessDecider`` with one safety mechanism removed at a time, so that "what
does hysteresis buy?" has a number instead of an opinion. Run over
``interfaces/mock/mock_temporal.json`` the study was nearly vacuous: four of the
five mechanisms produced output byte-identical to the full configuration. Not
because they do nothing, but because that fixture never puts them in charge of a
decision. Measured on the mock:

  * ``confidence`` never drops below 0.667 while the gate trips at 0.50, so the
    confidence gate cannot fire;
  * only 12 of 300 frames sit in the WARN band, and nothing hovers on a
    threshold, so hysteresis is never asked to hold a state;
  * the score crosses ``alert_on`` before the sustained-closure override would,
    so the override only re-asserts a decision the score already made;
  * the clip ends mid-alert, so recovery and the latch release are unobserved.

An ablation that reports "unchanged" four times out of five cannot answer the
examiner's obvious question -- *why not just a threshold?* -- because on that
input a plain threshold behaves the same. This file builds the missing input.

HOW IT IS BUILT
---------------
Named segments, one per mechanism, each engineered so that removing exactly one
mechanism changes the outcome. The segment table (``SEGMENTS``) is importable so
the harness can attribute ALERT frames to a genuine drowsy episode or to a false
alarm instead of guessing from a hard-coded onset time.

    awake_baseline       false-alarm denominator; nothing should fire
    boundary_hover       score parked on warn_on, alternating slower than the
                         dwell timer -> hysteresis must hold, warn_off==warn_on
                         must chatter
    single_frame_spikes  one-frame 0.95 spikes -> the dwell timer must swallow
                         them, no_dwell must not
    genuine_episode      a real episode: score past alert_on, 2.0 s closure,
                         reopen, recovery, and a 0.3 s observation gap inside
                         the latch window -> the latch must hold through it
    override_only        2.5 s closure with the score held BELOW alert_on ->
                         only the override can alert here
    low_coverage         confidence 0.30 with a high score -> only the gate
                         stops an alarm built on a handful of observations
    tail_awake           so every configuration's final state is observable

Short ``recover_*`` segments were added between the provocative ones; they are
not in the brief's sketch but are necessary, because ``decision.py`` holds the
current state when the confidence gate trips (``target = self._state`` unless
already OK) and holds ALERT through ``alert_latch_s``. Without a settled OK in
front of ``low_coverage`` the gate would merely freeze a leftover WARN and the
row would measure the previous segment instead of the gate.

HONESTY
-------
This track is synthetic by construction and more adversarial than any real
driver. It is evidence about MECHANISM BEHAVIOUR -- chattering, spurious alerts,
recovery, gap handling -- and about nothing else. Per ``datasets/README.md`` no
graded accuracy figure may come from it, and it would be dishonest to read the
ALERT counts here as detection performance.

Two fields are set by design rather than derived, and both are stated rather
than hidden:

  * ``drowsy_score`` is the fixture's control variable, not the output of SG-4's
    fusion formula. In ``override_only`` it is deliberately held at 0.50 while
    the eyes are shut for 2.5 s. That combination is exactly the lag the
    override exists to cover (the window has just turned over, so PERCLOS has
    not caught up yet), and holding it fixed is the only way to isolate the
    override -- but a live SG-4 would not sit there for four seconds.
  * ``low_coverage`` reports a short, unfilled window (1.2 s, PERCLOS 0.80 from
    roughly a dozen surviving observations, confidence 0.30). That is the thin
    evidence the gate is for; it is not a measurement of anything.

Everything else is derived from one closed-eye interval list over a 3 s sliding
window, the same way ``interfaces/mock/generate_mocks.py`` derives SG-4's
reference output, so PERCLOS, ``longest_closure_s`` and ``current_closure_s``
stay physically consistent with each other.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from interfaces.contracts import TARGET_FPS, TemporalResult, to_dict, validate  # noqa: E402

OUT_PATH = Path(__file__).resolve().parent / "stress_track.json"

FPS = TARGET_FPS
DT = 1.0 / FPS
WINDOW_S = 3.0                      # SG-4's sliding window, same as the mock
WINDOW_FRAMES = int(WINDOW_S * FPS)

CLIP_LENGTH_S = 32.5
N_FRAMES = int(round(CLIP_LENGTH_S * FPS))      # 975 frames

# Eye geometry, only used to synthesise a plausible avg_ear from PERCLOS so the
# field is not a lie. Same values as interfaces/mock/generate_mocks.py.
EAR_OPEN = 0.30
EAR_CLOSED = 0.07

# Blink bounds, so a short closure is reported as a blink and a long one is not
# (keeps blink_rate_per_min honest). Same values as the mock generator.
MIN_BLINK_S = 0.06
MAX_BLINK_S = 0.50

BASELINE_SCORE = 0.05

# boundary_hover. default.yaml has warn_on 0.45 / warn_off 0.35, so 0.43/0.47
# straddles the rising threshold and sits inside the dead band on the way down.
# The half-cycle MUST be longer than min_dwell_s (0.40 s) or the dwell timer
# alone would absorb the alternation and the row would measure dwell, not
# hysteresis -- that is the mistake that made this segment worth designing.
HOVER_HIGH = 0.47
HOVER_LOW = 0.43
HOVER_HALF_S = 0.50

SPIKE_SCORE = 0.95
# One frame each, spaced 0.8 s -- closer together than alert_latch_s (1.50 s),
# so a configuration that latches on a spike merges them into one long alarm
# while one that does not stutters once per spike.
SPIKE_FRAMES = frozenset({342, 366, 390, 414})      # t = 11.40, 12.20, 13.00, 13.80

OVERRIDE_SEGMENT_SCORE = 0.50       # below alert_on (0.70), above warn_on (0.45)

LOW_COVERAGE_SCORE = 0.80
LOW_COVERAGE_CONFIDENCE = 0.30      # below min_confidence (0.50)
LOW_COVERAGE_WINDOW_S = 1.20
LOW_COVERAGE_PERCLOS = 0.80
LOW_COVERAGE_LONGEST_S = 0.20

# The observation gap inside genuine_episode: SG-1 loses the face for 0.3 s
# while the alarm is live. It must sit ENTIRELY inside the latch window
# (alert_since 15.3333 s + alert_latch_s 1.50 s = 16.8333 s) or the full
# configuration drops the alarm part-way through the gap too and the row stops
# measuring the latch -- which is what a first placement at 16.60 s did. Placed
# at the tail of the closure, so observation resumes with the eyes already open:
# current_closure_s -> 0 while longest_closure_s keeps the 2.0 s it saw.
GAP_START_S = 16.50
GAP_END_S = 16.80
GAP_REASON = "no_valid_observations"


@dataclass(frozen=True)
class Segment:
    """One named stretch of the track, and what it is there to decide."""

    name: str
    start_s: float
    end_s: float
    targets: str            # the mechanism this segment puts in charge
    genuine: bool           # True only for a real drowsy episode
    rationale: str

    def contains(self, t: float) -> bool:
        return self.start_s <= t < self.end_s

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "targets": self.targets,
            "genuine_drowsy_episode": self.genuine,
            "rationale": self.rationale,
        }


# The machine-readable segment table. tools/ablation.py imports this to decide
# which ALERT frames are false alarms, so the fixture's ground truth lives in
# one place next to the code that produces it -- a hard-coded onset time in the
# harness would silently stop matching the moment this file is edited.
SEGMENTS: tuple[Segment, ...] = (
    Segment(
        "awake_baseline", 0.00, 4.00,
        "nothing -- false-alarm denominator",
        False,
        "Alert driver, score 0.05, full confidence, two ordinary blinks. Any "
        "ALERT in here is a nuisance alert and nothing else.",
    ),
    Segment(
        "boundary_hover", 4.00, 10.00,
        "hysteresis (warn_off vs warn_on)",
        False,
        "Score alternates 0.47/0.43 in 0.5 s half-cycles -- slower than "
        "min_dwell_s, so the dwell timer cannot absorb it. With the dead band "
        "the state settles into WARN and stays; with warn_off == warn_on it "
        "flips on every half-cycle.",
    ),
    Segment(
        "recover_hover", 10.00, 11.00,
        "nothing -- returns every variant to a settled OK",
        False,
        "Needed because the variants leave boundary_hover in different states; "
        "without it the next segment would measure the carry-over.",
    ),
    Segment(
        "single_frame_spikes", 11.00, 14.00,
        "dwell timer (min_dwell_s)",
        False,
        "Baseline 0.05 with four isolated ONE-frame spikes to 0.95. A dwell "
        "timer swallows them; without it each spike is an alarm on an awake "
        "driver.",
    ),
    Segment(
        "genuine_episode", 14.00, 20.00,
        "alert latch (alert_latch_s), and the score path end to end",
        True,
        "A real episode: score climbs past alert_on, eyes close for 2.3 s of "
        "which SG-4 observes 2.0 s, then the face is lost for 0.3 s (16.50-"
        "16.80 s, valid=False, reason='no_valid_observations') while the alarm "
        "is live -- entirely inside the latch window, so the latch is the only "
        "thing holding the alarm up. Observation resumes with the eyes open: "
        "current_closure_s -> 0 while longest_closure_s keeps 2.0 for the rest "
        "of the window, exactly as SG-4 reports it. The score then decays "
        "through the WARN band to baseline.",
    ),
    Segment(
        "override_only", 20.00, 24.00,
        "sustained-closure override (closure_override_s)",
        True,
        "Eyes shut for 2.5 s while the score is held at 0.50, below alert_on. "
        "The window has just turned over, so PERCLOS has not caught up: the "
        "override is the only mechanism that can alarm here, and without it "
        "nothing does.",
    ),
    Segment(
        "recover_override", 24.00, 25.50,
        "nothing -- drains the latch and returns every variant to OK",
        False,
        "The confidence gate holds the CURRENT state rather than forcing OK, so "
        "low_coverage must start from a settled OK or it would measure the "
        "leftover WARN from override_only instead of the gate.",
    ),
    Segment(
        "low_coverage", 25.50, 29.50,
        "confidence gate (min_confidence)",
        False,
        "Confidence 0.30 on a 1.2 s unfilled window with PERCLOS 0.80 and a "
        "score of 0.80 -- a high score computed from roughly a dozen surviving "
        "observations. Thin evidence, not a real event: with the gate there is "
        "no escalation, without it there is an alarm.",
    ),
    Segment(
        "tail_awake", 29.50, 32.50,
        "nothing -- makes the final state observable",
        False,
        "Back to baseline so a configuration that never releases its alarm is "
        "visible as such instead of being hidden by the clip ending mid-alert.",
    ),
)

# Closed-eye intervals, in seconds. Everything about closure, PERCLOS and
# avg_ear is derived from this one list, so the record set cannot claim a
# PERCLOS that disagrees with its own closure durations.
CLOSED_INTERVALS: tuple[tuple[float, float], ...] = (
    (1.00, 1.12),       # ordinary blink, awake_baseline
    (2.50, 2.62),       # ordinary blink, awake_baseline
    (6.00, 6.12),       # ordinary blink during boundary_hover
    # genuine_episode: a 2.3 s closure of which the last 0.3 s is unobserved
    # (the gap below), so SG-4 reports a 2.0 s closure and then open eyes.
    (14.50, 16.80),
    (20.50, 23.00),     # override_only: SUSTAINED 2.5 s closure
    (30.50, 30.62),     # ordinary blink, tail_awake
)


def segment_at(t: float) -> Segment:
    """The segment covering ``t``. The table is contiguous, so this cannot miss."""
    for seg in SEGMENTS:
        if seg.contains(t):
            return seg
    return SEGMENTS[-1]


def genuine_spans() -> list[tuple[float, float]]:
    """The spans a correct system is *supposed* to alarm on, from the table."""
    return [(s.start_s, s.end_s) for s in SEGMENTS if s.genuine]


def _lerp(t: float, t0: float, v0: float, t1: float, v1: float) -> float:
    """Clamped linear interpolation -- keeps the score ramps readable."""
    if t1 <= t0:
        return v1
    f = (t - t0) / (t1 - t0)
    return v0 + (v1 - v0) * max(0.0, min(1.0, f))


def score_at(t: float, frame_id: int) -> float:
    """The designed ``drowsy_score`` at ``t``. The fixture's control variable.

    Piecewise and deliberate: each branch belongs to one segment, and the
    numbers are chosen against default.yaml's thresholds (warn_on 0.45,
    alert_on 0.70, warn_off 0.35, alert_off 0.55) so that the mechanism under
    test is the thing that decides the outcome.
    """
    if t < 4.00:                                        # awake_baseline
        return BASELINE_SCORE
    if t < 10.00:                                       # boundary_hover
        half = int((t - 4.00) / HOVER_HALF_S)
        return HOVER_HIGH if half % 2 == 0 else HOVER_LOW
    if t < 11.00:                                       # recover_hover
        return BASELINE_SCORE
    if t < 14.00:                                       # single_frame_spikes
        return SPIKE_SCORE if frame_id in SPIKE_FRAMES else BASELINE_SCORE
    if t < 20.00:                                       # genuine_episode
        # Rise crosses alert_on (0.70) at ~14.92 s, which is BEFORE the override
        # could fire at 15.70 s -- on a genuine episode the score should be the
        # thing that alarms, so that no_override is not silently credited here.
        if t < 14.50:
            return _lerp(t, 14.00, 0.05, 14.50, 0.30)
        if t < 15.00:
            return _lerp(t, 14.50, 0.30, 15.00, 0.78)
        if t < 17.20:
            # Plateau held past the observation gap on purpose: the score is
            # still above alert_on when observation resumes, so a variant
            # without the latch RE-fires rather than quietly giving up, and the
            # stutter shows as an extra ALERT episode.
            return _lerp(t, 15.00, 0.78, 17.20, 0.88)
        if t < 18.30:
            # Decay through the WARN band rather than straight to OK, so the
            # release path (ALERT -> WARN -> OK) is exercised too.
            return _lerp(t, 17.20, 0.88, 18.30, 0.30)
        if t < 19.30:
            return _lerp(t, 18.30, 0.30, 19.30, 0.05)
        return BASELINE_SCORE
    if t < 24.00:                                       # override_only
        return OVERRIDE_SEGMENT_SCORE
    if t < 25.50:                                       # recover_override
        return BASELINE_SCORE
    if t < 29.50:                                       # low_coverage
        return LOW_COVERAGE_SCORE
    return BASELINE_SCORE                               # tail_awake


def _is_closed(t: float) -> bool:
    return any(a <= t < b for a, b in CLOSED_INTERVALS)


def _is_gap(t: float) -> bool:
    return GAP_START_S <= t < GAP_END_S


def _in_low_coverage(t: float) -> bool:
    return segment_at(t).name == "low_coverage"


def build_sequence() -> list[TemporalResult]:
    """The whole track. Deterministic: no RNG, no seeds, no wall-clock."""
    # Per-frame closure run length, accumulated exactly as SG-2 does, so
    # longest_closure_s over a window is a max of real run lengths.
    closed_flags: list[bool] = []
    closure_runs: list[float] = []
    blink_ends: list[bool] = []
    run = 0.0
    prev_closed = False
    for i in range(N_FRAMES):
        t = i * DT
        closed = _is_closed(t) and not _is_gap(t)
        # A blink is reported on the frame a SHORT closure ends; a 2 s closure
        # is a microsleep and must not inflate blink_rate_per_min.
        blink_ends.append(prev_closed and not closed and MIN_BLINK_S <= run <= MAX_BLINK_S)
        run = run + DT if closed else 0.0
        closed_flags.append(closed)
        closure_runs.append(round(run, 4))
        prev_closed = closed

    out: list[TemporalResult] = []
    for i in range(N_FRAMES):
        t = i * DT
        if _is_gap(t):
            # Empty behaviour per the contract: the payload still comes back,
            # with valid=False and a reason. Never None, never an exception.
            out.append(TemporalResult.empty(i, round(t, 4), reason=GAP_REASON))
            continue

        lo = max(0, i - WINDOW_FRAMES + 1)
        idx = [j for j in range(lo, i + 1) if not _is_gap(j * DT)]
        span = len(idx) * DT

        closed_count = sum(1 for j in idx if closed_flags[j])
        perclos = closed_count / len(idx)
        longest = max((closure_runs[j] for j in idx), default=0.0)
        current = closure_runs[i] if closed_flags[i] else 0.0
        blinks = sum(1 for j in idx if blink_ends[j])
        window_filled = len(idx) >= WINDOW_FRAMES
        confidence = 1.0

        if _in_low_coverage(t):
            # Overridden, not derived: see the module docstring. A thin,
            # unfilled window whose few surviving observations were mostly
            # closed -- which is what a high PERCLOS at low coverage means.
            perclos = LOW_COVERAGE_PERCLOS
            longest = LOW_COVERAGE_LONGEST_S
            current = 0.0
            span = LOW_COVERAGE_WINDOW_S
            window_filled = False
            confidence = LOW_COVERAGE_CONFIDENCE
            blinks = 1

        out.append(TemporalResult(
            frame_id=i,
            timestamp=round(t, 4),
            valid=True,
            reason="",
            window_s=round(span, 4),
            window_filled=window_filled,
            perclos=round(perclos, 4),
            blink_rate_per_min=round(blinks * 60.0 / max(span, 1e-6), 2),
            yawn_rate_per_min=0.0,      # no yawns: SG-3's cues are not under test here
            longest_closure_s=round(longest, 4),
            current_closure_s=round(current, 4),
            # Plausible rather than invented: the window mean of an open-eye and
            # a closed-eye EAR, weighted by PERCLOS.
            avg_ear=round(EAR_OPEN * (1.0 - perclos) + EAR_CLOSED * perclos, 4),
            drowsy_score=round(score_at(t, i), 4),
            confidence=confidence,
        ))
    return out


def main() -> int:
    records = build_sequence()

    # Fail loudly: a fixture that violates the frozen V1 contract is worse than
    # no fixture, because every number downstream of it would be unexplainable.
    violations: list[str] = []
    for rec in records:
        errs = validate(rec)
        if errs:
            violations.append(f"frame {rec.frame_id} (t={rec.timestamp:g}): " + "; ".join(errs))
    assert not violations, (
        f"{len(violations)} contract violation(s) in the stress track:\n  "
        + "\n  ".join(violations[:10])
    )

    payload = [to_dict(r) for r in records]
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")

    print(f"SG-5 mechanism stress track -- {len(records)} frames @ {FPS} fps "
          f"({records[-1].timestamp:g} s), contract-clean")
    print(f"{'segment':<21} {'span (s)':<14} {'genuine':<8} targets")
    for seg in SEGMENTS:
        span = f"{seg.start_s:g}-{seg.end_s:g}"
        print(f"  {seg.name:<19} {span:<14} {str(seg.genuine):<8} {seg.targets}")
    n_invalid = sum(1 for r in records if not r.valid)
    print(f"  invalid frames (observation gap): {n_invalid} "
          f"({GAP_START_S:g}-{GAP_END_S:g} s, reason={GAP_REASON!r})")
    print(f"  wrote : {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
