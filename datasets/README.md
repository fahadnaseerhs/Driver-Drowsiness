# Datasets

> **Nothing in `raw/`, `processed/` or `clips/` is ever committed.** The guide is
> explicit: *"Do not commit large raw datasets, trained-model caches or environment
> folders unless specifically approved; maintain reproducible download/setup
> instructions instead"* (§3.2). `.gitignore` enforces it.
>
> What *is* committed: manifests, labels, and the scripts that fetch and prepare
> data. Someone cloning this repo should be able to reproduce your dataset from
> what is in here.

## Layout

```
datasets/
  manifests/     committed — which clips, which split, which labels
  scripts/       committed — download and preparation scripts
  samples/       committed — a FEW tiny files for tests only (keep under ~1 MB each)
  raw/           ignored  — downloaded archives as they arrived
  processed/     ignored  — extracted frames, normalised clips
  clips/         ignored  — your own recordings
```

## Candidate public datasets

Shortlisting these is Lab 2 work, and the guide wants 2–3 considered with their
limitations stated. Commonly used in this problem space:

- **NTHU-DDD** (NTHU Driver Drowsiness Detection) — the standard benchmark for
  this task. Includes glasses and night-time scenarios, which is exactly what
  risk R1 is about. Requires a request to the authors.
- **YawDD** (Yawning Detection Dataset) — dashboard-mounted video, with and
  without glasses. Useful for SG-3 specifically.
- **CEW** / **MRL Eye Dataset** — still images of open/closed eyes. Good for
  training or evaluating SG-2's CNN comparison; useless for anything temporal.
- **UTA-RLDD** (Real-Life Drowsiness Dataset) — self-recorded, longer sequences
  with three alertness levels.

**Verify licence and access terms before downloading**, and record them in the
manifest. The licence column in the decision matrix is there for a reason, and
"we used a dataset we were not licensed for" is not a recoverable problem.

## You will still need your own clips

Risk **R1** is the highest-exposure item on the register: *"dataset does not cover
glasses or night lighting"*, mitigated by *"collect a 500-clip in-car supplement at
dusk"*.

Public datasets were recorded with other cameras, other mounting positions and
other lighting. The Face-Off is evaluated under conditions you do not control
(risk R8), so some of your data must come from your own camera in your own rig.

**This has the longest lead time of anything in the project** — it needs people, a
car, a camera and the right time of day. Start it around Lab 3–4, not after the
Lab 6 accuracy numbers disappoint you.

### Recording guidance

- Use the **same camera and mounting position** you will demo with.
- Cover deliberately: with and without glasses, day / dusk / night, different
  people, head turned away, hand over face, direct sun through a side window.
- Keep clips short (20–60 s) and name them systematically.
- **Record the ground truth as you go.** Labelling from memory a week later does
  not work. Note the start and end second of every eye closure and yawn while you
  still remember the take.
- Get consent from everyone recorded, and keep the clips off the repo.

## Manifest format

One JSON file per split in `manifests/`. Everything needed to reproduce the set
without the files themselves:

```json
{
  "name": "dusk_glasses_v1",
  "split": "test",
  "created": "2026-10-15",
  "source": "self-recorded",
  "camera": "Logitech C920, 1280x720 @30, dash-mounted centre",
  "notes": "Dusk, 6 subjects, 3 wearing glasses.",
  "clips": [
    {
      "file": "clips/dusk_glasses_v1/s03_take2.mp4",
      "sha256": "...",
      "duration_s": 42.5,
      "subject": "s03",
      "glasses": true,
      "lighting": "dusk",
      "ground_truth": {
        "eyes_closed_s": [[12.4, 14.1], [28.0, 28.3]],
        "yawn_s": [[19.2, 21.0]],
        "drowsy_episodes_s": [[12.4, 14.1]]
      }
    }
  ]
}
```

`drowsy_episodes_s` is what `evaluation/src/metrics.py` scores against — the
episodes a correct system must alarm on. It is not the same as every eye closure: a
normal blink is a closure and must **not** produce an alarm.

## Splits, and risk R5

Risk **R5** is *"thresholds overfit to the recorded clips"*, mitigated by *"hold-out
set untouched until final validation"*.

Three splits, decided once:

| Split | Used for | Who may look at it |
|---|---|---|
| `train` | fitting models, choosing thresholds | anyone, any time |
| `val` | comparing candidates in Labs 5–6 | anyone, any time |
| `test` | Lab 13 blind validation **only** | nobody until Lab 13 |

**Split by subject, not by clip.** The same person in train and test leaks — their
baseline eye shape is a strong cue, and your numbers will be optimistic in a way
that collapses at the Face-Off.

Write down the date the `test` split was sealed. If someone tunes against it, say
so in the validation report rather than quietly reporting the number.

## Mock data is not a dataset

`interfaces/mock/` is synthetic, geometrically perfect, and has no camera noise,
no glasses, no motion blur and no lighting variation. It is for interface tests
and unit tests.

**No accuracy number that gets graded may come from it.** It will make any method
look excellent, including a bad one.
