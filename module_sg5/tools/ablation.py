"""SG-5 Phase 1 ablation study -- what each nuisance-alert brake actually buys.

    python module_sg5/tools/ablation.py

ALGORITHM_PLAN.md section 5, task 1.3 calls this "the single most persuasive
artefact this module can produce", and the reason is narrow: decision.py spends
five mechanisms (hysteresis, dwell, latch, closure override, confidence gate) on
a job a single `if score > 0.7` would appear to do. An examiner is right to ask
why. "Removing the latch turned 2 state transitions into 31" answers that with a
number; README section 4's prose does not.

So this script replays fixed inputs through DrowsinessDecider under the full
configuration and under one-mechanism-removed variants of it, plus the
all-brakes-off rule-based baseline from configs/experiment_a.yaml, and reports
the behaviour that changes: chattering (state transitions, ALERT episodes),
latency (lag from closure onset to alarm), recovery (whether and when the alarm
cleared), and nuisance alerts (ALERT frames outside a genuine drowsy episode).

TWO FIXTURES, AND WHY
---------------------
1. ``interfaces/mock/mock_temporal.json`` -- the shared reference input every
   module develops against. It is the honest first thing to try, and the result
   was nearly vacuous: four of five mechanisms produced byte-identical output,
   because that clip never puts them in charge of a decision (confidence never
   falls below 0.667 against a 0.50 gate; nothing hovers on a threshold; the
   score crosses alert_on before the override could fire). An ablation that
   reports "unchanged" four times out of five cannot answer "why not just a
   threshold?", because on that input a plain threshold behaves the same.

2. ``module_sg5/fixtures/stress_track.json`` -- built by
   ``module_sg5/fixtures/stress_track.py`` precisely to close that gap: named
   segments, one per mechanism, each engineered so that removing exactly that
   mechanism changes the outcome. Its segment table says which spans are
   genuine drowsy episodes, so ALERT frames can be attributed to a real event or
   counted as nuisance alerts instead of being judged against a hard-coded
   onset time.

Both are reported. Keeping the mock in the study is the point: it is the
evidence that the stress track was necessary.

WHAT THIS IS NOT
----------------
Both inputs are synthetic -- geometrically perfect, no camera noise, no real
driver. The stress track is additionally adversarial by construction: it is
engineered to provoke, which makes it *less* like a real driver, not more. Per
datasets/README.md no graded accuracy figure may come from either, and the JSON
report carries ``graded_accuracy: false`` for exactly that reason. These studies
are evidence about MECHANISM BEHAVIOUR -- chattering, spurious alerts, recovery,
observation-gap handling -- which a deterministic FSM on a deterministic input
can honestly demonstrate. They are not evidence about detection accuracy, which
needs the clips Phase 2 has to record.

The fixture's job is to put each mechanism in a position to decide something,
NOT to make the FSM look good. Where a mechanism still changes nothing, or where
removing one *improves* a metric, that is reported next to its cost rather than
tuned away.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from common.config import load_config  # noqa: E402
from interfaces.contracts import DrowsinessState, TemporalResult, from_dict  # noqa: E402
from module_sg5.fixtures import stress_track  # noqa: E402
from module_sg5.src.decision import DrowsinessDecider  # noqa: E402

MODULE = Path(__file__).resolve().parents[1]
MOCK_INPUT = ROOT / "interfaces" / "mock" / "mock_temporal.json"
STRESS_INPUT = MODULE / "fixtures" / "stress_track.json"
DEFAULT_CONFIG = MODULE / "configs" / "default.yaml"
EXPERIMENT_A = MODULE / "configs" / "experiment_a.yaml"
OUT_JSON = MODULE / "results" / "ablation.json"
OUT_MD = MODULE / "results" / "ablation.md"

# The sustained closure in the mock begins here. Alert lag is measured from it,
# and any ALERT before it is a false alarm in the awake opening. Hard-coded
# deliberately: it is a property of the fixture, and reading it back out of the
# fixture would let a regenerated mock silently redefine "on time".
MOCK_CLOSURE_ONSET_S = 5.20

# A high override threshold no clip here can reach, which is how the override is
# removed without touching decision.py.
OVERRIDE_DISABLED_S = 999.0

SYNTHETIC_WARNING = (
    "Synthetic input. These numbers describe MECHANISM BEHAVIOUR (chattering, "
    "spurious alerts, recovery, observation-gap handling) only. No graded "
    "accuracy figure may come from them -- see datasets/README.md."
)


@dataclass(frozen=True)
class Fixture:
    """One input clip plus the ground truth needed to score behaviour on it.

    ``genuine_spans`` is what makes the false-alarm count meaningful: an ALERT
    frame inside one of these spans is the system doing its job, and an ALERT
    frame outside them is a nuisance alert. The mock has no segment table, so
    its span is stated here; the stress track's comes from its own generator so
    the two cannot drift apart.
    """

    name: str
    path: Path
    closure_onset_s: float
    genuine_spans: tuple[tuple[float, float], ...]
    headline: str
    caveat: str
    segments: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def is_genuine(self, t: float) -> bool:
        return any(a <= t < b for a, b in self.genuine_spans)

    def segment_at(self, t: float) -> str | None:
        for seg in self.segments:
            if seg["start_s"] <= t < seg["end_s"]:
                return str(seg["name"])
        return None


def _fixtures() -> tuple[Fixture, ...]:
    return (
        Fixture(
            name="mock_temporal",
            path=MOCK_INPUT,
            closure_onset_s=MOCK_CLOSURE_ONSET_S,
            # The shared mock has no segment table. Its one genuine episode is
            # the scripted sustained closure from 5.20 s to the end of the clip
            # (the microsleeps at 7.25-7.98 s are part of the same episode), so
            # "outside a genuine episode" reduces to "before the onset" -- which
            # is the same false-alarm definition this study has always used.
            genuine_spans=((MOCK_CLOSURE_ONSET_S, float("inf")),),
            headline="The shared reference input every module develops against.",
            caveat=(
                "The score here rises monotonically and cleanly: no jitter, no "
                "boundary hovering, confidence never below 0.667 against a 0.50 "
                "gate, and the clip ends mid-alert. Most mechanisms are never "
                "put in charge of a decision, so most rows read `unchanged`. "
                "That is a statement about this fixture, not a verdict on the "
                "mechanisms -- and it is why the stress track exists."
            ),
        ),
        Fixture(
            name="stress_track",
            path=STRESS_INPUT,
            # The actual eye-closure onset inside genuine_episode, which is what
            # alert lag should be measured from -- not the segment boundary.
            closure_onset_s=14.50,
            genuine_spans=tuple(stress_track.genuine_spans()),
            headline=(
                "Built by module_sg5/fixtures/stress_track.py to put each "
                "mechanism in a situation where it decides something."
            ),
            caveat=(
                "Engineered to provoke, which makes it LESS like a real driver, "
                "not more. Every number here is about mechanism behaviour. The "
                "two fields set by design rather than derived are stated in the "
                "generator's docstring: `drowsy_score` is the fixture's control "
                "variable, and `low_coverage` reports a deliberately thin, "
                "unfilled window."
            ),
            segments=tuple(s.to_dict() for s in stress_track.SEGMENTS),
        ),
    )


def _variants(default: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The configurations to compare, each one mechanism away from ``default``.

    Built in code rather than as seven more YAML files: a variant here is
    defined by its single difference from default.yaml, and seven near-identical
    configs on disk would hide that difference and drift out of sync with it.
    experiment_a.yaml is the exception -- it is a committed artefact in its own
    right (the documented backup), so it is loaded from disk.
    """
    return {
        "full": dict(default),
        "no_hysteresis": {**default, "warn_off": default["warn_on"],
                          "alert_off": default["alert_on"]},
        "no_dwell": {**default, "min_dwell_s": 0.0},
        "no_latch": {**default, "alert_latch_s": 0.0},
        "no_override": {**default, "closure_override_s": OVERRIDE_DISABLED_S},
        "no_confidence_gate": {**default, "min_confidence": 0.0},
        "rules_only": load_config(EXPERIMENT_A),
    }


