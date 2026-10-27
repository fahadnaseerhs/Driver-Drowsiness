# Live run 01 — first real-data findings

**Date:** 2026-10-26 · **Subject:** 1 (SG-5 owner), laptop webcam, indoor light, no glasses
**Run:** 4257 frames, 177 s, 24.0 fps effective · **Log:** `live_01.csv` · **Plot:** `live_01.png`
**Command:** `python module_sg5/tools/alarm_demo.py --source 0 --display --status-every 0.5 --log module_sg5/results/live_01.csv`

> **Status of these numbers.** This is one unlabelled run of one subject with no ground
> truth, so **no accuracy figure may be quoted from it** — no recall, no precision, no
> false alarms per hour. What it *does* establish is mechanism behaviour on real pixels,
> and that is enough to settle three things the synthetic mock got wrong.

---

## 1. The whole chain works on a real face

| | |
|---|---|
| Face detected | 4203 / 4257 frames (**98.7 %**) |
| Effective frame rate | **24.0 fps** (SG-1 is the bottleneck, ~35 ms/frame) |
| Contract violations | 0 |
| ALERT episodes | 9 |

SG-1 → SG-2 → SG-3 → SG-4 → SG-5 → audible alarm, end to end, on live camera input. Every
alarm fired, and the `evidence` string named its cause each time.

## 2. ⚠ `WARN` **is** reachable on real input — the README was wrong

`README.md` §7 recorded `WARN` as unreachable dead code, based on the synthetic mock. On
real input:

| | |
|---|---|
| `WARN` entries | **12** |
| `WARN` frames | 739 (**17.4 %** of the run) |
| Longest `WARN` stretch | 3.48 s |

The mock produced exactly 12 `WARN`-band frames — one `min_dwell_s` window — so the
candidate state never survived long enough to be adopted. A real score moves far more
slowly and sits in the 0.45–0.70 band for seconds at a time.

**Consequence for issue #13:** the question is no longer "is `WARN` dead code". It is live
and occupies a sixth of the run. The decision is now purely about actuation — does SG-6
give it a distinct cue, or does a state nobody can hear belong in the contract at all?

## 3. ⚠ The stuck alarm is far worse on real data than on the mock

**Every one of the 9 ALERT episodes outlived the eye closure that caused it.**

| # | Alarm | Raised by | Eyes reopened | Alarm cleared |
|---|---|---|---|---|
| 1 | 14.95 → 22.97 s | override | 19.59 s | **+3.38 s** |
| 2 | 34.53 → 38.25 s | override | 34.66 s | **+3.59 s** |
| 3 | 52.92 → 56.83 s | override | 53.52 s | **+3.31 s** |
| 4 | 67.58 → 82.84 s | override | 69.48 s | **+13.36 s** |
| 5 | 83.94 → 88.94 s | score | 83.94 s | **+5.00 s** |
| 6 | 99.77 → 102.80 s | score | 99.77 s | **+3.03 s** |
| 7 | 119.66 → 124.77 s | override | 119.78 s | **+4.98 s** |
| 8 | 134.66 → 143.78 s | score | 138.69 s | **+5.09 s** |
| 9 | 171.77 → 177.03 s | score | 174.98 s | **+2.05 s** |

The mock showed 3.9 s. Real data shows **2.05 s to 13.36 s**, and the alarm was sounding
for **35.8 % of the entire run** against roughly 27.6 s of genuine long eye-closure.

### The mechanism, visible in the plot

`drowsy_score` is pinned at **exactly 0.90 for 659 frames — 15.5 % of the run.** That
number is not a coincidence:

```
0.90 = 0.60 (PERCLOS term, saturated)  +  0.30 (closure term, saturated)  +  0.00 (yawn)
```

Both terms are at their ceiling simultaneously, so the score carries **no information at
all** for a sixth of the run — it cannot rise, and it cannot fall until a term leaves
saturation. Measured: after a ≥1.2 s closure *ends*, `drowsy_score` takes a mean of
**3.94 s** (range 2.74–6.70 s) to fall back below `alert_off` 0.55.

Panel 2 of `live_01.png` shows it directly: `current_closure_s` (green) drops to zero the
instant the eyes open, while `longest_closure_s` (dotted) stays pinned — and panel 3 shows
the score flat-lining at 0.90 across the same stretch.

This confirms issue #16 on real data, and strengthens it: the fix must change **how the
closure term is computed**, not any threshold in SG-5.

## 4. A new finding for SG-2 — closures held open by the hysteresis

SG-2's Schmitt trigger closes below EAR 0.19 and reopens above 0.23.

| | |
|---|---|
| `OPEN` frames | 2894, EAR min/median/max 0.190 / 0.258 / 0.358 |
| `CLOSED` frames | 1309, EAR min/median/max 0.034 / 0.153 / 0.230 |
| `CLOSED` frames whose EAR sits **inside** the 0.19–0.23 band | **314 (24.0 %)** |
| Blink rate | median 20/min, **max 143/min** |

A quarter of all `CLOSED` frames are being held closed by the hysteresis rather than by a
clearly shut eye. The longest "closure" in the run was **5.78 s** — longer than a blink by
two orders of magnitude, and plausible only if the eyes really were shut that long.

A blink rate of **143/min** is physiologically impossible (resting humans blink 10–20
times a minute), so SG-2 is generating phantom blink events when the EAR hovers in the
band. Since PERCLOS and the closure term both derive from these closures, **SG-2's
threshold calibration propagates directly into SG-5's alarms.**

Worth testing: `normalise_by_baseline: true` in `module_sg2/configs/default.yaml`, which
divides EAR by a running open-eye baseline. This subject's open-eye median is 0.258, not
the 0.30 the fixed threshold assumes.

---

## What to do with this

| Finding | Owner | Action |
|---|---|---|
| Stuck alarm, 2–13 s on real data | **SG-4** with SG-5 | Issue #16 — the closure term must decay or key on `current_closure_s` |
| `WARN` is live, not dead | **SG-6** with SG-5 | Issue #13 — the question is now actuation only. Correct README §7 |
| 24 % of closures held by hysteresis; 143 blinks/min | **SG-2** | Try per-subject EAR normalisation; report the open-eye baseline per subject |
| 24 fps, SG-1 at ~35 ms/frame | **SG-6** | First real frame-budget figure; the Jetson target is below this |

**Next run:** label it. Note the start and end second of each deliberate closure while
recording, build a manifest with `datasets/scripts/make_manifest.py`, and the same run
then yields recall, precision and false alarms per hour — figures that can be graded.
