---
tags: [driver-drowsiness, sg-5, decision, midterm, log]
owner: Fahad Naseer
updated: 2026-10-27
---
# SG-5 Midterm Log — what we built, found and still owe

Related: [[SG-5 Decision Flow Map]] · [[1 - Pipeline SG-1 to SG-5]] · [[Driver Drowsiness Index]] ·
[[Planning/Midterm Message To Team]] · [[Agent Working/To-Do Tasks]]

Module README (the full technical version): `module_sg5/README.md`
Demo script: `module_sg5/DEMO.md` · Plan: `module_sg5/ALGORITHM_PLAN.md`

---

## The two algorithms, in one table

| | **Primary — shipping now** | **Alternative — the comparison** |
|---|---|---|
| Name | Weighted score + hysteresis state machine | Learned risk scorer (logistic regression) |
| What it is | Hand-set rules: thresholds, timers, an emergency override | A model fitted to labelled video |
| Score on the team matrix | 54 | **56** |
| Status | Implemented, tested, demoed | Designed, not built — **blocked on data** |
| Why | Needs no training data, explains every decision, 0.008 ms/frame | Would tell us whether our hand-set weights are any good |

**Why we are still on the rule-based one even though the other scores higher:** we have no
labelled in-car video. A model trained on our synthetic test data would look excellent and
be worthless. The honest answer in the viva is exactly that sentence.

**The design that keeps both cheap:** the model would replace only the *scoring* step. The
safety layer (hysteresis, dwell, latch, override, confidence gate) sits above it and never
changes. Swapping them touches one object and zero interface fields.

---

## What we built this round

| Thing | Where | What it is for |
|---|---|---|
| Ablation study | `module_sg5/tools/ablation.py` → `results/ablation.md` | Turns each safety check off in turn and measures the damage. The 4-mark "comparative rationale" evidence |
| Stress fixture | `module_sg5/fixtures/stress_track.py` | A 975-frame track built so each mechanism actually gets exercised |
| Recovery check | `module_sg5/tools/recovery_check.py` | Does the alarm switch off after the driver wakes? Currently **fails on purpose** |
| Audible alarm | `module_sg5/tools/alarm_demo.py` | Beeps on ALERT, chimes on WARN. Runs from fixtures, the mock pipeline, or the live camera |
| Live logging | `--log` on the alarm tool | One CSV row per frame + a diagnostics block that names where the chain broke |
| Graphs | `module_sg5/tools/plot_run.py` → `results/live_01.png` | Four stacked charts; `--from/--to` to zoom |
| Recording + labelling | `datasets/scripts/record_clip.py`, `make_manifest.py` | The path from "no data" to gradeable accuracy numbers |
| Tests | `module_sg5/tests/` | 28 (22 decision + 6 alarm). Whole project: 119 |

---

## What we found — the part that earns marks

### 1. The stuck-alarm fix only fixed half the problem

Commit `8c9c079` is recorded as resolved. It is not. Measured end to end, the alarm keeps
sounding **2.05 s to 13.36 s** after the eyes reopen, and on the live run it was on for
**35.8 % of a 177 s run**.

The override half genuinely works. But a counterfactual arm reproducing the pre-fix
behaviour leaves ALERT at the *identical instant*, so the override was never the cause.
The real cause is upstream: SG-4's closure term stays saturated for a whole window, so
`drowsy_score` pins at **exactly 0.90 for 15.5 % of the run** (0.60 PERCLOS maxed + 0.30
closure maxed). Nothing for our hysteresis to de-escalate from.

→ **GitHub issue #16. Owner: SG-4 with SG-5.** Not fixable from our side.

### 2. `WARN` is not dead code after all

We had recorded it as unreachable. True on the synthetic mock (the WARN band lasts exactly
one 0.40 s dwell window), **false on a real person**: 12 entries, 17.4 % of the run.

→ **Issue #13 changes meaning.** No longer "is WARN reachable" but "does SG-6 give it its
own sound". Our alarm tool already demonstrates a distinct chime, so the answer is easy to
show.

### 3. Four of five safety checks did nothing on the mock

Disabling hysteresis, the latch, the override or the confidence gate gave byte-identical
output. The fixture never exercised them. We built one that does, and **kept the original
negative result in the write-up** — it is the reason the better fixture exists.

Decisive number: a 2.5 s eye closure with the score suppressed gives **53 ALERT frames
with the override and 0 without it**. All brakes off: 30 state changes and 7 alarms,
against 8 and 2.

### 4. A finding that belongs to SG-2

24 % of all `CLOSED` frames had an EAR inside the hysteresis band — held closed by the
trigger, not by a shut eye. Blink rate peaked at **143/min** (humans: 10–20). That inflates
PERCLOS and the closure term, which drives our alarms.

→ Worth trying `normalise_by_baseline: true`. This subject's open-eye EAR median is 0.258,
not the 0.30 the fixed threshold assumes.

### 5. First real speed numbers for the team

98.7 % face detection, **24 fps effective**, SG-1 at ~35 ms/frame — essentially the whole
frame budget, on a laptop. The Jetson is slower. → SG-6 should see this.

---

## What we corrected in our own notes

All four found by measuring, not assuming:

1. §5 documented the override against the wrong field (`longest_closure_s`); the code has
   keyed on `current_closure_s` since `8c9c079`.
2. §7 claimed the override is what skips `WARN`. The score beats it by 0.17 s. The real
   cause is the dwell timer.
3. §9's alarm time was wrong: 6.20 s → **6.27 s**, lag 1.00 → **1.07 s**.
4. §9 claimed "2 state transitions (no chattering ✓)". It is **1**, and that tidy number
   was the never-clearing alarm in disguise.

> Admitting a measured mistake is worth more than a table that silently agrees with itself
> all semester. This is the §3.5 discipline the guide asks for.

---

## Still open

| # | What | Blocked on |
|---|---|---|
| 13 | Does `WARN` get its own cue, or leave the contract? | **SG-6** |
| 16 | Stuck alarm — closure term must decay | **SG-4** |
| 14 | 19 interface questions | SG-1, SG-2, SG-3, SG-4, SG-6 |
| 7 | Labelled clips → real accuracy numbers | team |
| — | Low-confidence branch freezes state instead of decaying | our call |

**No accuracy figure exists yet** — no recall, no false alarms per hour. Nobody has written
down when the subject was genuinely drowsy. One labelled recording fixes this.

---

## Jetson Orin Nano (Component C, 5 marks — SG-6 leads)

Not our module, but we must understand the dependency:

- Our decision code is **pure standard library** — it ports to the Jetson with no work at
  all. We are not the deployment risk.
- **SG-1 is.** 35 ms/frame on a laptop; the board is slower and shares 8 GB with everything.
- If the ML arm ever wins, it needs `scikit-learn` on JetPack aarch64 — which is why the
  design exports plain coefficients and does inference with one dot product instead.
- `latency_ms` in our output is left `None` on purpose: **the pipeline owns the clock**, so
  SG-6 fills it. Alert latency is a graded KPI.
- Stage 1 does **not** require the full camera-to-decision system on the Jetson. Integration
  is Lab 8, Jetson deployment Lab 9, full embedded pipeline Lab 11.
