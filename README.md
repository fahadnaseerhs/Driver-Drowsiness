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

## Algorithm
**Chosen (target): weighted score + hysteresis.** Scored 54 — chosen over the plain
rule-based baseline (49) in the decision matrix (`documentation/algorithm_selection.md`).

- **What it does:** turns SG-4's `drowsy_score` into OK/WARN/ALERT with four safeguards:
  **asymmetric thresholds** (rising needs a higher score than falling, so a score on the
  boundary doesn't flicker), a **dwell time** (a state must persist before it's adopted), a
  **latch** (once ALERT fires it holds briefly so it doesn't stutter off), and a **hard
  override** straight to ALERT if the eyes are closed *right now* for too long. It also
  refuses to escalate when upstream `confidence` is low.
- **Why this one:** this is the system's only safety-relevant output and it owns risk R6 —
  *false alarms make the driver switch the system off.* Plain thresholds flicker; the
  hysteresis/dwell/latch machinery is what keeps nuisance alarms down, so there was no
  reason to ship the weaker rule-based version first.
- **Being compared (Labs 5–6):** a second decision rule (different thresholds vs a
  state-machine), and an SVM / small MLP (scored 50) once there is enough labelled data to
  train one without overfitting (risk R5).

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
*This is the `module_sg5` branch's landing README. Detailed module design: `module_sg5/README.md`. Full project plan: `Driver Drowsiness/Planning/Big-6 Plan.md`.*
