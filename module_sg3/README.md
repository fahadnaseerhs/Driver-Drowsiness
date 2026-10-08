# SG-3 — Yawn & Facial-Cue Analysis

**Owners:** NUST 456020, 456910 — *confirm names, see `documentation/team.md`*
**Status:** 🟢 GREEN — baseline implemented, runs on mock data, 0 contract violations.
No real-data accuracy yet.

## 1. Purpose

Detect yawning from mouth geometry, providing fatigue evidence that is **independent
of eye closure**.

That independence is the whole reason this module is separate. Per the guide, it
*"provides evidence independent of eye closure and improves robustness to single-cue
failure"* — when the driver wears reflective glasses and SG-2 degrades, SG-4 still has
something to work with.

**Do not reach into SG-2's output from here.** Correlating the two cues is SG-4's job.
If this module starts depending on eye state, the independence that justifies it
disappears.

## 2. Dependencies

Pure Python and the standard library. No numpy, no OpenCV, no model.

Runs in CI with no install, which is why it is testable from week one. Keep it that
way unless the CNN comparison forces otherwise.

## 3. Input / output interface

```
FaceResult  ->  YawnResult
```

**In** — `FaceResult` from SG-1. Uses `landmarks[48:60]` (outer lip). Ignores `image`.

**Out** — `interfaces.contracts.YawnResult`:

| Field | Units | Meaning |
|---|---|---|
| `mar` | ratio | Mouth Aspect Ratio, or `None` if landmarks are degenerate |
| `yawn_flag` | bool | the mouth is wide open **on this frame** |
| `yawn_event` | bool | `True` on the frame a yawn **completes** |
| `yawn_duration_s` | seconds | length of the opening in progress |
| `confidence` | [0, 1] | inherited from SG-1 |

**MAR definition, frozen for V1** (0-indexed iBUG):

```
MAR = |p51 - p57| / |p48 - p54|
      (upper-lip centre to lower-lip centre, over mouth corner to corner)
```

Normalising by mouth width makes it scale-invariant. Changing this breaks
`interfaces/mock/mock_yawn.json` — raise it with the team first.

**Empty behaviour:** upstream `valid=False`, collapsed mouth landmarks, or an
implausibly long opening returns `YawnResult.empty(...)` with a reason.

## 4. How to run

```bash
python module_sg3/run.py                                  # against mock_face.json
python module_sg3/run.py --dump module_sg3/results/run01.json
pytest module_sg3/tests -q
```

Config: `configs/default.yaml` — `mar_threshold`, `hysteresis`, `min_yawn_s`,
`max_yawn_s`.

## 5. Known weakness — measure it, do not hide it

**MAR cannot distinguish a yawn from talking, singing or laughing.** It only knows the
mouth is open.

Two defences are implemented, and neither fully solves it:

1. `min_yawn_s` (0.80 s) — a yawn is sustained; talking produces brief, repeated
   openings. `test_brief_openings_are_not_yawns` covers this.
2. SG-4 looks at yawn *rate over a window*, so one ambiguous event does not decide
   anything.

Quantify the residual error in Lab 7: record clips of a driver talking and report the
false-positive rate. "We know this limitation and here is how big it is" scores; "we
didn't test conversation" does not.

## 6. Test data

- `interfaces/mock/mock_face.json` — 300 frames, 10 s, one scripted yawn at 2.2–3.4 s.
  Mock landmarks are built so this module's real MAR maths recovers the scripted curve
  to within 0.00012.
- `tests/test_yawn_detect.py` — 10 tests: MAR correctness and scale invariance,
  sustained-vs-brief discrimination, the stuck-landmark latch, upstream failure, reset.
- Real clips: **none yet.** You specifically need *talking* footage, which public yawn
  datasets tend not to include. See `datasets/README.md`.

## 7. Current performance

Measured on `mock_face.json`, 300 frames, Windows AMD64, CPython 3.12:

| Metric | Value |
|---|---|
| Latency, mean | **0.006 ms/frame** — the cheapest module in the pipeline |
| Latency, p95 | 0.010 ms |
| Valid frames | 270 / 300 |
| Yawn events | 1 / 1 scripted ✓ |
| Contract violations | 0 |

| Metric | Target | Measured |
|---|---|---|
| Yawn detection F1 | > 0.85 | — |
| False positives while talking | < 0.1 / min | — |
| Accuracy with a hand over the mouth | documented | — |

## A bug already found and fixed here

The first version converted a **tracking failure into fatigue evidence**. A landmark
stuck wide open tripped the `max_yawn_s` limit, reset, started counting a fresh
opening, and when the mouth finally closed it emitted `yawn_event = True` — a camera
glitch became a yawn.

Now latched: once an opening is flagged implausible, the module stays `valid=False`
until the mouth genuinely closes. Covered by
`test_implausibly_long_opening_is_treated_as_tracking_failure`.

Worth remembering as a pattern: **any sensor failure that can be silently reinterpreted
as a positive detection is a bug**, not a quirk.

## Still owed

- [ ] Real labelled clips, including a driver talking (Lab 4)
- [ ] Baseline accuracy on real data (Lab 4)
- [ ] **MobileNet yawn-classifier comparison** (Labs 5–6) — ties with MAR at 49, so it
      must be measured, not argued
- [ ] `mar_threshold` parameter study across subjects (Lab 5)
- [ ] False-positive rate while talking, laughing, drinking (Lab 7)
- [ ] Consider additional fatigue cues: head nodding (needs SG-1 head pose), blink
      morphology, eye rubbing (Lab 7 stretch)
