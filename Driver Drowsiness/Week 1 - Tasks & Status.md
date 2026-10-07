---
tags: [driver-drowsiness, week-1, tasking, status]
---
# Week 1 - Tasks & Status

Part of [[Driver Drowsiness Index]]. Task detail: [[4 - Week 5 First Tasks]].
Home: [[Welcome]].

> **Naming:** we call this **Week 1** (our team's first working week). It maps to the
> course's **Week 5** assessment rubric — same tasks, same marking.

Status checked against the repo on **2026-10-07**.
Legend: ✅ done · 🟡 partial · ❌ not started.

## The task this week (per sub-group, out of 10)
Each pair must: (1) keep the baseline, (2) build **one** alternative, (3) record
**numbers** comparing them, (4) keep the interface + commit cleanly, (5) write the
Week 6 decision and both understand the code.

## Overall status — what is NOT done

The **baselines exist**, but the **actual Week 5 work does not yet**:

- ❌ **No experiment/alternative** built for any module (no `experiment_*.yaml` configs).
- ❌ **No quantitative evidence** — every `module_sgN/results/` folder is empty.
- ❌ **No Week 6 decision** recorded in any module README.
- 🟡 SG-1 is **coded but never run** (MediaPipe not yet verified).
- ❌ SG-4 stuck-alarm bug **not fixed**; SG-5 risk **not resolved**.
- ❌ SG-6 **unassigned**; nothing on the Jetson.

## Per sub-group checklist

### SG-1 - Face & Landmarks `sg1/landmark-detector`
- ✅ Baseline coded (MediaPipe FaceMesh + 468→68 mapping)
- 🟡 Actually run / verified on real input
- ❌ Alternative config (confidence / resolution)
- ❌ Results: comparison table, FPS, failure cases
- ❌ Week 6 decision in README

### SG-2 - Eye State & Blink `sg2/eye-threshold`
- ✅ Baseline coded (EAR), runs on mock
- ❌ Alternative (EAR thresholds, or EAR vs classifier)
- ❌ Results: open/closed, false-open/closed, glasses/pose/light cases
- ❌ Week 6 decision in README

### SG-3 - Yawn & Cues `sg3/yawn-cues`
- ✅ Baseline coded (MAR), runs on mock
- ❌ Alternative (MAR threshold / yawn-persistence)
- ❌ Results: yawn / non-yawn, false pos/neg
- ❌ Week 6 decision in README

### SG-4 - Temporal `sg4/temporal-window` 🟡 at risk
- ✅ Baseline coded (PERCLOS + window)
- ❌ **Fix stuck-alarm bug** (alarm held ~3 s after recovery)
- ❌ Alternative (compare 2 window lengths)
- ❌ Results: stability vs detection-delay trade-off
- ❌ Week 6 decision in README

### SG-5 - Decision & Alert `sg5/fusion-rules` 🟡 at risk
- ✅ Baseline coded (weighted + hysteresis)
- ❌ Resolve the at-risk issue
- ❌ Alternative (2 decision rules)
- ❌ Results: false/missed alarms, latency
- ❌ Week 6 decision in README

### SG-6 - Jetson & Integration `sg6/jetson-integration` ❌
- ❌ **Owner not assigned**
- ❌ Reproducible Jetson environment
- ❌ One real module running on Jetson (CPU vs GPU)
- ❌ Integration-issue log; confirm all branches merge cleanly

## Group-level bonuses
- ✅ Repository structure + branches (SG-1…SG-6 folders, one branch each)
- ❌ GitHub Project board set up and actively used (+5 with repo structure)
- ❌ Ranked reference-implementation screening, Primary + Backup (+5)
- ❌ Group-leader coordination report + one meeting logged (+2)

## Bottom line
Week 4 baselines are in place. **The Week 5 deliverables — experiments, numbers,
decisions, the two bug fixes, and the Jetson work — are still to do.** First moves:
assign SG-6, and each pair adds an `experiment_*.yaml` + a results file this week.
