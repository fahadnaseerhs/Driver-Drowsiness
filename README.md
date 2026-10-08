# SG-4 — Temporal Behaviour Analysis  (branch `sg4/temporal-window`)

## What this README is about
A quick guide to the `sg4/temporal-window` branch: what this part of the system does, what we did on
it this week, how to run it, and what's next. Work for this module lives in `module_sg4/`.

## What's the project
A driver drowsiness monitor: a camera watches the driver, the system reads the eyes and
mouth, decides if they're getting drowsy, and sounds an alarm. It runs on an NVIDIA Jetson
Orin Nano. It's built by six pairs at once — each owns one stage and they connect through a
fixed data format, so no one waits for anyone else.

## What this module does
Turns single-frame cues into behaviour over time: how much of the last few seconds the eyes were closed (PERCLOS), blink/yawn rates, the current and longest closure, and a combined drowsiness score. This is what makes it a real monitor instead of a frame-by-frame guess.

## Algorithm
**Chosen (baseline): PERCLOS over a sliding window.** Highest weighted score (56) of any
candidate in the decision matrix (`documentation/algorithm_selection.md`).

- **What it does:** keeps a few seconds of recent frames and computes PERCLOS — the fraction
  of that window the eyes were closed — plus blink/yawn rates, the longest and the current
  closure, and a fused `drowsy_score`. PERCLOS is computed over *valid* frames only, and
  `confidence` reports observation coverage so SG-5 can distrust a window built from few
  observations.
- **Why this one:** PERCLOS is the industry-standard fatigue measure, it is cheap
  (pure-Python, no model, high FPS, low memory), and "drowsiness is inherently temporal" — a
  single closed frame is meaningless, a window is not.
- **Being compared (Labs 5–6): an LSTM over the frame cues (scored 49, stretch goal).** It
  could learn patterns a fixed window misses, but costs memory/FPS and needs labelled data;
  the window baseline is the dependable default to beat.

## How we did it this week
Fixed the stuck-alarm bug: the alarm used to stay on ~3 s after the driver's eyes reopened. We added a current-closure signal so the alarm can clear as soon as the eyes open. Next: compare a 2-second vs 3-second window and note the trade-off between a steady signal and a fast reaction.

## How to run it
```bash
git checkout sg4/temporal-window
git merge origin/main        # get the latest shared code
pip install -r requirements.txt
python module_sg4/run.py
python module_sg4/run.py --config module_sg4/configs/window_2s.yaml --dump module_sg4/results/window_2s.json
```
Quick self-check before you push:
```bash
ruff check .
pytest -q
python integration/run_pipeline.py --source mock --check-scenario
```

## What's the task for next week
Run the chosen window on live recordings, plus tune the closure term / PERCLOS reference on real behaviour (not the mock, which is too clean).

## Other project notes
Reads EyeResult + YawnResult, outputs TemporalResult (now includes current_closure_s, schema 1.0.1). SG-5 reads it. Build against mock_eye.json + mock_yawn.json. Edit only module_sg4/. For now we test against the mock data; the real numbers come from our own **live
recordings** (saved under `datasets/clips/`, scored with `evaluation/run_eval.py`).

---
*This is the `module_sg4` branch's landing README. Detailed module design: `module_sg4/README.md`. Full project plan: `Driver Drowsiness/Planning/Big-6 Plan.md`.*
