# Driver Drowsiness Monitoring — Team G2-D1

**CS-477 Computer Vision · SEECS CV Face-Off 2026 · Semester Project**

Target platform: **NVIDIA Jetson Orin Nano 8GB** · Python 3.10 · OpenCV · TensorRT FP16

---

## Assessment breakdown

**Grade = 60% sub-group + 40% overall project + up to 5% Face-Off bonus.**

The overall 40% is capped by system completeness:

| Completion level | Max overall score |
|---|---|
| Working end-to-end system on the Jetson | **40/40** |
| Essential module missing | **30/40** |
| Modules exist but no working pipeline | **20/40** |

A module that works alone but cannot integrate through its agreed interface **is not complete**.

**Formal gates:** Lab 3 (interface freeze) -- Lab 8 (real modules replace mocks) -- Lab 11 (full pipeline on the Jetson). Labs 12-14 optimise an existing integrated system -- first-time integration must not begin there.

---

## What is working right now

Tested on Windows AMD64, CPython 3.12. Reproduce with `python integration/run_pipeline.py --source mock`.

| Metric | Value |
|---|---|
| Tests passing | **102** (1 skipped -- needs MediaPipe) |
| Contract violations across 300 frames | **0** |
| Module errors | none |
| Alarm latency behind closure onset | 1.00 s |
| False alarms while driver is awake | 0 |
| State transitions over 10 s | 2 (no chattering) |

Per-frame cost: SG-2 0.012 ms, SG-3 0.006 ms, SG-4 0.063 ms, SG-5 0.008 ms, end-to-end **0.103 ms** (excludes SG-1 and camera capture, which will dominate on Jetson).

**Not measured yet:** any accuracy figure, anything on the Jetson, anything on real video, and SG-1 in any form.

---

## Sub-groups and status

| | Module | Baseline | Status | Owners (NUST ID) |
|---|---|---|---|---|
| **SG-1** | [Face & landmarks](module_sg1/README.md) | MediaPipe FaceMesh | never run | 466391, 464775 |
| **SG-2** | [Eye state & blink](module_sg2/README.md) | Eye Aspect Ratio | runs on mock | 457506, 455712 |
| **SG-3** | [Yawn & facial cues](module_sg3/README.md) | Mouth Aspect Ratio | runs on mock | 456020, 456910 |
| **SG-4** | [Temporal analysis](module_sg4/README.md) | PERCLOS + window | at risk, see its README | 459631, 481329 |
| **SG-5** | [Decision & alert](module_sg5/README.md) | weighted + hysteresis | at risk, see its README | 472195, 403897, 459305 |
| **SG-6** | [Jetson & integration](embedded_sg6/README.md) | -- | **unassigned** | -- |

Names are omitted -- the allocation PDF could not be parsed reliably. Confirm at the first team meeting. See [`documentation/team.md`](documentation/team.md).

---

## Decisions needed at Lab 3/4

These are cheap to change now and expensive later.

**1. SG-6 is unassigned.** The allocation lists no pair for Embedded Deployment & Integration, while four RACI rows have SG-6 as Responsible -- including the Jetson base image everything else depends on. Nobody reaches Integration Gate 2 (Lab 11) without it. Raise with the instructor. Risk **R10**.

**2. SG-1's landmark mapping is unverified.** `FACEMESH_TO_IBUG68` maps MediaPipe's 468 mesh vertices onto the 68-point layout that SG-2 and SG-3 depend on. If one index is wrong, EAR and MAR are quietly wrong on every frame with no crash to flag it.

```bash
python module_sg1/run.py --source 0 --verify-landmarks
```

**3. The alarm never clears.** It fires at 6.20 s and stays on even after the driver recovers at 9.0 s. The cause is structural: SG-4's `longest_closure_s` keeps reporting the 1.8 s closure while it sits inside the 3-second window. The fix likely adds a field to the contract -- much cheaper before the freeze. See [`documentation/baseline_findings.md`](documentation/baseline_findings.md).

**4. `WARN` never happens.** The system goes straight from OK to ALERT, making the intermediate state unreachable and untested. Either give it a purpose and a wide enough score band, or remove it from the contract before the freeze.

