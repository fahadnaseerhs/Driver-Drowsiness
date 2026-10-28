# SG-2 — Eye State & Blink Analysis

**Owners:** Anss Ahmad & Sammi — NUST 457506, 455712 — *confirm the ID ↔ name pairing in `documentation/team.md`*
**Status:** 🟢 GREEN — baseline implemented, runs on mock data, 0 contract violations;
live webcam demo added. No real-data accuracy yet.

## 1. Purpose

Decide whether the driver's eyes are open or closed on each frame, count blinks, and
track how long the eyes have been continuously closed.

Eye behaviour is the strongest single drowsiness cue, and the guide separates it out
precisely because it is *"a major but independently testable drowsiness cue."*

The important distinction this module owns: **a blink is not a closure.** A 120 ms
blink is normal alertness. A 1.8 s closure is a microsleep. If they get conflated,
SG-4 sees an inflated blink rate and loses the PERCLOS signal that actually matters.

### Where SG-2 sits

```
CAMERA ─► SG-1 face + 68 landmarks ─► SG-2 EYE (EAR) ─┐
                               └────► SG-3 YAWN (MAR) ┴─► SG-4 PERCLOS window ─► SG-5 OK/WARN/ALERT
```

### Algorithm choice

| Option | Role | Why |
|---|---|---|
| **EAR on landmarks** (Soukupová & Čech, 2016) | **Baseline** — `src/eye_state.py` | ~0.01 ms/frame, no model, explainable, scale-invariant. Weak on glasses, glare, low light, large head yaw. |
| **MobileNetV2 open/closed classifier** on SG-1's eye ROIs | **Comparison** (Labs 5–6) | Learns appearance, so it copes better with glasses and dim light; costs memory and FPS on the Jetson. Ties EAR at 49 in the decision matrix, so the choice is made with measured numbers. |
| dlib HOG + 68-point predictor, same EAR | Landmark-source cross-check | Same EAR maths on a different landmark detector; useful to tell an EAR failure apart from an SG-1 landmark failure. |

## 2. Dependencies

The analyser (`src/eye_state.py`) is pure Python and the standard library. **No numpy,
no OpenCV, no model.**

That is deliberate: this module runs anywhere, in CI, with no install, which means it
can be tested on every push from week one. Keep it that way unless the CNN comparison
forces otherwise.

The **live demo** (`live_demo.py`) additionally needs what SG-1 needs, all pinned in the
root `requirements.txt`: `mediapipe==0.10.14`, `opencv-python==4.10.0.84`,
`numpy==1.26.4`, `PyYAML`.

> **Windows:** use Python **3.10–3.12** (3.11 recommended). The pinned
> `mediapipe==0.10.14` only ships wheels up to Python 3.12, and newer MediaPipe releases
> dropped the legacy `mp.solutions` API that SG-1 uses. Either mismatch ends in
> `AttributeError: module 'mediapipe' has no attribute 'solutions'`.
> The demo checks this at start-up and prints the fix. Also make sure no file or folder
> called `mediapipe` sits next to your script, because it would shadow the package.

## 3. Input / output interface

```
FaceResult  ->  EyeResult
```

