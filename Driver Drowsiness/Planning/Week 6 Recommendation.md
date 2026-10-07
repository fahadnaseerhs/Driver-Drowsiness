---
tags: [driver-drowsiness, planning, week-6, recommendation]
---
# Week 6 Recommendation — candidate per sub-group

Part of [[Driver Drowsiness Index]]. Plan: [[Week 6 Plan (APPROVED)]]. Overview: [[Big-6 Plan]].

> These are the **candidates to carry into Week 6's rigorous comparison** — the justified
> starting points from the Week-4 baselines and each module's decision matrix. They are
> **not** final picks: Week 6 confirms or overturns each on **live-recorded** clips with
> `evaluation/run_eval.py`. No graded number comes from the mock.

| SG | Baseline (keep) | Alternative to test in W6 | Metric that decides | Recommended default* |
|---|---|---|---|---|
| **SG-1** | MediaPipe FaceMesh @ default conf/res | lower confidence **or** higher input resolution | detection rate, precision/recall, FPS | keep FaceMesh; tune confidence for recall without FPS collapse |
| **SG-2** | EAR, threshold 0.21 | EAR thresholds 0.18 / 0.25, **and** glasses cases | false open / false closed | EAR baseline; pick threshold per the false-open/closed curve on live clips |
| **SG-3** | MAR, threshold 0.45 | MAR threshold **and** yawn-persistence time | yawn FP / FN | MAR baseline; add a short persistence gate to kill talking/smiling FPs |
| **SG-4** | PERCLOS + 3 s window | 2 s vs 3 s window; **closure-term source** (`longest` vs recency-weighted); `perclos_ref` | stability vs detection-delay; false/missed | keep PERCLOS; study the closure term + `perclos_ref` on live data (the stuck-alarm follow-up) |
| **SG-5** | weighted score + hysteresis + override | thresholds vs a state-machine rule | false-alarm rate, missed-alarm rate, latency | keep weighted+hysteresis (override now on `current_closure_s`); tune `alert_on/off` on live FAs |
| **SG-6** | — | CPU vs GPU / FP16 on Jetson | end-to-end FPS, latency, memory | run the integrated pipeline on Jetson Orin Nano; confirm ~30 FPS within 8 GB |

\* *Recommended default = the sensible config to start Week 6 from; the live-clip metrics
have the final say.*

## Why these (short)
- Decision matrices in the module READMEs already score the baselines highest (PERCLOS 56,
  weighted+hysteresis 54, FaceMesh 55) — so Week 6 is about **confirming on real behaviour
  and tuning operating points**, not swapping architectures.
- SG-4/SG-5's structural stuck-alarm risk is already fixed (`current_closure_s`); the
  remaining SG-4 question (closure-term source, `perclos_ref`) is a **live-data tuning**
  study, flagged explicitly so nobody tunes it on the mock.

## What must happen first
1. Each pair records + labels live clips and adds a manifest under `datasets/`.
2. Run `run_eval.py` for baseline and alternative; file results in `module_sgN/results/`.
3. Fill the real pick + numbers into each branch README and this table.