def _percentile(sorted_values: list[float], fraction: float) -> float:
    """Nearest-rank percentile, matching common.timing.Stopwatch.summary()."""
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, int(fraction * len(sorted_values)))
    return sorted_values[idx]


def _measure(name: str, config: dict[str, Any], inputs: list[TemporalResult],
             fixture: Fixture) -> dict[str, Any]:
    """Replay the whole clip under one configuration and score its behaviour."""
    decider = DrowsinessDecider(config)
    decider.reset()                      # state must not leak between configs

    latencies_ms: list[float] = []
    frames_in_state: dict[str, int] = {s.value: 0 for s in DrowsinessState}
    alert_by_segment: dict[str, int] = {str(s["name"]): 0 for s in fixture.segments}
    transitions = 0
    alert_episodes = 0
    first_alert_s: float | None = None
    first_episode_alert_s: float | None = None
    last_alert_cleared_s: float | None = None
    false_alarm_frames = 0
    previous = DrowsinessState.OK

    for temporal in inputs:
        t0 = time.perf_counter()
        result = decider.process(temporal)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        frames_in_state[result.state.value] += 1
        if result.state is not previous:
            transitions += 1
            if result.state is DrowsinessState.ALERT:
                alert_episodes += 1
                if first_alert_s is None:
                    first_alert_s = result.timestamp
            elif previous is DrowsinessState.ALERT:
                # Overwritten by each later clear, so it ends up holding the
                # LAST one. Stays None if the clip ends mid-alert.
                last_alert_cleared_s = result.timestamp
        if result.state is DrowsinessState.ALERT:
            if not fixture.is_genuine(result.timestamp):
                false_alarm_frames += 1
            elif first_episode_alert_s is None:
                first_episode_alert_s = result.timestamp
            seg = fixture.segment_at(result.timestamp)
            if seg is not None:
                alert_by_segment[seg] += 1
        previous = result.state

    ordered = sorted(latencies_ms)
    out: dict[str, Any] = {
        "config": config,
        "transitions": transitions,
        "alert_episodes": alert_episodes,
        "first_alert_s": round(first_alert_s, 4) if first_alert_s is not None else None,
        # The first ALERT frame that lands inside a genuine episode, and the lag
        # from the closure onset to it. Measuring lag from first_alert_s alone
        # produced a NEGATIVE "lag" for the variants that alarm on a one-frame
        # spike 3 s before the episode starts -- which reads like a latency win
        # and is in fact a nuisance alert. These two keys separate the two.
        "first_episode_alert_s": (round(first_episode_alert_s, 4)
                                  if first_episode_alert_s is not None else None),
        "episode_lag_s": (round(first_episode_alert_s - fixture.closure_onset_s, 4)
                          if first_episode_alert_s is not None else None),
        "alert_lag_s": (round(first_alert_s - fixture.closure_onset_s, 4)
                        if first_alert_s is not None else None),
        "last_alert_cleared_s": (round(last_alert_cleared_s, 4)
                                 if last_alert_cleared_s is not None else None),
        "frames_in_state": frames_in_state,
        "false_alarm_frames": false_alarm_frames,
        "latency_mean_ms": round(sum(ordered) / len(ordered), 4) if ordered else 0.0,
        "latency_p95_ms": round(_percentile(ordered, 0.95), 4),
        # Cross-check against the decider's own counter: they should agree, and a
        # disagreement means one of the two definitions of "episode" is wrong.
        "decider_alert_count": decider.alert_count,
        "name": name,
    }
    if fixture.segments:
        out["alert_frames_by_segment"] = alert_by_segment
    return out


