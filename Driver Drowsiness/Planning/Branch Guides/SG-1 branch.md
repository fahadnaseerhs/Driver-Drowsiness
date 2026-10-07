---
tags: [driver-drowsiness, branch-guide, sg1]
---
# SG-1 — Face & Landmark Detection  (branch `sg1/landmark-detector`)

## What this README is about
A quick guide to the `sg1/landmark-detector` branch: what this part of the system does, what we did on
it this week, how to run it, and what's next. Work for this module lives in `module_sg1/`.

## What's the project
A driver drowsiness monitor: a camera watches the driver, the system reads the eyes and
mouth, decides if they're getting drowsy, and sounds an alarm. It runs on an NVIDIA Jetson
Orin Nano. It's built by six pairs at once — each owns one stage and they connect through a
fixed data format, so no one waits for anyone else.

## What this module does
Finds the driver's face in each camera frame and places 68 landmark points on it (eyes, mouth, jaw, nose). It's the first stage — everything downstream reads its output.

## How we did it this week
Baseline is coded (MediaPipe FaceMesh, 468 points mapped to our 68). This week: actually run it and confirm it emits one valid face result, then try a second setting (detection confidence or input resolution) and note the detection rate, speed, and where it fails.

## How to run it
```bash
git checkout sg1/landmark-detector
git merge origin/main        # get the latest shared code
pip install -r requirements.txt
python module_sg1/run.py
python module_sg1/run.py --config module_sg1/configs/experiment_a.yaml --dump module_sg1/results/exp_a.json
```
Quick self-check before you push:
```bash
ruff check .
pytest -q
python integration/run_pipeline.py --source mock --check-scenario
```

## What's the task for next week
Run the baseline vs the chosen setting on our live recordings and pick the config that detects reliably without tanking the frame rate.

## Other project notes
Output is a FaceResult (face box + 68 points + eye/mouth regions). SG-2 and SG-3 read it, so don't change that shape. While building, test against interfaces/mock/mock_face.json. Edit only module_sg1/. For now we test against the mock data; the real numbers come from our own **live
recordings** (saved under `datasets/clips/`, scored with `evaluation/run_eval.py`).
