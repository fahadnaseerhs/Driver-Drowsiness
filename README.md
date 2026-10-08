# SG-6 — Embedded Deployment & Integration  (branch `sg6/jetson-integration`)

## What this README is about
A quick guide to the `sg6/jetson-integration` branch: what this part of the system does, what we did on
it this week, how to run it, and what's next. Work for this module lives in `embedded_sg6/`.

## What's the project
A driver drowsiness monitor: a camera watches the driver, the system reads the eyes and
mouth, decides if they're getting drowsy, and sounds an alarm. It runs on an NVIDIA Jetson
Orin Nano. It's built by six pairs at once — each owns one stage and they connect through a
fixed data format, so no one waits for anyone else.

## What this module does
Gets the whole pipeline running on the NVIDIA Jetson Orin Nano and keeps the six modules fitting together — the integration owner.

## Algorithm
SG-6 does not pick a detection algorithm — it **deploys and profiles** the ones the other
five modules chose (see `documentation/algorithm_selection.md`): MediaPipe FaceMesh (SG-1),
EAR (SG-2), MAR (SG-3), PERCLOS over a sliding window (SG-4) and weighted-score + hysteresis
(SG-5). Its own choices are about the *runtime*, not the maths:

- **What it does:** stands up a reproducible Jetson environment, runs the end-to-end pipeline
  (`integration/run_pipeline.py`) on the device, and measures frame rate, latency and memory
  against the 8 GB budget and the ~30 FPS target.
- **Why it matters:** every FPS/memory score in the decision matrix is currently an
  *estimate* made on a PC — MediaPipe's aarch64 build, and CPU-vs-GPU execution, are open
  questions until measured on the Orin Nano. Deployment is where the algorithm choices get
  confirmed or revised, and where power mode (`nvpmodel`) must be recorded with every number.
- **Decisions it drives:** CPU vs GPU per stage, whether MediaPipe runs acceptably on device,
  and whether any module must fall back to a lighter variant to hold real-time.

## How we did it this week
Needs an owner. This week: set up a Jetson environment others can reproduce, get one real module running on it, compare CPU vs GPU, and keep a log of integration problems.

## How to run it
```bash
git checkout sg6/jetson-integration
git merge origin/main        # get the latest shared code
pip install -r requirements.txt
bash embedded_sg6/jetson/setup_jetson.sh
python integration/run_pipeline.py --source clip.mp4
python embedded_sg6/profiling/profile_pipeline.py
```
Quick self-check before you push:
```bash
ruff check .
pytest -q
python integration/run_pipeline.py --source mock --check-scenario
```

## What's the task for next week
Integrate everyone's chosen configs and run the full pipeline live on the Jetson; report frame rate, latency, and memory.

## Other project notes
Uses the full pipeline (integration/run_pipeline.py) and the real-data harness (evaluation/run_eval.py). Keeps the integration branch stable and checks each branch merges without breaking the shared interface. For now we test against the mock data; the real numbers come from our own **live
recordings** (saved under `datasets/clips/`, scored with `evaluation/run_eval.py`).

---
*This is the `embedded_sg6` branch's landing README. Detailed module design: `embedded_sg6/README.md`. Full project plan: `Driver Drowsiness/Planning/Big-6 Plan.md`.*
