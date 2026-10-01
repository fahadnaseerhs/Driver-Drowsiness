# Baseline findings — first run, 2026-10-01

What the scaffolded baseline actually does on the synthetic mock driver, including
the parts that are wrong. Recorded here so nobody rediscovers them in week eight.

Reproduce everything below with:

```bash
python integration/run_pipeline.py --source mock --check-scenario
```

---

## 1. The chain runs end to end, with zero contract violations

| Measure | Value |
|---|---|
| Frames processed | 300 (10 s @ 30 FPS) |
| Contract violations | **0** |
| Module errors | none |
| Peak `drowsy_score` | 0.927 |
| Alarm fired at | 6.20 s (closure began 5.20 s → **1.00 s lag**) |
| False alarms in the first 2 s | 0 |

Per-stage cost on a development PC (Windows, AMD64, CPython 3.12):

| Stage | mean | p95 |
|---|---|---|
| SG-2 eye | 0.012 ms | 0.019 ms |
| SG-3 yawn | 0.006 ms | 0.010 ms |
| SG-4 temporal | 0.063 ms | 0.116 ms |
| SG-5 decision | 0.008 ms | 0.015 ms |
| **end to end** | **0.103 ms** | 0.183 ms |

**Do not quote the implied FPS ceiling from this.** It excludes SG-1 and camera
capture, which will dominate the real budget. SG-1 plus capture is the whole
performance question; these four stages are noise next to it.

---

## 2. Open problem: the alarm never clears

Observed state track:

```
OK      0.00 ->  6.17 s
ALERT   6.20 ->  9.97 s      <-- runs to the end of the clip
```

The scenario has the driver recovering from 9.0 s with eyes open, so the alarm
should have cleared. It does not, and the reason is structural rather than a
threshold being slightly off:

`longest_closure_s` is computed over SG-4's 3-second window, and it reports the
largest value *present in the window*. The 1.8 s closure that ended at 7.0 s stays
inside the window until 10.0 s. While it is there, SG-5's closure term stays
saturated and the score stays above `alert_off`.

So a single long closure holds the alarm on for `window_s` seconds after the
driver's eyes have reopened. On the demo that reads as an alarm you cannot switch
off, which is a worse failure mode than a late alarm.

**Owner: SG-4 with SG-5.** Candidate directions, none yet measured:

- Report `current_closure_s` alongside `longest_closure_s`, and let SG-5 use the
  current value for de-escalation and the longest for escalation.
- Decay the closure term by how long ago the closure ended.
- Shorten `window_s`, which trades this problem against PERCLOS stability.

Pick with evidence on real clips, not by tuning against this synthetic file.

---

## 3. Open problem: WARN is never reached

The run goes straight from OK to ALERT and never passes through WARN, so the
intermediate state is effectively dead code and completely untested on real data.

Two causes, both real:

1. The sustained-closure override in SG-5 jumps straight to ALERT by design,
   skipping WARN entirely. That is correct for an emergency.
2. The score crosses `warn_on` (0.45) and `alert_on` (0.70) within a few frames,
   because 0.60 of the score comes from PERCLOS alone and PERCLOS climbs fast once
   the eyes shut.

**Owner: SG-5.** Decide what WARN is actually *for*. If it should drive a gentler
cue (a chime rather than an alarm), it needs its own evidence path and a score
band wide enough to sit in. If it has no purpose, remove it from the contract
rather than shipping a state that never occurs.

---

## 4. Known quirk: blink rate is under-counted around tracking dropouts

The scenario scripts six short closures, but only **five** blinks are detected.

A blink is reported when the eyes *re-open*. The sixth closure ends at 7.98 s and
the lids finish opening around 8.02 s — inside the 8.0–9.0 s no-face gap — so the
completion is never observed.

This is correct behaviour, not a bug, but it has a consequence worth knowing:
**blink rate is systematically under-reported whenever tracking drops out.** SG-4
should treat `blink_rate_per_min` as a lower bound and read it together with
`confidence` (the observation coverage), not on its own.

This was also a genuine bug in the mock generator, now fixed: it originally
labelled the 1.8 s microsleep as a blink, because it had no duration filter. A
correct SG-2 refuses to, so the reference data disagreed with correct behaviour.
If you change the blink rules in `module_sg2/configs/default.yaml`, change
`MIN_BLINK_S` / `MAX_BLINK_S` in `interfaces/mock/generate_mocks.py` to match, or
CI will fail — deliberately.

---

## 5. Fixed during scaffolding, kept here as a warning

**SG-3 could convert a tracking failure into a yawn.** A landmark stuck wide open
tripped the `max_yawn_s` limit, reset, started counting again, and when the mouth
finally closed it emitted `yawn_event = True`. A camera glitch became fatigue
evidence. Now latched: once flagged implausible, SG-3 stays invalid until the
mouth genuinely closes. Covered by
`test_implausibly_long_opening_is_treated_as_tracking_failure`.

**Eye sides were backwards.** The first draft of `contracts.py` labelled iBUG
indices 36–41 as the *left* eye. In the iBUG/300-W convention they are the
driver's **right** eye, appearing on the left of a non-mirrored image. This is the
classic silent bug in this problem space — it never crashes, it just mislabels
every ROI. Now stated explicitly in `contracts.py` and matched in the mock.

---

## 6. The biggest untested thing

**SG-1 has never run.** OpenCV and MediaPipe are not installed on the machine this
scaffold was built on.

Inside `module_sg1/src/face_landmarks.py` is `FACEMESH_TO_IBUG68`, a 68-entry table
mapping MediaPipe's 468 mesh vertices onto the standard 68-point layout. It is the
widely used community mapping, written from memory, **verified by nobody**.

If one index in that table is wrong, SG-2's EAR and SG-3's MAR are quietly wrong
on every frame and nothing crashes to tell you. The tests check the table has 68
unique in-range entries — which catches a typo, not a misplacement.

Verify it before Lab 4:

```bash
python module_sg1/run.py --source 0 --verify-landmarks
```

Check with your own eyes that 36 and 39 sit on the corners of your **right** eye,
42 and 45 on your left, 48 and 54 on your mouth corners, and 51/57 on the top and
bottom of your lips. Then record in `module_sg1/README.md` that you did, and who.