**In** — `FaceResult` from SG-1. Uses `landmarks[36:42]` (driver's right eye) and
`landmarks[42:48]` (left). Ignores `image` entirely.

**Out** — `interfaces.contracts.EyeResult`:

| Field | Units | Meaning |
|---|---|---|
| `ear_left`, `ear_right` | ratio | per-eye Eye Aspect Ratio, or `None` if degenerate |
| `ear` | ratio | mean of the eyes that were available |
| `eye_state` | enum | `OPEN` / `CLOSED` / `UNKNOWN` |
| `blink_event` | bool | `True` on the frame a blink **completes** |
| `closure_duration_s` | seconds | continuous closure up to this frame; `0.0` when open |
| `confidence` | [0, 1] | lowered to 0.6× when only one eye was usable |

**EAR definition, frozen for V1** (0-indexed iBUG):

```
EAR = (|p37 - p41| + |p38 - p40|) / (2 × |p36 - p39|)     per eye
```

Scale-invariant: the driver leaning closer does not change it. Changing this formula
breaks `interfaces/mock/mock_eye.json` — raise it with the team first.

**Empty behaviour:** upstream `valid=False`, or collapsed eye landmarks, returns
`EyeResult.empty(...)` with the upstream reason propagated.

> **An unobserved driver is not a closed-eye driver.** When the face is lost, this
> module resets `closure_duration_s` to 0 rather than carrying it forward. Inventing
> closure through a tracking gap would manufacture drowsiness evidence out of a
> camera problem.

**Live demo I/O** (`live_demo.py`):

| | What |
|---|---|
| In | webcam index (`--source 0`) or a video file, BGR frames, 1280×720 requested |
| Out | an OpenCV window with the HUD (EAR per eye and mean, OPEN/CLOSED, blink count and blinks/min, closure time, threshold, FPS, contract violations, rolling EAR graph); a red **DROWSINESS ALERT** banner and a beep when the eyes have been closed for `--alert-s` (default 1.5 s); optional `--dump` JSON of every `EyeResult`; a one-line summary on exit |

The demo alert is a stand-in for SG-4/SG-5 so a single module can be shown on its own;
the system's real decision is SG-5's.

## 4. How to run

```bash
python module_sg2/run.py                                  # against mock_face.json
python module_sg2/run.py --dump module_sg2/results/run01.json
python module_sg2/run.py --config module_sg2/configs/experiment_a.yaml
pytest module_sg2/tests -q
```

Live webcam (needs `pip install -r requirements.txt`):

```bash
python module_sg2/live_demo.py                                    # laptop webcam
python module_sg2/live_demo.py --source 1                         # external camera
python module_sg2/live_demo.py --alert-s 2.0 --dump module_sg2/results/live01.json
```

Keys: `q`/`Esc` quit · `r` reset counters · `[` / `]` EAR threshold −/+ 0.01 · `m` mirror.
The preview is mirrored for the driver, but SG-1 always gets the un-mirrored frame,
as the contract requires.

Config: `configs/default.yaml` — `ear_threshold`, `hysteresis`, `min_blink_s`,
`max_blink_s`, and an optional per-driver baseline normalisation (off by default).

## 5. Test data

- `interfaces/mock/mock_face.json` — 300 frames, 10 s. Contains six short blinks, a
  1.8 s sustained closure, and a 1 s no-face gap. The mock landmarks are built so this
  module's real EAR maths recovers the scripted curve to within 0.00003.
- `tests/test_eye_state.py` — 11 tests: EAR correctness and scale invariance, blink
  vs. closure classification, single-frame jitter rejection, threshold chattering,
  upstream failure, reset between clips.
- `tests/test_live_demo.py` — 4 tests for the demo's alert and blink-rate helpers
  (no camera needed).
- Real clips: **none yet.** Risk R1 (no glasses, no night coverage) is owned by this
  sub-group and has the longest lead time of anything on the register.

## 6. Current performance

Measured on `mock_face.json`, 300 frames, Windows AMD64, CPython 3.12:

| Metric | Value |
|---|---|
| Latency, mean | **0.012 ms/frame** |
| Latency, p95 | 0.019 ms |
| Valid frames | 270 / 300 (30 are the scripted no-face gap) |
| Blinks detected | 5 (see note) |
| Contract violations | 0 |

> Five blinks, not six. The sixth short closure ends at 7.98 s and the lids finish
> opening inside the 8.0–9.0 s no-face gap, so its completion is never observed. This
> is correct — and it means **blink rate is systematically under-reported around
> tracking dropouts.** Tell SG-4 to read `blink_rate_per_min` together with
> `confidence`, not alone.

Live webcam, SG-1 + SG-2 together (copy from the summary line `live_demo.py` prints on exit):

| Metric | Value | Hardware |
|---|---|---|
| FPS | — | *laptop CPU + webcam model* |
| SG-1 + SG-2 latency | — ms/frame | |
| Contract violations | — | |

**No accuracy figure exists**, because accuracy needs labelled real video. The mock is
synthetic and geometrically perfect; it would flatter any method, including a bad one.

| Metric | Target | Measured |
|---|---|---|
| Blink detection F1 | > 0.90 | — |
| Closure detection F1 | > 0.95 | — |
| Accuracy with glasses | > 0.85 | — |
| Accuracy at night | > 0.80 | — |

## Still owed

- [ ] Real labelled clips, including glasses and dusk (risk R1 — **start now**)
- [ ] Baseline accuracy on real data (Lab 4)
- [ ] **MobileNetV2 classifier comparison** (Labs 5–6). It ties with EAR at 49 in the
      decision matrix, which is exactly why the comparison must be measured rather
      than argued. EAR is cheap and explainable; the CNN is robust on glasses but
      costs memory and FPS. On an 8 GB Jetson that trade is the whole question.
- [ ] `ear_threshold` parameter study — is a fixed threshold viable across drivers,
      or is per-subject normalisation needed? (Lab 5) — the live demo's `[` / `]` keys
      give a quick first look.
- [ ] Failure analysis: glasses, reflections, squinting, side lighting (Lab 7)
