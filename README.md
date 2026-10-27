# SG-5 — Decision & Alert  (branch `sg5/fusion-rules`)

## What this README is about
A guide to the `sg5/fusion-rules` branch: what this part of the system does, the two
algorithms we carry, how to run each of them, where the results and graphs are kept, and
what's still broken. Work for this module lives in `module_sg5/`.

## What's the project
A driver drowsiness monitor: a camera watches the driver, the system reads the eyes and
mouth, decides if they're getting drowsy, and sounds an alarm. It runs on an NVIDIA Jetson
Orin Nano. It's built by six pairs at once — each owns one stage and they connect through a
fixed data format, so no one waits for anyone else.

## What this module does
The other groups watch the face. SG-1 finds it, SG-2 watches the eyes, SG-3 the mouth,
SG-4 adds it up over the last three seconds. They hand us numbers.

**We make the final call — OK / WARN / ALERT — and sound the alarm.** We also say *why*, in
a sentence a human can read.

> Most of our work is about **not** sounding the alarm. If it goes off for no reason the
> driver switches the whole system off, and then it protects nobody. This module owns
> risk R6.

## How to pull and push
```bash
git checkout sg5/fusion-rules    # our branch -- never work on main
git pull                         # our branch, from GitHub
git merge origin/main            # everyone else's merged work

git status                       # look before you stage
git add module_sg5               # our module only, not other groups' files
git commit -m "SG-5: <what you did>"
git push
```
Rules we follow because they're marked: never commit on `main`, small meaningful commits
(not one dump the night before), never commit another group's files, never commit video —
`datasets/clips/` is gitignored and clips of people stay off the repository.

---

## The two algorithms

| | **Chosen — running now** | **Comparison — not built yet** |
|---|---|---|
| Method | Weighted score + hysteresis | Learned scorer (logistic regression, then SVM / small MLP) |
| What it is | Hand-set rules, thresholds and timers | Coefficients fitted to labelled video |
| Matrix score | 54 | **56** |
| Needs training data | **No** | Yes — labelled clips |
| Status | Shipping, tested, demoed | Designed, **blocked on data** |

**Why we still ship the one that scores lower:** we have no labelled in-car video. A model
trained on our synthetic test data would look excellent and be worthless. That is the whole
argument — the paper score isn't the deciding factor, the missing data is.

**The design that keeps swapping cheap:** the model would replace only the *scoring* step.
The safety layer sits above it and never changes, so swapping them touches one object and
no interface fields.

### Algorithm 1 — weighted score + hysteresis (running)
Turns SG-4's `drowsy_score` into OK / WARN / ALERT with five safeguards:

1. **Asymmetric thresholds** — going up costs more than coming down (0.45/0.35 for WARN,
   0.70/0.55 for ALERT), so a score on the boundary can't flicker.
2. **Dwell time** (0.40 s) — a state must persist before it's adopted; one bad frame can't
   raise an alarm.
3. **Latch** (1.50 s) — once ALERT fires it holds, and survives a gap where the face is
   lost.
4. **Sustained-closure override** (1.20 s) — eyes shut *right now* for over a second goes
   straight to ALERT, skipping everything. That's an emergency.
5. **Confidence gate** (0.50) — refuses to escalate when upstream coverage is poor.

### Algorithm 2 — the learned scorer (comparison)
Logistic regression over the eight numbers SG-4 already sends. It's the same *shape* as
what we run now — a weighted sum through a squash — so the comparison isolates exactly one
thing: weights set by hand versus weights fitted to data. It also outputs a proper
probability, so every threshold keeps its meaning.

Then SVM, then a small MLP, only to answer "is the boundary non-linear?". If logistic
regression matches the SVM, **that's the result — report it and stop.**

Trained with scikit-learn as a dev-only tool, then exported as plain coefficients so the
Jetson runs it with one dot product and no extra dependency.

---

## How to run it
```bash
pip install -r requirements.txt

python module_sg5/run.py                                              # the module alone
python module_sg5/run.py --config module_sg5/configs/experiment_a.yaml  # the backup rules
python integration/run_pipeline.py --source mock --check-scenario     # the whole system
pytest module_sg5/tests -q                                            # 28 tests
```
Quick self-check before you push:
```bash
ruff check .
pytest -q
```

## The comparison — what each safeguard is worth
```bash
python module_sg5/tools/ablation.py     # -> module_sg5/results/ablation.md
```
Runs the decision logic seven times: once whole, once with each safeguard switched off, and
once with all of them off. Results on the purpose-built stress fixture:

| Config | State changes | Alarms | False alarms |
|---|:--:|:--:|:--:|
| **everything on** | **8** | **2** | **0** |
| no hysteresis | 19 | 2 | 0 |
| no dwell timer | 15 | 5 | 75 |
| no latch | 10 | 3 | 0 |
| no override | 6 | **1** | 0 |
| no confidence gate | 10 | 3 | 120 |
| all brakes off | **30** | **7** | 4 |

**The number to remember:** a 2.5 s eye closure with the score held down gives **53 alarm
frames with the override and 0 without it.** No alarm at all. That's the answer to "why not
just a simple threshold?"

