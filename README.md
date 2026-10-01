# Driver Drowsiness Monitoring — Team G2-D1

**CS-477 Computer Vision · SEECS CV Face-Off 2026 · Semester Project**
Target platform: **NVIDIA Jetson Orin Nano 8GB** · CUDA · TensorRT FP16 · GStreamer · Python 3.10 · OpenCV

An embedded driver-monitoring system that watches facial and behavioural cues **over
time** and produces a robust drowsiness state and alert — rather than guessing from a
single frame.

```
CAMERA ──► SG-1 ──┬──► SG-2 ──┐
USB-UVC    face   │    eye     ├──► SG-4 ──► SG-5 ──► ALERT
720p30     + 68   └──► SG-3 ──┘   temporal   decision   OK/WARN/ALERT
           landmarks   yawn        PERCLOS    hysteresis
```

| Arrow | Payload |
|---|---|
| CAMERA → SG-1 | `frame` uint8 H×W×3 BGR |
| SG-1 → SG-2 | `face_box` + eye ROIs + 68 landmarks |
| SG-1 → SG-3 | `mouth_roi` + 68 landmarks |
| SG-2 → SG-4 | `eye_state` + `ear` float |
| SG-3 → SG-4 | `yawn_flag` + `mar` float |
| SG-4 → SG-5 | `drowsy_score` 0 … 1 |
| SG-5 → alert | `state` |

> **Interface rule.** Every arrow carries: data type · units · coordinate convention ·
> confidence · empty behaviour · example payload. All six are enforced in code, in
> [`interfaces/contracts.py`](interfaces/contracts.py).

---

## Start here — five minutes, no camera, no models

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

That last command runs the **entire system** against a synthetic driver who blinks,
yawns, falls asleep for 1.8 seconds and turns away from the camera. You should see:

```
frames            : 300
states            : OK 186  WARN 0  ALERT 114
contract violations: 0
scenario check    :
  PASS  alarm fired at 6.20s during the 1.80s closure starting 5.20s (lag 1.00s)
  PASS  no false alarm in the alert driver's first 2.0s
```

**Nothing above needs a camera, a Jetson, or any model weights.** That is the point: the
guide requires that *"no pair should wait for the preceding module to be completed"*, so
every pair can start today.

---

## Repository layout

```
interfaces/       the frozen contracts + synthetic mock data   <-- READ THIS FIRST
common/           shared helpers: config, timing, video, JSON
module_sg1/       Driver Face & Landmark Detection
module_sg2/       Eye State & Blink Analysis
module_sg3/       Yawn & Facial-Cue Analysis
module_sg4/       Temporal Behaviour Analysis
module_sg5/       Drowsiness Decision & Alert Logic
embedded_sg6/     Jetson deployment, capture, profiling
integration/      the pipeline that chains all five + end-to-end tests
evaluation/       episode-level metrics, shared so reports compare
datasets/         manifests and scripts only -- never the data itself
documentation/    team, roadmap, RACI, risks, decisions, findings
```

## Sub-groups and status

| | Module | Baseline | Status | Owners (NUST ID) |
|---|---|---|---|---|
| **SG-1** | [Face & landmarks](module_sg1/README.md) | MediaPipe FaceMesh | 🔴 **never run** | 466391, 464775 |
| **SG-2** | [Eye state & blink](module_sg2/README.md) | Eye Aspect Ratio | 🟢 runs on mock | 457506, 455712 |
| **SG-3** | [Yawn & facial cues](module_sg3/README.md) | Mouth Aspect Ratio | 🟢 runs on mock | 456020, 456910 |
| **SG-4** | [Temporal analysis](module_sg4/README.md) | PERCLOS + window | 🟡 see §7 of its README | 459631, 481329 |
| **SG-5** | [Decision & alert](module_sg5/README.md) | weighted + hysteresis | 🟡 see §7 of its README | 472195, 403897, 459305 |
| **SG-6** | [Jetson & integration](embedded_sg6/README.md) | — | 🔴 **unassigned** | — |

🟢 on track · 🟡 at risk, mitigation documented · 🔴 blocking

Names are omitted deliberately — the allocation PDF's name-to-ID pairing could not be
extracted reliably and **needs confirming at the first team meeting**. See
[`documentation/team.md`](documentation/team.md).

---

## Four things that need a decision at Lab 3/4

These are cheap to change now and expensive later. Do not inherit them silently.

**1. SG-6 is unassigned.** The allocation sheet lists no pair for Embedded Deployment &
Integration, while four rows of the RACI have SG-6 as *Responsible* — including the
Jetson base image that everything else depends on. Nobody reaches Integration Gate 2
(Lab 11) without it. Raise it with the instructor. Logged as risk **R10**.

**2. SG-1's landmark mapping is unverified.** `FACEMESH_TO_IBUG68` maps MediaPipe's 468
mesh vertices onto the 68-point layout that SG-2 and SG-3 depend on completely. It is the
standard community mapping, **checked by nobody**. If one index is wrong, EAR and MAR are
quietly wrong on every frame and nothing crashes to tell you.

