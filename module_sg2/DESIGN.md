# SG-2 — Eye State & Blink Analysis

**Owners:** NUST 457506, 455712 — *confirm names, see `documentation/team.md`*
**Status:** 🟢 GREEN — baseline implemented, runs on mock data, 0 contract violations.
No real-data accuracy yet.

## 1. Purpose

Decide whether the driver's eyes are open or closed on each frame, count blinks, and
track how long the eyes have been continuously closed.

Eye behaviour is the strongest single drowsiness cue, and the guide separates it out
precisely because it is *"a major but independently testable drowsiness cue."*

The important distinction this module owns: **a blink is not a closure.** A 120 ms
blink is normal alertness. A 1.8 s closure is a microsleep. If they get conflated,
SG-4 sees an inflated blink rate and loses the PERCLOS signal that actually matters.

## 2. Dependencies

Pure Python and the standard library. **No numpy, no OpenCV, no model.**

That is deliberate: this module runs anywhere, in CI, with no install, which means it
can be tested on every push from week one. Keep it that way unless the CNN comparison
forces otherwise.

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
| `confidence` | [0, 1] | halved when only one eye was usable |

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

## 4. How to run

```bash
python module_sg2/run.py                                  # against mock_face.json
python module_sg2/run.py --dump module_sg2/results/run01.json
python module_sg2/run.py --config module_sg2/configs/experiment_a.yaml
pytest module_sg2/tests -q
```

Config: `configs/default.yaml` — `ear_threshold`, `hysteresis`, `min_blink_s`,
`max_blink_s`, and an optional per-driver baseline normalisation (off by default).

## 5. Test data

- `interfaces/mock/mock_face.json` — 300 frames, 10 s. Contains six short blinks, a
  1.8 s sustained closure, and a 1 s no-face gap. The mock landmarks are built so this
  module's real EAR maths recovers the scripted curve to within 0.00003.
- `tests/test_eye_state.py` — 11 tests: EAR correctness and scale invariance, blink
  vs. closure classification, single-frame jitter rejection, threshold chattering,
  upstream failure, reset between clips.
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
      or is per-subject normalisation needed? (Lab 5)
- [ ] Failure analysis: glasses, reflections, squinting, side lighting (Lab 7)