Worth saying out loud: on the *original* test data four of the five safeguards made no
difference at all, because that data never exercised them. That's kept in the write-up —
it's why the stress fixture exists.

## Hearing the alarm
```bash
python module_sg5/tools/alarm_demo.py              # beeps, then stops
python module_sg5/tools/alarm_demo.py --source 0   # LIVE CAMERA
```
ALERT is an urgent pulsing beep; WARN is one soft chime. It pulses rather than drones,
because a continuous tone is what a driver reaches over and switches off. SG-6 owns the real
buzzer — this plays the same decisions through the laptop speaker, so it doubles as a
specification of what they have to build.

## Logging a live run, and the graphs
```bash
python module_sg5/tools/alarm_demo.py --source 0 --display --status-every 0.5 \
       --log module_sg5/results/live_01.csv

python module_sg5/tools/plot_run.py --log module_sg5/results/live_01.csv
python module_sg5/tools/plot_run.py --log module_sg5/results/live_01.csv --from 67 --to 90
```
`--log` writes one row per frame (EAR, eye state, closure, PERCLOS, score, state, evidence).
Every run ends with a diagnostics block that names where the chain broke if nothing fired.

**Where the graphs are kept:** `module_sg5/results/`, committed, as PNG.

| File | What it is |
|---|---|
| `module_sg5/results/live_01.png` | The whole 177 s live run |
| `module_sg5/results/live_01_episode4.png` | Zoom on the worst episode |
| `module_sg5/results/live_01.csv` | The raw per-frame log |
| `module_sg5/results/live_01_findings.md` | What it showed, written up |

## What the first live run showed
Real camera, 177 s, 4257 frames, one subject. 98.7 % face detection, 24 fps, no contract
violations, 9 alarms. **No accuracy figure can come from it** — nobody wrote down when the
subject was actually drowsy — but it settled three things our synthetic data got wrong:

1. **WARN is not dead code.** We had recorded it as never happening. On a real person it
   happened 12 times, 17 % of the run.
2. **The stuck alarm is worse than we thought.** All 9 alarms kept sounding after the eyes
   reopened — by 2 to 13 seconds.
3. **A problem that belongs to SG-2.** A quarter of "eyes closed" frames were the eyes
   hovering in a grey zone, not shut, and the blink rate peaked at 143/min (humans: 10–20).

## What's still broken, and whose it is
| | What | Waiting on |
|---|---|---|
| [#16](https://github.com/fahadnaseerhs/Driver-Drowsiness/issues/16) | Alarm doesn't switch off — the score it's given stays stuck at maximum | **SG-4** |
| [#13](https://github.com/fahadnaseerhs/Driver-Drowsiness/issues/13) | Does WARN get its own sound, or leave the contract? | **SG-6** |
| [#14](https://github.com/fahadnaseerhs/Driver-Drowsiness/issues/14) | 19 interface questions, one tick-box each | everyone |
| [#7](https://github.com/fahadnaseerhs/Driver-Drowsiness/issues/7) | Labelled clips, so we can finally report accuracy | team |

Answer the interface questions **in a comment on #14**, not in chat — documented
coordination is worth 2 marks and a WhatsApp reply is not documentation.

## Jetson Orin Nano
SG-6 leads this (5 marks). What matters for us:

- Our decision code is **pure standard library** — it ports with no work. We are not the
  deployment risk.
- **SG-1 is.** ~35 ms per frame on a laptop, a 24 fps ceiling, sharing 8 GB with everything
  else. The board is slower.
- `latency_ms` is left empty on purpose — the pipeline owns the clock, so SG-6 fills it.
- SG-6 must call `reset()` between clips, or clip 2 starts mid-alarm.
- Stage 1 does **not** need the whole system running on the Jetson. That's Labs 8, 9 and 11.

## What's the task for next week
Record and label clips, so the first real accuracy numbers exist — recall, and false alarms
per hour on an awake driver. Everything in `module_sg5/tools/` is ready for them; the data
is the only thing missing.

```bash
python datasets/scripts/record_clip.py --name s01_awake_day_01 --seconds 30
python datasets/scripts/make_manifest.py --clip datasets/clips/s01_awake_day_01.mp4 \
    --name s01_awake_day_01 --split train --subject s01 --closed "12.4-14.1"
python evaluation/run_eval.py --manifest datasets/manifests/s01_awake_day_01.json
```

## Other project notes
Reads `TemporalResult`, outputs `DecisionResult` (state + alert + reason + latency). This is
the safety-critical output. Build against `mock_temporal.json`. Edit only `module_sg5/`.

---
*This is the `sg5/fusion-rules` branch landing README. Detailed module design, with all the
measured numbers: `module_sg5/README.md`. Demo script: `module_sg5/DEMO.md`. Plan:
`module_sg5/ALGORITHM_PLAN.md`. Plain-language log: `Driver Drowsiness/Fahad Naseer/SG-5
Midterm Log.md`. Full project plan: `Driver Drowsiness/Planning/Big-6 Plan.md`.*
