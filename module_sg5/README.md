# SG-5 — Drowsiness Decision & Alert Logic

**Owners:** NUST 472195, 403897, 459305 (three members) — *confirm names, see
`documentation/team.md`*
**Status:** 🟡 **AMBER** — baseline works, but `WARN` is never reached on the mock run,
so the intermediate state is effectively untested. See §7.

## 1. Purpose

Turn a continuous drowsiness score into the system's one safety-relevant output:
`OK` / `WARN` / `ALERT`, plus the alert itself.

The guide separates this from cue detection so the final decision can be evaluated
independently: *"separates cue detection from the final safety decision and permits
system-level evaluation."*

**This module owns risk R6** — *"false alerts cause the driver to disable the system"*,
mitigated by *"hysteresis plus a sustained-closure duration gate"*. Both are implemented.

> A system that cries wolf gets switched off, and a switched-off system detects
> nothing. **Not alerting is half this module's job**, and the harder half.

## 2. Dependencies

Pure Python and the standard library. No numpy, no model.

An SVM/MLP comparison (Labs 5–6) would change this.

## 3. Input / output interface

```
TemporalResult  ->  DecisionResult
```

**In** — `TemporalResult` from SG-4. Reads `drowsy_score`, `longest_closure_s`,
`confidence`, and the supporting fields for the evidence string.

**Out** — `interfaces.contracts.DecisionResult`:

| Field | Units | Meaning |
|---|---|---|
| `state` | enum | `OK` / `WARN` / `ALERT` |
| `alert` | bool | `True` **if and only if** `state == ALERT` (enforced by `validate`) |
| `drowsy_score` | [0, 1] | the score this decision came from |
| `evidence` | string | human-readable justification, e.g. `"ALERT: score 0.93, PERCLOS 0.88, closure 1.77s"` |
| `latency_ms` | ms | capture→decision, filled in by the pipeline (which owns the clock) |

**Empty behaviour:** a decision **always exists**, even when upstream is invalid —
there is always an answer to "should the alarm be sounding". With invalid input the
module returns `valid=False` with a reason, while holding a latched `ALERT` through the
gap (see §5).

`evidence` is not decoration: it drives the demo overlay and the failure analysis, both
of which are graded ("Alert thresholds and failure analysis" is **R** for this
sub-group in the RACI).

## 4. The three brakes on false alerts

All three are independent, and you should be able to show on real clips what happens
when each is removed. That demonstration is worth more than the code.

**1. Asymmetric thresholds (hysteresis).** Rising into a state needs a higher score
than falling out of it, so a score hovering on a boundary cannot flicker.

```
            rising      falling
WARN         0.45        0.35
ALERT        0.70        0.55
```

**2. Dwell time** (`min_dwell_s`, 0.40 s). A candidate state must persist before it is
adopted. A single noisy frame cannot raise an alarm —
`test_single_spike_does_not_raise_an_alert` pins this.

**3. Latching** (`alert_latch_s`, 1.50 s). Once `ALERT` fires it holds, so the alarm
does not stutter off the moment the driver's eyes flick open.

Plus a **confidence gate**: below `min_confidence` (0.50) upstream coverage, the module
refuses to escalate at all. SG-4's `confidence` is observation coverage, so this means
"do not raise an alarm from a PERCLOS computed out of three usable frames."

## 5. The sustained-closure override

If `longest_closure_s` ≥ `closure_override_s` (1.20 s), go straight to `ALERT` —
bypassing the score, the dwell timer and everything else.

A driver with their eyes shut for over a second at speed is an emergency. No amount of
window-averaging should be able to smooth that away, and a dwell timer on an emergency
would be the wrong kind of caution.

Related: a live `ALERT` is **held through an observation gap** within its latch window.
Losing the face mid-alert must not silence the alarm — the driver did not become safe
because the camera stopped seeing them.
(`test_alert_survives_an_observation_gap_within_the_latch`)

## 6. How to run

```bash
python module_sg5/run.py                                  # against mock_temporal.json
python module_sg5/run.py --dump module_sg5/results/run01.json
pytest module_sg5/tests -q
python integration/run_pipeline.py --source mock --check-scenario   # end to end
```

Config: `configs/default.yaml` — all thresholds, dwell, latch, override, confidence gate.
Inconsistent thresholds are rejected at construction rather than silently misbehaving.

## 7. ⚠ Open problem: `WARN` never happens

On the mock run the system goes **straight from OK to ALERT**, never passing through
`WARN`. The intermediate state is effectively dead code and completely untested on real
data.

Two causes, both real:

1. The sustained-closure override jumps to `ALERT` by design, skipping `WARN`. Correct
   for an emergency.
2. The score crosses `warn_on` (0.45) and `alert_on` (0.70) within a few frames, because
   0.60 of it comes from PERCLOS alone and PERCLOS climbs fast once the eyes shut.

**Decide what `WARN` is for.** If it should drive a gentler cue — a chime rather than an
alarm — it needs its own evidence path and a score band wide enough to sit in. If it has
no purpose, **remove it from the contract** rather than shipping a state that never
occurs. Either answer is defensible; shipping an unreachable state is not.

Raise this before the Lab 3 freeze — removing an enum member afterwards is a breaking
change.

See also `module_sg4/README.md` §7: the alarm also never *clears* within the clip. That
one is shared between SG-4 and SG-5.

## 8. Test data

- `interfaces/mock/mock_temporal.json` — 300 frames, 10 s.
- `tests/test_decision.py` — 16 tests, deliberately weighted toward **not** alerting:
  single-spike rejection, boundary chattering, low-confidence refusal, latch hold, latch
  expiry, gap survival, override immediacy, override boundary, threshold validation.
- Real clips: none yet. **The number this module lives or dies by is false alarms per
  hour on footage of an awake driver**, and no such footage exists yet. Ask for it early
  — it is the cheapest data to collect in the whole project.

## 9. Current performance

Measured on `mock_temporal.json`, 300 frames, Windows AMD64, CPython 3.12:

| Metric | Value |
|---|---|
| Latency, mean | **0.008 ms/frame** |
| Latency, p95 | 0.015 ms |
| Alarm fired at | 6.20 s (closure began 5.20 s → **1.00 s lag**) |
| False alarms in the awake opening | 0 ✓ |
| State transitions over 10 s | 2 (no chattering) ✓ |
| Contract violations | 0 |

| Metric | Target | Measured |
|---|---|---|
| **False alarms / hour, awake driver** | **< 1** | — |
| Drowsy-episode recall | > 0.90 | — |
| Alert latency from episode onset | < 2 s | 1.00 s (synthetic) |

Use `evaluation/src/metrics.py` for these — it scores **episodes, not frames**, because
frame accuracy flatters a detector that misses every microsleep.

## Still owed

- [ ] **Resolve §7** — decide `WARN`'s purpose before the contract freeze
- [ ] Resolve the never-clearing alarm, with SG-4
- [ ] Clips of an awake driver, to measure false alarms per hour (**ask at Lab 3**)
- [ ] Threshold study: how do recall and false-alarm rate trade off? (Lab 5)
- [ ] Ablation: remove hysteresis, then dwell, then latch — show what each one buys
      (Lab 6). This is the clearest evidence you can present for this module.
- [ ] **SVM / small MLP comparison** (Labs 5–6, scored 50) — only meaningful once there
      is enough labelled data to train without overfitting (risk R5)
- [ ] Alert modality with SG-6: sound, visual, or both; and what happens on repeat
      alerts (Lab 9)
