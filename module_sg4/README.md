# SG-4 — Temporal Behaviour Analysis

**Owners:** NUST 459631, 481329 — *confirm names, see `documentation/team.md`*
**Status:** 🟡 **AMBER** — baseline works, but a known structural problem holds the
alarm on for 3 s after the driver recovers. See §7.

## 1. Purpose

Turn frame-level cues into **behaviour over time**. This is the module that makes the
system a drowsiness monitor rather than a frame classifier.

The guide puts it directly: *"Drowsiness is inherently temporal; this module converts
observations into behavior."* A single closed-eye frame means nothing — a blink, a
glance down, a landmark glitch. Eyes closed for 40% of the last three seconds means
something.

The primary measure is **PERCLOS** (percentage of eye closure over time), the standard
fatigue metric, scored 56 in the decision matrix — the highest of any candidate.

## 2. Dependencies

Pure Python and the standard library (`collections.deque`). No numpy, no model.

An LSTM comparison (Labs 5–6, stretch goal) would change this. Until then, keep it
dependency-free so it runs in CI.

## 3. Input / output interface

```
EyeResult + YawnResult  ->  TemporalResult
```

**In** — `EyeResult` from SG-2 and `YawnResult` from SG-3, **for the same frame**.
`yawn` may be `None` if SG-3 is not running; the yawn term then contributes 0 and
`reason` records `no_yawn_input` rather than silently pretending the driver never yawns.

**Out** — `interfaces.contracts.TemporalResult`:

| Field | Units | Meaning |
|---|---|---|
| `perclos` | [0, 1] | fraction of the window with eyes closed |
| `blink_rate_per_min` | /min | extrapolated from the window |
| `yawn_rate_per_min` | /min | extrapolated from the window |
| `longest_closure_s` | seconds | longest closure **present in the window** |
| `avg_ear` | ratio | mean EAR over valid frames |
| `drowsy_score` | [0, 1] | fused evidence, 1 = most drowsy |
| `window_s` | seconds | the window actually used |
| `window_filled` | bool | `False` while warming up |
| `confidence` | [0, 1] | **observation coverage** = valid / total frames in window |

**Baseline fusion** (weights from the Figma plan, `configs/default.yaml`):

```
drowsy_score = 0.60 × min(1, PERCLOS / 0.40)
             + 0.30 × min(1, longest_closure_s / 1.50)
             + 0.10 × min(1, yawn_events / 1)
```

These are a **starting point, not a result.** Labs 5–7 owe a sensitivity study.

## 4. Observation gaps — the design decision that matters most here

When SG-1 loses the face, SG-2 and SG-3 return `valid=False`. Those frames carry **no
information** about eye closure.

Counting them as "eyes open" would quietly dilute PERCLOS and hide real drowsiness.
So this module:

- computes PERCLOS over **valid frames only**;
- reports `confidence` = valid / total, so SG-5 can distrust a PERCLOS built from a
  handful of observations;
- **refuses to decide** when coverage falls below `min_valid_fraction` (0.5), returning
  `valid=False` with `insufficient_coverage:0.31<0.50`.

`test_invalid_frames_are_excluded_not_counted_as_open` is the test that pins this.
It is the single most important test in this module.

**Consequence for SG-5:** `confidence` is not decoration. Read it.

## 5. How to run

```bash
python module_sg4/run.py                                  # mock_eye.json + mock_yawn.json
python module_sg4/run.py --dump module_sg4/results/run01.json
pytest module_sg4/tests -q
```

Config: `configs/default.yaml` — `window_s`, `min_valid_fraction`, the four fusion
weights and their reference levels.

## 6. Test data

- `interfaces/mock/mock_eye.json` + `mock_yawn.json` — 300 frames, 10 s.
- `tests/test_temporal.py` — 13 tests: PERCLOS arithmetic, score bounds, window ageing,
  the observation-gap rule, low-coverage refusal, `frame_id` mismatch detection,
  missing SG-3 input, warm-up, reset between clips.
- Real clips: none yet. Risk **R5** (thresholds overfit to recorded clips) is owned by
  this sub-group — **keep a hold-out set untouched until Lab 13.**

## 7. ⚠ Open problem: the alarm never clears

On the mock run the state track is:

```
OK      0.00 ->  6.17 s
ALERT   6.20 ->  9.97 s      <-- runs to the end of the clip
```

The driver recovers from 9.0 s with eyes open, so the alarm should clear. It does not,
and the cause is structural rather than a threshold being slightly off:

`longest_closure_s` reports the largest closure **present in the window**. The 1.8 s
closure that ended at 7.0 s stays inside the 3 s window until 10.0 s. While it is
there, SG-5's closure term stays saturated and the score stays above `alert_off`.

**So one long closure holds the alarm on for `window_s` seconds after the driver's eyes
have reopened.** On the demo that reads as an alarm you cannot switch off — a worse
failure mode than a late alarm.

**Owner: SG-4 with SG-5.** Candidate directions, none yet measured:

1. Add `current_closure_s` alongside `longest_closure_s`, and let SG-5 de-escalate on
   the current value while escalating on the longest. **Cheapest if done before the
   Lab 3 contract freeze** — raise it now.
2. Decay the closure term by how long ago the closure ended.
3. Shorten `window_s`, trading this against PERCLOS stability.

Choose with evidence on real clips. **Do not tune against the synthetic mock** — it has
no noise and will mislead you.

## 8. Current performance

Measured on the mock sequences, 300 frames, Windows AMD64, CPython 3.12:

| Metric | Value |
|---|---|
| Latency, mean | **0.063 ms/frame** — the most expensive pure-Python stage |
| Latency, p95 | 0.116 ms |
| Valid frames | 300 / 300 |
| Peak `drowsy_score` | 0.927 |
| Contract violations | 0 |

Still cheap in absolute terms. If it ever matters, the window scan is O(window) per
frame and could become incremental — but measure before optimising.

| Metric | Target | Measured |
|---|---|---|
| PERCLOS error vs. manual labels | < 0.05 | — |
| Drowsy-episode detection F1 | > 0.85 | — |
| Score stability (no oscillation) | — | — |

## Still owed

- [ ] **Resolve §7** — propose the contract change before the Lab 3 freeze
- [ ] Baseline on real labelled clips (Lab 4)
- [ ] `window_s` parameter study: 2 s / 3 s / 5 s / 10 s (Lab 5)
- [ ] Fusion-weight sensitivity study — how do F1 and false-alarm rate move? (Labs 5–6)
- [ ] **LSTM over frame cues** comparison (Labs 5–6, stretch, scored 49)
- [ ] Hold-out discipline documented, with the date the test split was sealed (R5)
- [ ] Failure analysis: long tracking gaps, a driver who blinks unusually slowly (Lab 7)
