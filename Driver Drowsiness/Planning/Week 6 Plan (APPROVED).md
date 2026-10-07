---
tags: [driver-drowsiness, planning, week-6, approved]
---
# Week 6 Plan — APPROVED

Part of [[Driver Drowsiness Index]]. Overview: [[Big-6 Plan]]. Recommendation: [[Week 6 Recommendation]].
**Approved by the user on 2026-10-08.**

## What Week 6 is (from the rubric)
Week 5 ends with a *justified candidate/configuration*; **Week 6 is the rigorous,
quantitative comparison of that candidate vs the baseline, then integration + a run on the
Jetson.**

## Data source: LIVE recording (decided)
We are **not** curating a fixed dataset. The team **records live** — webcam on a dev PC
and the camera on the Jetson — and saves those sessions under `datasets/clips/`
(git-ignored) with a manifest + ground-truth labels (`eyes_closed_s`, `yawn_s`,
`drowsy_episodes_s`). Those recordings are what `evaluation/run_eval.py` scores, and the
Week 6 demo is a live run. The mock stays for interface/unit tests only — no graded number
comes from it.

> Action: each pair records a few short live clips (alert, drowsy, yawning; with/without
> glasses; varied light) and labels them. Keep a held-out clip untouched (risk R5).

## Per sub-group in Week 6
| SG | Week 6 work | Metric reported |
|---|---|---|
| SG-1 | baseline detector vs selected alt on live clips | detection rate, precision/recall, FPS |
| SG-2 | selected EAR threshold/method (glasses/pose/light) | false open / false closed, blink error |
| SG-3 | selected MAR threshold / yawn-persistence | yawn FP / FN |
| SG-4 | selected window length **+ closure-term / `perclos_ref` follow-up** | stability vs delay; false/missed |
| SG-5 | selected decision rule | false-alarm rate, missed-alarm rate, latency |
| SG-6 | integrate all selected configs; run full pipeline on **Jetson** | end-to-end FPS, latency, memory |

How: `python evaluation/run_eval.py --manifest datasets/manifests/<name>.json --out module_sgN/results/<name>_eval.json`

## Deliverables
- **Per-branch README** × 6 — see [[Branch Guides/SG-1 branch|Branch Guides]].
- **One Big-6 Plan README** — [[Big-6 Plan]].
- **Week 6 Recommendation README** — [[Week 6 Recommendation]].

## Still open
- SG-6 owner undecided.
- Each pair to record + label live clips before Week 6 numbers can be produced.