# The metrics that count as "behaviour". Latency is excluded on purpose: it is
# wall-clock noise, it differs between two identical runs, and treating it as a
# behavioural change would make every mechanism look like it did something.
BEHAVIOURAL_KEYS = ("transitions", "alert_episodes", "first_alert_s", "alert_lag_s",
                    "first_episode_alert_s", "episode_lag_s", "last_alert_cleared_s",
                    "frames_in_state", "false_alarm_frames", "alert_frames_by_segment")


def _changed_keys(run: dict[str, Any], full: dict[str, Any]) -> list[str]:
    """Which behavioural metrics this variant moved relative to ``full``."""
    return [k for k in BEHAVIOURAL_KEYS if k in full and run.get(k) != full.get(k)]


def _fmt(value: Any) -> str:
    return "never" if value is None else (f"{value:g}" if isinstance(value, float) else str(value))


def _delta(mechanism: dict[str, Any], full: dict[str, Any], key: str, unit: str = "") -> str:
    """"2 -> 31" style change, or "unchanged", for the per-mechanism prose.

    The unit is appended only to a real change, because "unchanged s" is noise.
    """
    a, b = full[key], mechanism[key]
    return "unchanged" if a == b else f"{_fmt(a)} -> {_fmt(b)}{unit}"


def _segment_delta(run: dict[str, Any], full: dict[str, Any]) -> str:
    """Per-segment ALERT-frame changes, which is where the attribution lives.

    The aggregate counts say a variant behaved differently; this says WHERE, and
    "`override_only` 52 -> 0" is the sentence that actually answers the examiner.
    """
    a = full.get("alert_frames_by_segment")
    b = run.get("alert_frames_by_segment")
    if not a or not b:
        return ""
    bits = [f"`{k}` {a[k]} -> {b[k]}" for k in a if a[k] != b[k]]
    return "; ".join(bits) if bits else "no segment changed its ALERT frame count"


