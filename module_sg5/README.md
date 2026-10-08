# SG-5 — Decision & Alert  (branch `sg5/fusion-rules`)

## What this README is about
A quick guide to the `sg5/fusion-rules` branch: what this part of the system does, what we did on
it this week, how to run it, and what's next. Work for this module lives in `module_sg5/`.

## What's the project
A driver drowsiness monitor: a camera watches the driver, the system reads the eyes and
mouth, decides if they're getting drowsy, and sounds an alarm. It runs on an NVIDIA Jetson
Orin Nano. It's built by six pairs at once — each owns one stage and they connect through a
fixed data format, so no one waits for anyone else.

## What this module does
Makes the final call — OK / WARN / ALERT — from the temporal evidence, and raises the alarm. It uses hysteresis, a hold time, and a latch so the alarm doesn't flicker, plus an instant override if the eyes are shut too long.

## How we did it this week
The emergency override now triggers on the CURRENT closure (part of the stuck-alarm fix), so the alarm clears when the eyes reopen. Next: try a second decision rule (different thresholds vs a state-machine) and count false and missed alarms.

## How to run it
```bash
git checkout sg5/fusion-rules
git merge origin/main        # get the latest shared code
pip install -r requirements.txt
python module_sg5/run.py
python module_sg5/run.py --config module_sg5/configs/rule_b.yaml --dump module_sg5/results/rule_b.json
```
Quick self-check before you push:
```bash
ruff check .
pytest -q
python integration/run_pipeline.py --source mock --check-scenario
```

## What's the task for next week
Run the chosen rule on live recordings and tune the on/off thresholds against real false-alarm behaviour.

## Other project notes
Reads TemporalResult, outputs DecisionResult (state + alert + reason + latency). This is the safety-critical output. Build against mock_temporal.json. Edit only module_sg5/. For now we test against the mock data; the real numbers come from our own **live
recordings** (saved under `datasets/clips/`, scored with `evaluation/run_eval.py`).

---
*Full project plan: `Driver Drowsiness/Planning/Big-6 Plan.md`. Detailed module design (if present): `module_sg5/DESIGN.md`.*