---

## Pipeline

```
CAMERA --> SG-1 --+--> SG-2 --+--> SG-4 --> SG-5 --> ALERT
USB-UVC    face   |    eye    |   temporal   decision   OK/WARN/ALERT
720p30     + 68   +--> SG-3 --+   PERCLOS    hysteresis
           lmks        yawn
```

| Arrow | Payload |
|---|---|
| CAMERA to SG-1 | `frame` uint8 HxWx3 BGR |
| SG-1 to SG-2 | `face_box` + eye ROIs + 68 landmarks |
| SG-1 to SG-3 | `mouth_roi` + 68 landmarks |
| SG-2 to SG-4 | `eye_state` + `ear` float |
| SG-3 to SG-4 | `yawn_flag` + `mar` float |
| SG-4 to SG-5 | `drowsy_score` 0..1 |
| SG-5 to alert | `state` |

Contracts are enforced in [`interfaces/contracts.py`](interfaces/contracts.py). Changing them after the freeze needs team agreement, a `SCHEMA_VERSION` bump, and regenerated mocks in one pull request. See [`documentation/interface_change_policy.md`](documentation/interface_change_policy.md).

---

## Quick start -- five minutes, no camera, no models

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows;  source .venv/bin/activate on Linux
pip install -r requirements-dev.txt
```

```bash
python -m pytest -q
```

```bash
python integration/run_pipeline.py --source mock --check-scenario
```

That last command runs the entire system against a synthetic driver who blinks, yawns, falls asleep for 1.8 seconds and turns away. Expected output:

```
frames            : 300
states            : OK 186  WARN 0  ALERT 114
contract violations: 0
scenario check    :
  PASS  alarm fired at 6.20s during the 1.80s closure starting 5.20s (lag 1.00s)
  PASS  no false alarm in the alert driver's first 2.0s
```

No camera, Jetson, or model weights needed. Every pair can start today.

---

## Repository layout

```
interfaces/       frozen contracts + synthetic mock data       <-- read first
common/           shared helpers: config, timing, video, JSON
module_sg1/       Driver Face & Landmark Detection
module_sg2/       Eye State & Blink Analysis
module_sg3/       Yawn & Facial-Cue Analysis
module_sg4/       Temporal Behaviour Analysis
module_sg5/       Drowsiness Decision & Alert Logic
embedded_sg6/     Jetson deployment, capture, profiling
integration/      pipeline that chains all five + end-to-end tests
evaluation/       episode-level metrics
datasets/         manifests and scripts only -- never the data itself
documentation/    team, roadmap, RACI, risks, decisions, findings
```

## Common commands

```bash
python -m pytest -q                                    # all 102 tests
pytest interfaces/tests -q                             # Lab 3 interface gate
pytest module_sg2/tests -q                             # one module
ruff check .                                           # lint
```

```bash
python module_sg2/run.py                               # one module, standalone, on mock input
python module_sg2/run.py --dump module_sg2/results/run01.json
python module_sg1/run.py --source 0 --verify-landmarks  # SG-1 needs a camera
```

```bash
python integration/run_pipeline.py --source mock --check-scenario
python integration/run_pipeline.py --source 0 --display
python embedded_sg6/profiling/profile_pipeline.py --source mock
```

## Where to read next

| If you are... | Read |
|---|---|
| joining the team | this file, then [`documentation/team.md`](documentation/team.md) |
| writing a module | [`interfaces/README.md`](interfaces/README.md), then your `module_sgN/README.md` |
| about to open a PR | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| wondering what is broken | [`documentation/baseline_findings.md`](documentation/baseline_findings.md) |
| planning the semester | [`documentation/roadmap.md`](documentation/roadmap.md) |
| choosing an algorithm | [`documentation/algorithm_selection.md`](documentation/algorithm_selection.md) |
| worried about something | [`documentation/risk_register.md`](documentation/risk_register.md) |
| wondering who owns what | [`documentation/raci.md`](documentation/raci.md) |
| deploying to the Jetson | [`embedded_sg6/README.md`](embedded_sg6/README.md) |
