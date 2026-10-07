---
tags: [driver-drowsiness, branch-guide, sg6]
---
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
