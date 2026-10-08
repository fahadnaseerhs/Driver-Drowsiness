# SG-2 — Eye State & Blink  (branch `sg2/eye-threshold`)

## What this README is about
A quick guide to the `sg2/eye-threshold` branch: what this part of the system does, what we did on
it this week, how to run it, and what's next. Work for this module lives in `module_sg2/`.

## What's the project
A driver drowsiness monitor: a camera watches the driver, the system reads the eyes and
mouth, decides if they're getting drowsy, and sounds an alarm. It runs on an NVIDIA Jetson
Orin Nano. It's built by six pairs at once — each owns one stage and they connect through a
fixed data format, so no one waits for anyone else.

## What this module does
Decides whether the eyes are open or closed each frame, counts blinks, and times how long the eyes stay shut — using the Eye Aspect Ratio (EAR) from the landmarks.

## Algorithm
**Chosen (baseline): Eye Aspect Ratio (EAR) with a threshold.** Scored 49 in the decision
matrix (`documentation/algorithm_selection.md`).

- **What it does:** from the six eye landmarks, EAR = (‖p2−p6‖ + ‖p3−p5‖) / (2·‖p1−p4‖) —
  the ratio of eye height to width. It drops sharply when the lid closes; below a threshold
  the eye is CLOSED. From that the module times closure duration and flags a blink only on a
  *short* closure, so a long microsleep is not mistaken for a blink.
- **Why this one:** it is arithmetic on points we already have — no model, near-zero memory
  (scored 5) and frame-rate cost (5), and fully explainable, which matters for a safety
  cue. Fast and transparent beats a black box for the baseline.
- **Being compared (Labs 5–6): a MobileNetV2 open/closed classifier (also 49 — a genuine
  tie).** EAR is cheap but degrades with glasses and low light; the CNN is robust there but
  costs memory and FPS. That trade can't be settled without glasses/night clips (risk R1) —
  fix the data before arguing about the model.

## How we did it this week
Baseline (EAR with a threshold) runs on mock input. This week: try different EAR thresholds (or EAR vs a small classifier) and check how it behaves with glasses, head tilt, and dim light — count the wrong open/closed calls.

## How to run it
```bash
git checkout sg2/eye-threshold
git merge origin/main        # get the latest shared code
pip install -r requirements.txt
python module_sg2/run.py
python module_sg2/run.py --config module_sg2/configs/experiment_a.yaml --dump module_sg2/results/exp_a.json
```
Quick self-check before you push:
```bash
ruff check .
pytest -q
python integration/run_pipeline.py --source mock --check-scenario
```

## What's the task for next week
Run the chosen threshold/method on live recordings and lock in the operating point that minimises wrong open/closed calls.

## Other project notes
Reads FaceResult, outputs EyeResult (EAR, open/closed, blink, closure time). SG-4 reads it. Build against interfaces/mock/mock_face.json. Edit only module_sg2/. For now we test against the mock data; the real numbers come from our own **live
recordings** (saved under `datasets/clips/`, scored with `evaluation/run_eval.py`).

---
*This is the `module_sg2` branch's landing README. Detailed module design: `module_sg2/README.md`. Full project plan: `Driver Drowsiness/Planning/Big-6 Plan.md`.*
