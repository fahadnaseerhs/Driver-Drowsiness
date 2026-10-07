---
tags: [driver-drowsiness, agent-working, todo]
---
# To-Do Tasks

Part of [[Driver Drowsiness Index]]. Maintained by the **Researcher**.
How to do them → [[How To Do These Tasks]]. Questions → [[Chats/_index|Chats]].

> This is the single live list of open work for the week (our **Week 1** = course
> **Week 5**). The Researcher keeps it current: open = `[ ]`, done = `[x]`.
> Status as of **2026-10-07**.

## Blocking decisions (owner: team lead)
- [ ] Assign an owner to **SG-6** (Jetson & integration)
- [x] Merge `fix/stuck-alarm` into `main` (SG-5 owner approved; pushed as 8c9c079). Sub-group branches should now `git merge origin/main`.

## Researcher / Coder active work
- [x] Coder: real-data evaluation harness (PASS; MERGED to main 2683fa4, pushed)
- [x] Researcher: Week 6 plan — APPROVED (data source = live recording); see [[Planning/Week 6 Plan (APPROVED)]]
- [x] Researcher: per-branch READMEs drafted in [[Planning/Branch Guides/SG-1 branch]] … SG-6 — [ ] still to distribute onto each branch
- [x] Researcher: [[Planning/Big-6 Plan]] + [[Planning/Week 6 Recommendation]] written
- [ ] Researcher: put the To-Do on GitHub (Issues / Project board, +5 bonus)

## Per sub-group (each pair)

### SG-1 — Face & Landmarks `sg1/landmark-detector`
- [ ] Run the MediaPipe baseline and confirm one valid `FaceResult`
- [ ] Add an alternative config (`configs/experiment_a.yaml`): confidence / resolution
- [ ] Record results in `module_sg1/results/` (comparison table, FPS, failure cases)
- [ ] Write the Week 6 decision in `module_sg1/README.md`

### SG-2 — Eye State & Blink `sg2/eye-threshold`
- [ ] Add alternative config (EAR thresholds, or EAR vs classifier)
- [ ] Record results (open/closed, false-open/closed, glasses/pose/light)
- [ ] Write the Week 6 decision in README

### SG-3 — Yawn & Cues `sg3/yawn-cues`
- [ ] Add alternative config (MAR threshold / yawn-persistence)
- [ ] Record results (yawn / non-yawn, false pos/neg)
- [ ] Write the Week 6 decision in README

### SG-4 — Temporal `sg4/temporal-window`  🟡 at risk
- [x] **Fix the stuck-alarm bug** — structural fix done (PASS, `fix/stuck-alarm` dc9f837); mock PERCLOS-tail de-escalation deferred to the SG-4 experiment on real data
- [ ] Add alternative config (compare 2 window lengths)
- [ ] Record results (stability vs detection-delay trade-off)
- [ ] Write the Week 6 decision in README

### SG-5 — Decision & Alert `sg5/fusion-rules`  🟡 at risk
- [ ] Resolve the at-risk issue
- [ ] Add alternative config (2 decision rules)
- [ ] Record results (false/missed alarms, latency)
- [ ] Write the Week 6 decision in README

### SG-6 — Jetson & Integration `sg6/jetson-integration`
- [ ] Stand up a reproducible Jetson environment
- [ ] Run one real module on Jetson; compare CPU vs GPU
- [ ] Keep an integration-issue log; confirm all branches merge cleanly

## Group bonuses
- [ ] Set up and actively use a GitHub Project board (+5 with repo structure)
- [ ] Ranked reference-implementation screening — Primary + Backup (+5)
- [ ] Group-leader coordination report + one logged meeting (+2)
