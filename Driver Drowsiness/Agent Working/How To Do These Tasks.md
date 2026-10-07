---
tags: [driver-drowsiness, agent-working, how-to]
---
# How To Do These Tasks

Part of [[Driver Drowsiness Index]]. Task list → [[To-Do Tasks]]. Questions → [[Chats/_index|Chats]].
Written and maintained by the **Researcher**.

For every task: **how to run it**, **what the output is**, **what good output looks
like**, and **what makes the output suspicious** (reject and redo). When a pair
reports a result, the Researcher files it under the matching section and ticks
[[To-Do Tasks]].

## Ground rules for a valid result
- Baseline and alternative are run on the **same** test data, same metric.
- Numbers, not opinions: a table or plot, saved under `module_sgN/results/`.
- Before any push: `ruff check .`, `pytest -q`, and
  `python integration/run_pipeline.py --source mock --check-scenario` all pass.
- The V1 interface in `interfaces/contracts.py` is unchanged.

---

## SG-1 — Face & Landmarks
**Run**
```bash
git checkout sg1/landmark-detector
python module_sg1/run.py                                  # baseline
python module_sg1/run.py --config module_sg1/configs/experiment_a.yaml --dump module_sg1/results/exp_a.json
```
**Output** — a `FaceResult` per frame: face box, 68 landmarks, eye/mouth ROIs, confidence.
**Good output looks like** — a face found on clear frames; 68 points sitting on the real
face; eyes/mouth ROIs over the right features; plausible FPS logged.
**Suspicious — reject if** — landmarks drift off the face; left/right eye swapped (subject's
left is image-right); FPS absurd (e.g. 1000+); "face found" on an empty frame; ROIs outside
the image. These break SG-2/SG-3 downstream.
**Yield** — table comparing 2 configs (detection rate, FPS, failures) + Week 6 pick.

## SG-2 — Eye State & Blink
**Run**
```bash
git checkout sg2/eye-threshold
python module_sg2/run.py                                  # baseline on mock_face.json
python module_sg2/run.py --config module_sg2/configs/experiment_a.yaml --dump module_sg2/results/exp_a.json
```
**Output** — `EyeResult` per frame: EAR, `eye_state` OPEN/CLOSED, `blink_event`, closure duration.
**Good output looks like** — EAR drops during the scripted closures (5.2–7.0 s), blinks only on
short closures, the 1.8 s closure is **not** labelled a blink.
**Suspicious — reject if** — eyes "CLOSED" the whole clip; blink count far above a human rate
(~10–30/min); EAR flat/constant (formula not wired to landmarks); glasses case silently ignored.
**Yield** — threshold comparison, false-open/false-closed counts, chosen threshold.

## SG-3 — Yawn & Cues
**Run**
```bash
git checkout sg3/yawn-cues
python module_sg3/run.py
python module_sg3/run.py --config module_sg3/configs/experiment_a.yaml --dump module_sg3/results/exp_a.json
```
**Output** — `YawnResult` per frame: MAR, `yawn_flag`, `yawn_event`, yawn duration.
**Good output looks like** — one yawn event around 2.2–3.4 s; MAR high only during the yawn.
**Suspicious — reject if** — constant yawning; talking/smiling counted as yawns; zero yawns on
the known yawn interval; MAR not responding to mouth opening.
**Yield** — yawn/non-yawn table for 2 configs, false pos/neg, chosen threshold.

## SG-4 — Temporal  🟡 bug first
**Run**
```bash
git checkout sg4/temporal-window
python module_sg4/run.py
python module_sg4/run.py --config module_sg4/configs/window_2s.yaml --dump module_sg4/results/window_2s.json
```
**Output** — `TemporalResult` per frame: PERCLOS, rates, longest closure, `drowsy_score` 0–1.
**Good output looks like** — PERCLOS rises during sustained closure then **falls after recovery**;
`drowsy_score` tracks it; `window_filled=False` only while warming up.
**Suspicious — reject if** — `drowsy_score` stays high ~3 s after the eyes reopen (the known bug);
PERCLOS > 1 or < 0; score ignores yawns entirely; window never fills.
**Yield** — 2 window lengths compared, stability-vs-delay trade-off, chosen window. **Bug fixed.**

## SG-5 — Decision & Alert  🟡
**Run**
```bash
git checkout sg5/fusion-rules
python module_sg5/run.py
python module_sg5/run.py --config module_sg5/configs/rule_b.yaml --dump module_sg5/results/rule_b.json
```
**Output** — `DecisionResult` per frame: state OK/WARN/ALERT, `alert` flag, `evidence`, latency.
**Good output looks like** — OK while alert, WARN→ALERT during the long closure (~6.2 s), back to
OK after recovery with a short cool-down; `alert == (state==ALERT)`.
**Suspicious — reject if** — chattering (OK↔ALERT every frame); alarm never clears; alarm fires with
no drowsy evidence; `alert` flag disagreeing with `state`.
**Yield** — 2 decision rules compared, false/missed alarms, latency, chosen rule.

## SG-6 — Jetson & Integration
**Run**
```bash
git checkout sg6/jetson-integration
# on the Jetson:
bash embedded_sg6/jetson/setup_jetson.sh
python integration/run_pipeline.py --source clip.mp4
python embedded_sg6/profiling/profile_pipeline.py
```
**Output** — a reproducible setup, a module running on Jetson, FPS/latency/memory numbers, an issue log.
**Good output looks like** — pipeline runs end-to-end on device; FPS usable (target ~30); memory within
8 GB; each sub-group branch merges into `main` without breaking interfaces.
**Suspicious — reject if** — "works" only on the PC, never on device; FPS/memory not measured; merge
silently drops interface fields; numbers quoted with no command to reproduce them.
**Yield** — setup doc, on-device numbers, integration-issue log.

---

## How the Researcher files a reported output
1. Confirm the result passes the three pre-push checks above.
2. Save the raw dump under `module_sgN/results/` with a clear name.
3. Run the **Suspicious** checklist for that module; if any red flag → send it back with feedback.
4. If clean → tick the item in [[To-Do Tasks]] and note the Week 6 implication.
5. Record any question/answer in [[Chats/_index|Chats]].