# Why each variant is in the study, and what a difference in it would mean. Kept
# next to the prose generator so the write-up cannot silently lose a mechanism.
_NOTES: dict[str, tuple[str, str]] = {
    "no_hysteresis": (
        "Hysteresis (asymmetric thresholds)",
        "A score hovering on a threshold should not flicker the state. With the "
        "dead band removed, any chattering shows up as extra transitions.",
    ),
    "no_dwell": (
        "Dwell timer (min_dwell_s)",
        "A candidate state must persist before it is adopted, so a single noisy "
        "frame cannot raise an alarm. Removing it should let spikes through.",
    ),
    "no_latch": (
        "Alert latch (alert_latch_s)",
        "Once ALERT fires it holds, so the alarm does not stutter off the moment "
        "the eyes flick open -- and survives an observation gap.",
    ),
    "no_override": (
        "Sustained-closure override (closure_override_s)",
        "Eyes shut past the threshold escalate immediately, bypassing score, "
        "dwell and hysteresis. Removing it leaves the alarm to the score alone.",
    ),
    "no_confidence_gate": (
        "Confidence gate (min_confidence)",
        "Below the upstream coverage floor the module refuses to escalate, so an "
        "alarm is never raised from a PERCLOS computed out of a few frames.",
    ),
    "rules_only": (
        "All brakes off (configs/experiment_a.yaml)",
        "The documented backup: plain thresholds, no hysteresis, no dwell, no "
        "latch. The comparison the complexity of the FSM has to justify.",
    ),
}