```bash
python module_sg1/run.py --source 0 --verify-landmarks
```

**3. The alarm never clears.** On the mock run it fires at 6.20 s and stays on to the end
of the clip, even though the driver recovers at 9.0 s. The cause is structural, not a
threshold: SG-4's `longest_closure_s` keeps reporting the 1.8 s closure for as long as it
sits inside the 3-second window. The likely fix adds a field to the contract — **much
cheaper before the freeze.** See
[`documentation/baseline_findings.md`](documentation/baseline_findings.md) §2.

**4. `WARN` never happens.** The system goes straight from OK to ALERT, so the
intermediate state is unreachable and untested. Either give it a purpose and a wide
enough score band, or remove it from the contract. Removing an enum member after the
freeze is a breaking change.

---

## The contract, and why it is code

Each interface must fix six things by Lab 4: format, units, coordinate convention,
confidence, empty-output behaviour, and example data. As prose, five pairs interpret
those five ways and the mismatch surfaces at Integration Gate 1. As dataclasses with a
`validate()` function, a computer checks them on every push.

**Coordinates:** pixels, origin **top-left of the full frame**, x right, y down.

**Confidence:** float in `[0.0, 1.0]`.

**Empty behaviour:** every module, on every failure, returns its payload with
`valid=False` and a non-empty `reason`. **Never `None`. Never an exception.** This is why
the pipeline survives a lost face, an unwritten module, and a module that throws.

**Eye sides are subject-relative.** iBUG indices 36–41 are the driver's **right** eye,
which appears on the **left** of a non-mirrored image. This is the classic silent bug in
this problem space — it never crashes, it just mislabels every ROI.

Changing `contracts.py` after the freeze needs team agreement, a `SCHEMA_VERSION` bump and
regenerated mocks, in one pull request. See
[`documentation/interface_change_policy.md`](documentation/interface_change_policy.md).

## The mock driver

Deterministic — no randomness, no seeds — so two students on two machines get identical
files and can compare results. 300 frames, 10 seconds at 30 FPS:

| Time | What happens |
|---|---|
| 0.0–2.0 s | alert driver, two normal blinks |
| 2.2–3.4 s | a yawn |
| 4.0–5.0 s | one more blink |
| 5.2–7.0 s | **sustained closure, 1.8 s** — must end in `ALERT` |
| 7.0–8.0 s | microsleeps |
| 8.0–9.0 s | **no face** — exercises the empty-behaviour rule |
| 9.0–10.0 s | recovery |

The landmarks are synthetic but **geometrically consistent**: the eye hexagons are built
so the standard EAR formula evaluates to exactly the scripted aperture, verified to within
0.00003, and the lip ellipse likewise for MAR to within 0.00012. So SG-2 and SG-3 run
their **real** maths on it and recover the scripted curve.

```bash
python interfaces/mock/generate_mocks.py       # regenerate; never hand-edit the JSON
```

> **No graded accuracy number may come from the mock.** It has no camera noise, no motion
> blur, no glasses and no lighting variation. It will flatter any method, including a bad
> one. Real data is [`datasets/README.md`](datasets/README.md), and collecting it has the
> longest lead time in the project — risk **R1**, the highest exposure on the register.

---

## Common commands

```bash
python -m pytest -q                                    # all 102 tests
pytest interfaces/tests -q                             # the Lab 3 interface gate
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

## Current measured state

Everything below is from an actual run on a development PC (Windows AMD64, CPython 3.12),
not an estimate. Reproduce with `python integration/run_pipeline.py --source mock`.

| | Value |
|---|---|
| Tests passing | **102** (1 skipped — needs MediaPipe) |
| Contract violations across 300 frames | **0** |
| Module errors | none |
| Alarm latency behind closure onset | 1.00 s |
| False alarms while the driver is awake | 0 |
| State transitions over 10 s | 2 (no chattering) |

Per-stage cost per frame: SG-2 0.012 ms · SG-3 0.006 ms · SG-4 0.063 ms · SG-5 0.008 ms ·
**end to end 0.103 ms**.

> **Do not quote an FPS figure from that.** It excludes SG-1 and camera capture, which
> will dominate the entire budget. The performance question for this project is SG-1 plus
> capture on a Jetson, and neither has run yet.

**Not yet measured at all:** any accuracy figure, anything on the Jetson, anything on real
video, and SG-1 in any form.

---

## Where to read next

| If you are… | Read |
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

## Assessment, briefly

**Grade = 60% sub-group + 40% overall project + up to 5% Face-Off bonus.**

The overall 40% is capped by how complete the system is: **40/40** for a working
end-to-end system on the Jetson, **max 30/40** if an essential module is missing, **max
20/40** for modules with no working pipeline.

That cap is why this repository is organised around continuous integration rather than
five separate module folders that meet in week eleven. A module that works alone but
cannot integrate through its agreed interface **is not complete**.

The three formal gates: **Lab 3** interface · **Lab 8** real modules replace mocks ·
**Lab 11** full pipeline on the Jetson. Labs 12–14 optimise and validate an *existing*
integrated system — the guide is explicit that first-time integration must not begin
there.
