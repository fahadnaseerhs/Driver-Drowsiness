# SG-3 — Yawn & Facial Cues  (branch `sg3/yawn-cues`)

## What this README is about
A quick guide to the `sg3/yawn-cues` branch: what this part of the system does, what we did on
it this week, how to run it, and what's next. Work for this module lives in `module_sg3/`.

## What's the project
A driver drowsiness monitor: a camera watches the driver, the system reads the eyes and
mouth, decides if they're getting drowsy, and sounds an alarm. It runs on an NVIDIA Jetson
Orin Nano. It's built by six pairs at once — each owns one stage and they connect through a
fixed data format, so no one waits for anyone else.

## What this module does
Detects yawns from how wide the mouth opens (Mouth Aspect Ratio) and for how long.

## How we did it this week
Baseline (MAR with a threshold) runs on mock input. This week: try a different MAR threshold or require the mouth to stay open a minimum time before it counts as a yawn; measure false yawns and missed yawns.

## How to run it
```bash
git checkout sg3/yawn-cues
git merge origin/main        # get the latest shared code
pip install -r requirements.txt
python module_sg3/run.py
python module_sg3/run.py --config module_sg3/configs/experiment_a.yaml --dump module_sg3/results/exp_a.json
```
Quick self-check before you push:
```bash
ruff check .
pytest -q
python integration/run_pipeline.py --source mock --check-scenario
```

## What's the task for next week
Run the chosen setting on live recordings and pick the one that separates real yawns from talking/smiling.

## Other project notes
Reads FaceResult, outputs YawnResult (MAR, yawn flag/event, duration). SG-4 reads it. Build against interfaces/mock/mock_face.json. Edit only module_sg3/. For now we test against the mock data; the real numbers come from our own **live
recordings** (saved under `datasets/clips/`, scored with `evaluation/run_eval.py`).

---
*Full project plan: `Driver Drowsiness/Planning/Big-6 Plan.md`. Detailed module design (if present): `module_sg3/DESIGN.md`.*
