---
tags: [driver-drowsiness, week-5, tasking]
---
# 4 - Week 5 First Tasks & Research

Part of [[Driver Drowsiness Index]]. Pipeline detail: [[1 - Pipeline SG-1 to SG-5]].
Home: [[Welcome]].

Week 5 goal: keep the Week 4 baseline, build **one** alternative, measure both on the
same test data, keep the frozen interface, and pick a configuration for Week 6.

## Where work happens

`main` holds the frozen contracts, the mock data and the working mock pipeline. **No
new code is written on `main` this week** — it only changes when finished module work
is merged back. Each pair works on its own branch, against the mocks, in parallel.

### First task on `main` (everyone, day 1)
1. `git clone` and run `pytest` + `python integration/run_pipeline.py --source mock` — confirm green on your machine.
2. Read your module's input/output in `interfaces/contracts.py` (the "socket shape").
3. `git checkout <your branch>` and work only inside your own `module_sgN/` folder.

> **Independent ≠ no dependency.** SG-2/SG-3 depend on SG-1's *output format*, not its
> *code*. They build against `mock_face.json` today and never wait for SG-1. The only
> rule: nobody changes the format alone — see `documentation/interface_change_policy.md`.

## First task per sub-group

| SG | Branch | Very first task | Then: the Week 5 experiment |
|---|---|---|---|
| **SG-1** | `sg1/landmark-detector` | **Get it running at all** — install MediaPipe FaceMesh, map its 468 points to the 68-pt iBUG layout, output one valid `FaceResult` | Compare 2 configs (confidence / resolution); FPS + failure cases |
| **SG-2** | `sg2/eye-threshold` | Run EAR baseline on `mock_face.json`, reproduce the open/closed curve | Compare EAR thresholds (or EAR vs classifier); test glasses/pose/light |
| **SG-3** | `sg3/yawn-cues` | Run MAR baseline on `mock_face.json` | Compare MAR threshold / yawn-persistence; false pos/neg |
| **SG-4** | `sg4/temporal-window` | **Fix the stuck-alarm bug** (alarm held ~3 s after recovery, README §7) | Compare 2 window lengths; stability vs detection-delay trade-off |
| **SG-5** | `sg5/fusion-rules` | Run decision baseline on `mock_temporal.json` | Compare 2 decision rules; false/missed alarms, latency |
| **SG-6** | `sg6/jetson-integration` | **Assign an owner**, then stand up a reproducible Jetson environment | Run one real module on Jetson; CPU vs GPU; integration-issue log |

## How to do the research (every sub-group)

The +5 reference-implementation bonus and good module choices both come from the same
method. The LLM is a **search assistant, not the evidence** — every claim is verified
by hand.

1. **Find** 3+ candidate implementations for your module (GitHub + paper). Prefer
   working end-to-end code, Python/OpenCV/PyTorch, Jetson/edge evidence, pretrained
   weights, a public dataset.
2. **Verify by hand** — open each repo, actually clone/run the strongest one. Anything
   you cannot confirm is marked **Not Verified**, never invented.
3. **Score** them on the 100-point feasibility weights (End-to-end 15, Source 15,
   Jetson 15, Accuracy 10, Reproducibility 10, Weights 10, Real-time 10, Dataset 5,
   Interface 5, Maturity 5) → pick a **Primary** and a **Backup**.

### SG-1 research starter — the 68 landmarks
- MediaPipe FaceMesh gives **468** points; our contract wants the **68-pt iBUG** layout.
- Research task: find the 468→68 index mapping, then confirm the eye points feed the
  EAR formula and the mouth points feed MAR (so SG-2/SG-3 get the curve they expect).
- Verify against `mock_face.json`: your real detector's landmark order must match the
  mock's order, or integration breaks later.

## The five things each pair is graded on (out of 10)
1. Working baseline + can explain input/processing/output — 2
2. One alternative/experiment implemented — 2
3. Quantitative evidence (numbers, not "looks better") — 2
4. GitHub + interface readiness (right branch, usable README, V1 kept) — 2
5. Analysis + Week 6 decision + **both members understand the code** — 2

Put comparison numbers in `module_sgN/results/`; put the Week 6 decision in the README.