def _render_fixture_section(block: dict[str, Any]) -> list[str]:
    """One fixture's section: context, comparison table, per-mechanism verdicts."""
    runs: dict[str, dict[str, Any]] = block["configurations"]
    full = runs["full"]
    lines: list[str] = [
        f"## Fixture: `{block['input']}`",
        "",
        f"{block['headline']}",
        "",
        f"- {block['frames']} frames, {block['clip_length_s']:g} s"
        f" ({block['invalid_frames']} frames with `valid=False`)",
        f"- Closure onset **t = {block['closure_onset_s']:g} s**; the episode lag"
        " is measured from there to the first ALERT frame *inside* a genuine"
        " episode. `First ALERT` is the first ALERT frame anywhere, so a"
        " configuration whose first alarm is spurious shows the two apart. A"
        " NEGATIVE episode lag means the alarm was already ringing when the"
        " episode began -- carried in from an earlier spurious alert, not"
        " earned.",
        "- Genuine drowsy episodes (s): "
        + ", ".join(f"{a:g}-{b:g}" for a, b in block["genuine_spans_s"])
        + ". An ALERT frame outside them is counted as a false alarm.",
        f"- `graded_accuracy: false`. {block['caveat']}",
        "",
    ]

    if block["segments"]:
        lines += [
            "### Segments",
            "",
            "| Segment | Span (s) | Targets | Genuine episode |",
            "|---|---|---|---|",
        ]
        for seg in block["segments"]:
            lines.append(
                f"| `{seg['name']}` | {seg['start_s']:g}-{seg['end_s']:g} "
                f"| {seg['targets']} | {'yes' if seg['genuine_drowsy_episode'] else 'no'} |"
            )
        lines.append("")

    lines += [
        "### Comparison",
        "",
        "| Configuration | Transitions | ALERT episodes | First ALERT (s) "
        "| First in-episode ALERT (s) | Episode lag (s) "
        "| Last clear (s) | OK | WARN | ALERT | False alarms | Mean ms | p95 ms |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, run in runs.items():
        states = run["frames_in_state"]
        lines.append(
            f"| `{name}` | {run['transitions']} | {run['alert_episodes']} "
            f"| {_fmt(run['first_alert_s'])} "
            f"| {_fmt(run['first_episode_alert_s'])} "
            f"| {_fmt(run['episode_lag_s'])} "
            f"| {_fmt(run['last_alert_cleared_s'])} | {states['OK']} "
            f"| {states['WARN']} | {states['ALERT']} "
            f"| {run['false_alarm_frames']} "
            f"| {run['latency_mean_ms']:.4f} | {run['latency_p95_ms']:.4f} |"
        )
    lines.append("")

    if block["segments"]:
        names = [str(s["name"]) for s in block["segments"]]
        lines += [
            "### ALERT frames per segment",
            "",
            "Where each configuration raised its alarm. This is the attribution"
            " the aggregate table cannot give.",
            "",
            "| Configuration | " + " | ".join(f"`{n}`" for n in names) + " |",
            "|---" * (len(names) + 1) + "|",
        ]
        for name, run in runs.items():
            per = run["alert_frames_by_segment"]
            lines.append(f"| `{name}` | " + " | ".join(str(per[n]) for n in names) + " |")
        lines.append("")

    lines += ["### What removing each mechanism did", ""]
    for name, (title, purpose) in _NOTES.items():
        run = runs[name]
        changed = block["changed_metrics"][name]
        verdict = ("**changed nothing measurable on this fixture.**" if not changed
                   else f"changed: {', '.join(f'`{k}`' for k in changed)}.")
        lines += [
            f"#### {title}",
            "",
            f"{purpose}",
            "",
            f"Versus `full` it {verdict}",
            "",
            f"State transitions {_delta(run, full, 'transitions')}; "
            f"ALERT episodes {_delta(run, full, 'alert_episodes')}; "
            f"first ALERT {_delta(run, full, 'first_alert_s', ' s')}; "
            f"first in-episode ALERT {_delta(run, full, 'first_episode_alert_s', ' s')}; "
            f"episode lag {_delta(run, full, 'episode_lag_s', ' s')}; "
            f"last clear {_delta(run, full, 'last_alert_cleared_s', ' s')}; "
            f"ALERT frames {full['frames_in_state']['ALERT']} -> "
            f"{run['frames_in_state']['ALERT']}; "
            f"false alarms {_delta(run, full, 'false_alarm_frames')}.",
            "",
        ]
        seg_line = _segment_delta(run, full)
        if seg_line:
            lines += [f"By segment: {seg_line}.", ""]

    # A variant whose every behavioural metric equals `full` did not change the
    # outcome, which means this fixture never actually put that mechanism in
    # charge of a decision. That is a gap in the test input, and hiding it would
    # make the study look stronger than it is -- so it is reported explicitly.
    inert = block["inert_mechanisms"]
    lines += ["### Mechanisms this fixture does not exercise", ""]
    if inert:
        lines += [
            "The variants " + ", ".join(f"`{n}`" for n in inert) + " changed"
            " nothing measurable: identical transitions, episodes, timings,"
            " state occupancy and false-alarm counts. So on this input those"
            " mechanisms never decided anything, and this fixture is **not**"
            " evidence that they work -- only that they are inert here.",
            "",
        ]
    else:
        lines += [
            "None. Every mechanism changed at least one behavioural metric on"
            " this fixture, which is what it was built for.",
            "",
        ]
    return lines


def _render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = [
        "# SG-5 Phase 1 ablation -- what each safety mechanism buys",
        "",
        "> ## SYNTHETIC INPUT -- NOT AN ACCURACY RESULT",
        f"> {SYNTHETIC_WARNING}",
        ">",
        "> This study measures what *changes* when one mechanism is removed from"
        " an otherwise identical run over identical input. That difference is"
        " real evidence about the mechanism. The absolute values are properties"
        " of a synthetic fixture, not of a driver.",
        ">",
        "> **Both** fixtures below are synthetic, and the stress track is"
        " synthetic *by construction* -- it is engineered to provoke each"
        " mechanism, which makes it less like a real driver, not more. It"
        " demonstrates mechanism behaviour (chattering, spurious alerts,"
        " recovery, observation-gap handling). It demonstrates nothing about"
        " detection accuracy.",
        "",
        f"- Baseline config: `{report['baseline_config']}`",
        f"- `graded_accuracy: {str(report['graded_accuracy']).lower()}`",
        "- Fixtures: "
        + ", ".join(f"`{b['input']}`" for b in report["fixtures"].values()),
        "",
        "Two fixtures, because one was not enough. The shared mock is the honest"
        " first thing to try and it left four of five mechanisms inert -- which"
        " is itself the finding that motivated the second fixture. The mock"
        " section is kept so that motivation stays visible rather than being"
        " quietly replaced by a better-looking input.",
        "",
    ]
    for block in report["fixtures"].values():
        lines += _render_fixture_section(block)

    lines += ["## Reading this honestly", ""]

    # Cross-fixture verdict, computed rather than asserted: a mechanism that is
    # inert on BOTH fixtures has no evidence behind it in this study at all, and
    # that belongs in the limitations in plain words.
    inert_everywhere = report["inert_on_every_fixture"]
    if inert_everywhere:
        lines += [
            "**Inert on every fixture: "
            + ", ".join(f"`{n}`" for n in inert_everywhere) + ".** A fair"
            " attempt was made to provoke each of these and it did not change"
            " any behavioural metric. That is a real finding and it is a"
            " limitation, not a success: for those mechanisms the unit tests in"
            " `module_sg5/tests/` remain the only evidence, and the ablation"
            " offers no argument for keeping them.",
            "",
        ]
    else:
        lines += [
            "Every mechanism changes at least one behavioural metric on at least"
            " one fixture, so none of them is dead code on this evidence. That is"
            " a claim about behaviour on engineered input, and it is the strongest"
            " claim this study can make.",
            "",
        ]

    lines += [
        "A mechanism's row reading `unchanged` on the mock and changing on the"
        " stress track means the mock never asked it to decide anything -- read"
        " the stress-track row. A row that changes on both is the stronger"
        " result.",
        "",
        "Removing a brake is not uniformly bad, and the tables are not arranged"
        " to hide that. Two mechanisms cost something measurable:",
        "",
        "- **The dwell timer costs latency.** On the mock, `no_dwell` alarms at"
        " 5.8333 s instead of 6.2667 s -- 0.4333 s sooner, a real win on a real"
        " episode. Its price is on the stress track: 75 ALERT frames across"
        " `single_frame_spikes`, four one-frame score spikes turned into alarms"
        " on an awake driver (and, because the latch then holds them, one of"
        " those alarms is still ringing when the genuine episode starts, which"
        " is why its episode lag reads -0.5 s rather than as a head start).",
        "- **Hysteresis costs recovery time.** `no_hysteresis` releases the"
        " alarm earlier in `genuine_episode` -- 80 ALERT frames against 100 --"
        " because with `alert_off == alert_on` the alert drops as soon as the"
        " score falls under 0.70 instead of waiting for 0.55. Faster recovery is"
        " a real benefit. It is bought with 19 state transitions instead of 8,"
        " all of them chatter on `boundary_hover`.",
        "",
        "Whether 0.4 s of latency is worth four nuisance alarms, or faster"
        " recovery is worth a flickering state, is a judgement about risk R6"
        " (false alerts make the driver switch the system off). This table"
        " supplies the numbers for that argument; it does not settle it.",
        "",
        "What is still owed, and cannot be produced from either file: false alarms"
        " per hour on footage of an awake driver (the number this module lives or"
        " dies by), drowsy-episode recall, and alert latency on a real onset."
        " Those need the clips of ALGORITHM_PLAN.md Phase 2.",
        "",
        "Regenerate: `python module_sg5/fixtures/stress_track.py` then"
        f" `python module_sg5/tools/ablation.py` (writes `{OUT_JSON.name}` and"
        f" `{OUT_MD.name}`).",
        "",
    ]
    return "\n".join(lines)


def _run_fixture(fixture: Fixture, default: dict[str, Any]) -> dict[str, Any]:
    """Load one fixture and measure every variant over it."""
    # Same load path as common.module_runner: raw JSON sequence -> from_dict.
    raw = json.loads(fixture.path.read_text(encoding="utf-8"))
    inputs: list[TemporalResult] = [from_dict(x) for x in raw]

    runs = {name: _measure(name, cfg, inputs, fixture)
            for name, cfg in _variants(default).items()}
    full = runs["full"]
    changed = {name: _changed_keys(runs[name], full) for name in _NOTES}

    clip_len = inputs[-1].timestamp if inputs else 0.0
    return {
        "input": fixture.path.relative_to(ROOT).as_posix(),
        "input_is_synthetic": True,
        "headline": fixture.headline,
        "caveat": fixture.caveat,
        "frames": len(inputs),
        "invalid_frames": sum(1 for x in inputs if not x.valid),
        "clip_length_s": round(clip_len, 4),
        "closure_onset_s": fixture.closure_onset_s,
        # inf does not survive JSON, so the open-ended mock span is clipped to
        # the clip length for the report.
        "genuine_spans_s": [[a, min(b, clip_len)] for a, b in fixture.genuine_spans],
        "segments": list(fixture.segments),
        "changed_metrics": changed,
        "inert_mechanisms": [n for n, keys in changed.items() if not keys],
        "configurations": runs,
    }


def main() -> int:
    missing = [f for f in _fixtures() if not f.path.exists()]
    if missing:
        for fixture in missing:
            hint = ("python interfaces/mock/generate_mocks.py"
                    if fixture.name == "mock_temporal"
                    else "python module_sg5/fixtures/stress_track.py")
            print(f"input not found: {fixture.path}\nrun: {hint}")
        return 2

    default = load_config(DEFAULT_CONFIG)
    blocks = {f.name: _run_fixture(f, default) for f in _fixtures()}

    inert_everywhere = [n for n in _NOTES
                        if all(n in b["inert_mechanisms"] for b in blocks.values())]

    report: dict[str, Any] = {
        # First keys in the file, so the caveat is visible before any number.
        "graded_accuracy": False,
        "warning": SYNTHETIC_WARNING,
        "study": "SG-5 Phase 1 ablation (ALGORITHM_PLAN.md section 5, task 1.3)",
        "baseline_config": DEFAULT_CONFIG.relative_to(ROOT).as_posix(),
        "inert_on_every_fixture": inert_everywhere,
        "fixtures": blocks,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    OUT_MD.write_text(_render_markdown(report), encoding="utf-8")

    print("SG-5 Phase 1 ablation -- SYNTHETIC INPUT, graded_accuracy=false")
    for block in blocks.values():
        print(f"\n  fixture: {block['input']}  ({block['frames']} frames, "
              f"{block['clip_length_s']:g} s)")
        for name, run in block["configurations"].items():
            print(f"    {name:<20} transitions={run['transitions']:<3} "
                  f"episodes={run['alert_episodes']:<3} "
                  f"first_alert={_fmt(run['first_alert_s']):<8} "
                  f"in_episode={_fmt(run['first_episode_alert_s']):<8} "
                  f"cleared={_fmt(run['last_alert_cleared_s']):<8} "
                  f"alert_frames={run['frames_in_state']['ALERT']:<4} "
                  f"false_alarms={run['false_alarm_frames']}")
        inert = block["inert_mechanisms"]
        print(f"    inert here: {', '.join(inert) if inert else 'none'}")
    print(f"\n  inert on EVERY fixture: "
          f"{', '.join(inert_everywhere) if inert_everywhere else 'none'}")
    print(f"  wrote  : {OUT_JSON}")
    print(f"  wrote  : {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
