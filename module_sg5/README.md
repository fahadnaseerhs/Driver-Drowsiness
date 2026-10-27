# SG-5 — Drowsiness Decision & Alert Logic

**Owners:** NUST 472195, 403897, 459305 (three members) — *confirm names, see
[documentation/team.md](../documentation/team.md)*
**Status:** 🟢 **GREEN for the midterm** — the module runs standalone, through the whole
pipeline, and on a live camera with sound; every safety mechanism is measured. Two known
defects are open and **both belong upstream**: §9.1 (stuck alarm, SG-4) and §9.2 (`WARN`
actuation, SG-6).

| | |
|---|---|
| **Conceptual guide — start here** | [GUIDE.md](GUIDE.md) |
| Plan and algorithm selection | [ALGORITHM_PLAN.md](ALGORITHM_PLAN.md) |
| Demo script — what to run and say | [DEMO.md](DEMO.md) |
| Comparison evidence | [results/ablation.md](results/ablation.md) |
| Recovery check | [results/recovery_check.json](results/recovery_check.json) |
| First live run, with graphs | [results/live_01_findings.md](results/live_01_findings.md) |
| Plain-language log | `Driver Drowsiness/Fahad Naseer/SG-5 Midterm Log.md` |

---

## 1. What this module does

The other sub-groups watch the driver's face. SG-1 finds the face, SG-2 watches the eyes,
SG-3 watches the mouth, SG-4 adds it all up over the last three seconds. They hand us
numbers.

**We make the final call: is the driver `OK`, `WARN` (getting sleepy) or `ALERT` (danger)
— and should the alarm sound.** We also say *why*, in a sentence a human can read.

The guide separates this from cue detection so the final decision can be evaluated
independently: *"separates cue detection from the final safety decision and permits
system-level evaluation."*

**This module owns risk R6** — *"false alerts cause the driver to disable the system"*.

> A system that cries wolf gets switched off, and a switched-off system detects nothing.
> **Not alerting is half this module's job**, and the harder half.

---

## 2. Working with the repository (clone, set up, pull and push)

### First time: clone, set up, pull SG-5

**1. Clone the repository** (once per machine):

```bash
git clone https://github.com/fahadnaseerhs/Driver-Drowsiness.git
cd Driver-Drowsiness
```

**2. Set up a virtual environment** (Python 3.10, the Jetson's version) and install:

```bash
python -m venv .venv
.venv\Scripts\activate             # Windows (PowerShell: .venv\Scripts\Activate.ps1)
source .venv/bin/activate          # macOS / Linux -- run only the line for your OS
pip install -r requirements-dev.txt
```

Activate the environment again every time you open a new terminal.

**3. Pull the SG-5 branch:**

```bash
git fetch origin
git checkout sg5/fusion-rules
git pull origin sg5/fusion-rules
```

**4. Check it works:**

```bash
python integration/run_pipeline.py --source mock --check-scenario
pytest module_sg5/tests -q
```

Other sub-groups use the same steps with their own branch in step 3: SG-1
`sg1/landmark-detector`, SG-2 `sg2/eye-threshold`, SG-3 `sg3/yawn-cues`, SG-4
`sg4/temporal-window`, SG-6 `sg6/jetson-integration`.

### Every day after that

**Before you start work**, get everyone else's changes:

```bash
git checkout sg5/fusion-rules      # our sub-group branch -- never work on main
git pull                           # our branch, from GitHub
git merge origin/main              # everyone else's merged work
```

**When you have something working**, publish it:

```bash
git status                         # look at what you changed BEFORE staging
git add module_sg5                 # stage our module only, not other groups' files
git commit -m "SG-5: <what you did, in a few words>"
git push
```

First push of a new branch needs the upstream set once:

```bash
git push -u origin <branch-name>
```

Rules we follow, because they are marked:

- **Never commit on `main`.** Work on `sg5/fusion-rules`, or a short-lived branch off it.
- **Small, meaningful commits.** "Meaningful sub-group commits" is a graded criterion;
  one giant dump the night before is not.
- **Never commit other sub-groups' files.** If `git status` shows `module_sg4/...`, leave
  it alone.
- **Never commit video.** `datasets/clips/` is gitignored. Clips of people stay off the
  repository; the manifest describing them is what gets committed.

---

## 3. The two algorithms

We carry two, as the evaluation requires: a primary we ship, and an alternative we compare
against.

| | **Primary — implemented** | **Alternative — the ML arm** |
|---|---|---|
| Method | Weighted score + hysteresis state machine | Learned risk scorer: logistic regression, then SVM, then a small MLP |
| Nature | Hand-set rules and timers | Coefficients fitted to labelled video |
| Team matrix score | 54 | **56** |
| Training data needed | **None** | Labelled in-car clips |
| Cost | 0.008 ms/frame, pure standard library | One dot product at run time (see below) |
| Status | Shipping, tested, demoed | Designed, **not built — blocked on data** |

### Why we still ship the lower-scoring one

The learned scorer scores *higher* on the team's matrix. We have not adopted it because
**we have no labelled in-car footage**. A model fitted to our synthetic test data would
look excellent and be worthless — and risk R5 (overfitting to the few clips we have) is
real with a handful of subjects.

That is the honest argument, and it is the one to give in the viva: *the paper score is
not the deciding factor; the absence of data is.*

### The design that makes swapping them cheap

The model replaces **only the scoring step**. The safety layer sits above it and is
model-agnostic:

```
SG-4 features ──► [ SCORER ]  ──► risk 0..1 ──► [ SAFETY LAYER ] ──► OK / WARN / ALERT
                   rules (now)                   hysteresis + dwell
                   logreg (later)                + latch + override + confidence gate
                        ▲                               ▲
                 this is what we swap          this NEVER changes
```

Swapping engines touches one object and **zero interface fields**. `DecisionResult` is
identical either way.

---

## 4. Algorithm 1 — weighted score + hysteresis (what runs today)

Five independent brakes on false alarms. Each one is measured in §6.

**1. Asymmetric thresholds (hysteresis).** Going up costs more than coming down, so a
score sitting on a boundary cannot flicker:

```
            rising (on)   falling (off)
WARN           0.45           0.35
ALERT          0.70           0.55
                              └─ the gap IS the hysteresis
```

**2. Dwell time** (`min_dwell_s`, 0.40 s). A candidate state must persist ~12 frames
before it is adopted. One noisy frame cannot raise an alarm.

**3. Latching** (`alert_latch_s`, 1.50 s). Once `ALERT` fires it holds, so the alarm does
not stutter off the moment the eyes flick open. It is **held through an observation gap**
too — losing the face mid-alert must not silence the alarm.

**4. Sustained-closure override** (`closure_override_s`, 1.20 s). If `current_closure_s`
≥ 1.20 s, go straight to `ALERT` — bypassing the score, the dwell timer and everything
else. Eyes shut for over a second at speed is an emergency, and a dwell timer on an
emergency is the wrong kind of caution.

> It keys on the **ongoing** closure, not `longest_closure_s` (the window maximum), which
> stays high for a whole window after the eyes reopen. Fixed in `8c9c079`; pinned by
> `test_the_override_releases_on_reopen_and_the_state_then_leaves_alert`. See §9.1 — this
> fixed the override but **not** the stuck alarm.

**5. Confidence gate** (`min_confidence`, 0.50). Below half observation coverage the
module refuses to escalate at all: do not raise an alarm from a PERCLOS computed out of
three usable frames.

**Config:** [configs/default.yaml](configs/default.yaml). Inconsistent thresholds are
rejected at construction rather than silently misbehaving.

### How to run it

```bash
python module_sg5/run.py                                   # against mock_temporal.json
python module_sg5/run.py --dump module_sg5/results/run01.json
python module_sg5/run.py --config module_sg5/configs/experiment_a.yaml   # the backup rules
python integration/run_pipeline.py --source mock --check-scenario        # end to end
pytest module_sg5/tests -q                                 # 28 tests
python module_sg5/tools/recovery_check.py                  # alarm-clearing gate; exits 1 by design (§9.1)
```

---

## 5. Algorithm 2 — the learned scorer (the comparison arm)

Not yet built. This is what it will be, and why it is the right comparison.

**Features** — eight numbers already in the contract, so no upstream work is needed:
`perclos`, `longest_closure_s`, `current_closure_s`, `blink_rate_per_min`,
`yawn_rate_per_min`, `avg_ear`, `window_s`, `confidence`. Standardised with train-split
statistics.

**Labels** — a window is `drowsy = 1` if its timestamp falls inside a ground-truth
`drowsy_episodes_s` interval in the clip manifest. **A blink is a closure but not a drowsy
episode** — that distinction is the whole reason labelled data can beat a hand-set rule.

**Model** — `p(drowsy) = σ(w·z + b)`, class-weighted cross-entropy, L2 regularised.

Why logistic regression first, and not something fancier:

1. **It is the same shape as our current baseline** — a weighted sum through a squash. So
   the comparison isolates exactly one variable: weights chosen by hand versus weights
   fitted to data. The difference is attributable, which makes it evidence.
2. **It outputs a calibrated probability**, so it drops into the `drowsy_score` slot and
   every threshold keeps its meaning.
3. **The coefficients are readable** — `w` *is* the learned version of SG-4's hand-set
   0.60 / 0.30 / 0.10.
4. **Class weighting handles the imbalance.** Drowsy windows are rare; unweighted training
   learns "always awake", scores 97 % frame accuracy and catches nothing.

SVM (RBF) and a small MLP come after, and only to answer one question: is the boundary
non-linear? If logistic regression ≈ SVM, **that is the result — report it and stop.**

**Deployment trick:** train with scikit-learn as a dev-only dependency, then export
`μ, σ, w, b` to YAML. Inference on the Jetson is a dot product and one `exp` from the
standard library — no runtime dependency, and the shipped model is auditable plain text.

**How to run it:** not yet runnable. The blocking step is labelled clips —
`datasets/scripts/record_clip.py` then `make_manifest.py` (see §8). Full phase plan in
[ALGORITHM_PLAN.md](ALGORITHM_PLAN.md) §5.

---

## 6. The comparison — what each safety brake is worth

```bash
python module_sg5/tools/ablation.py          # -> results/ablation.md, .json and PNGs
python module_sg5/fixtures/stress_track.py   # regenerate the stress fixture
```

Each run writes **one PNG per fixture** — `results/ablation_<fixture>.png` — with the score
on top and one state row per configuration underneath. The tables say *what* changed; the
picture says *where*. You can see the override's red block disappear in the `no_override`
row, and the dwell timer's spikes appear in `no_dwell`.

### Comparing configurations on a real camera run

A live camera **cannot be rerun seven times** — you blink differently every take, so the
configurations would not be seeing the same input and the difference would mean nothing.
So capture the run once, then replay the comparison over the recording:

```bash
# 1. record a real run, saving SG-4's actual output
python module_sg5/tools/alarm_demo.py --source 0 --display --status-every 0.5 \
       --log module_sg5/results/live_02.csv \
       --save-temporal module_sg5/results/track_live_02.json

# 2. compare every configuration over THAT run
python module_sg5/tools/ablation.py --only-fixture --fixture module_sg5/results/track_live_02.json \
       --label live_02
```

`--save-temporal` writes SG-4's per-frame output in the same format as the fixtures, so the
ablation treats your recording as one more input. Ctrl-C and `q` still save it.

If you noted when you were genuinely drowsy, pass it and false alarms become countable:

```bash
python module_sg5/tools/ablation.py --only-fixture --fixture module_sg5/results/track_live_02.json \
       --label live_02 --onset 12.4 --episodes "12.4-14.1,28.0-28.3"
```

Without `--episodes` the input is unlabelled, so false alarms and episode lag read **`n/a`**
rather than `0` — "we did not count" and "we counted none" are different claims. Everything
that compares one configuration against another on identical input is still valid, because
that is what this study actually measures.

`--only-fixture` skips the built-in fixtures, reports on your recording alone, and writes
`results/ablation_<label>.md` / `.json` / `.png`, leaving the committed `ablation.*`
untouched. `--out BASENAME` picks the output name yourself. Without either, the run
regenerates the committed report with your recording appended.

It runs the decider seven times — once whole, once with each mechanism disabled, once
with all of them off (`configs/experiment_a.yaml`, the documented backup) — over **two**
fixtures.

**Start by admitting the first result.** On the shipped mock, **four of the five
mechanisms were inert** — disabling hysteresis, the latch, the override or the confidence
gate gave byte-identical output, because the fixture never exercised them (confidence
never drops below 0.667 against a 0.50 gate; only 12 of 300 frames sit in the WARN band).
That section is kept verbatim in the write-up. It is why the second fixture exists.

`fixtures/stress_track.json` is a 975-frame, contract-clean track with a segment per
mechanism: a boundary-hovering score, isolated one-frame spikes, a genuine episode with an
observation gap, a long closure with the score suppressed, and a low-coverage stretch.

| Config | State changes | ALERT episodes | False alarms |
|---|:--:|:--:|:--:|
| **full** | **8** | **2** | **0** |
| no_hysteresis | 19 | 2 | 0 |
| no_dwell | 15 | 5 | 75 |
| no_latch | 10 | 3 | 0 |
| no_override | 6 | **1** | 0 |
| no_confidence_gate | 10 | 3 | 120 |
| rules_only (all brakes off) | **30** | **7** | 4 |

**The decisive row:** a 2.5 s eye closure with the score held at 0.50 gives **53 ALERT
frames with the override and 0 without it.** No alarm at all for a two-and-a-half-second
closure. That is the answer to *"why not just a threshold?"*

Costs are reported next to benefits, because this is a comparison and not a sales pitch:
the dwell timer costs 0.43 s of latency, and hysteresis costs 20 extra ALERT frames after
an episode ends.

> Both fixtures are synthetic and both outputs carry `graded_accuracy: false`. They
> demonstrate **mechanism behaviour**, never detection accuracy.

---

## 7. The alarm — hearing the decision

```bash
python module_sg5/tools/alarm_demo.py                     # stress track: alarms twice, and clears
python module_sg5/tools/alarm_demo.py --input interfaces/mock/mock_temporal.json
python module_sg5/tools/alarm_demo.py --source mock       # through the whole pipeline
python module_sg5/tools/alarm_demo.py --source 0          # LIVE CAMERA
python module_sg5/tools/alarm_demo.py --silent --fast     # CI smoke test, makes no noise
```

- **`ALERT`** → urgent repeating pulse, 1000 Hz, 180 ms on / 120 ms off. It **pulses
  rather than drones**, because a continuous tone is what a driver reaches over and
  switches off.
- **`WARN`** → one soft 660 Hz chime, on *entry* only.
- Beeping runs on a daemon thread, so it never blocks the decision loop. Measure latency
  with `tools/ablation.py`, never here.
- Falls back to the terminal bell off Windows, and to counting silently with no audio
  device. A missing speaker must not take the pipeline down.

**By the contract SG-6 owns the physical alert** (buzzer, LED, GPIO). This is a *demo
actuator*: it consumes `DecisionResult` exactly as SG-6's hardware will, so it doubles as
a working specification of what they have to build. Nothing in `src/` imports it.

---

## 8. Logging a live run, and seeing the graphs

### Record the numbers

```bash
python module_sg5/tools/alarm_demo.py --source 0 --display --status-every 0.5 \
       --log module_sg5/results/live_01.csv
```

- `--display` — video with the debug overlay: face box, landmarks, state, EAR, MAR,
  PERCLOS, evidence. `q` ends the run.
- `--status-every 0.5` — a rolling one-liner instead of 30 lines a second.
- `--log` — **one CSV row per frame**, written to `module_sg5/results/`. Columns: `ear`,
  `eye_state`, `closure_s`, `perclos`, `longest_closure_s`, `current_closure_s`,
  `confidence`, `drowsy_score`, `state`, `alert`, `evidence`. This is the file that
  answers "why didn't it fire?".

Every run ends with a **diagnostics block** naming the likely cause, in the order the
chain breaks:

| Symptom | What it means |
|---|---|
| `face detected: 0/N` | SG-1 found nothing. Lighting or framing. Nothing downstream can work |
| no `CLOSED` in `eye_state counts` | SG-2's EAR threshold is wrong for this face — the commonest reason a live run never alarms |
| many `UNKNOWN` | Eye ROI unusable: glasses, head pose, low light |
| `longest closure seen` < 1.20 s | Never reached the override |
| `lowest confidence` < 0.50 | The gate refused to escalate |

Ctrl-C and `q` both still print the diagnostics — stopping a live run is not an error.

### Turn the numbers into graphs

```bash
python module_sg5/tools/plot_run.py --log module_sg5/results/live_01.csv
python module_sg5/tools/plot_run.py --log module_sg5/results/live_01.csv --from 67 --to 90
```

**Where the graphs are stored:** next to their log, in `module_sg5/results/`, as PNG.
Committed, so they can be shown without re-running anything.

| File | What it shows |
|---|---|
| [results/live_01.png](results/live_01.png) | The whole 177 s run |
| [results/live_01_episode4.png](results/live_01_episode4.png) | Zoom on the worst episode, 67–90 s |
| [results/live_01.csv](results/live_01.csv) | The raw per-frame log behind both |
| [results/live_01_findings.md](results/live_01_findings.md) | The written-up findings |
| [results/ablation_stress_track.png](results/ablation_stress_track.png) | All seven configurations side by side |
| [results/ablation_mock_temporal.png](results/ablation_mock_temporal.png) | The same on the shared mock |

### Everything, from the camera instead of fixtures

| What | Command |
|---|---|
| Hear it, live | `python module_sg5/tools/alarm_demo.py --source 0` |
| Watch it, live | `python module_sg5/tools/alarm_demo.py --source 0 --display` |
| Log it, live | add `--status-every 0.5 --log module_sg5/results/live_02.csv` |
| Save it for comparison | add `--save-temporal module_sg5/results/track_live_02.json` |
| Graph it afterwards | `python module_sg5/tools/plot_run.py --log module_sg5/results/live_02.csv` |
| Compare configs on it | `python module_sg5/tools/ablation.py --only-fixture --fixture module_sg5/results/track_live_02.json --label live_02` |
| Whole pipeline, live, no sound | `python integration/run_pipeline.py --source 0 --display` |
| A recorded video file instead | swap `--source 0` for `--source path/to/clip.mp4` |

`--source 0` is the first camera; use `1`, `2`… for others, or
`python datasets/scripts/record_clip.py --list-devices` to find out which is which.

Four stacked panels on a shared clock: **EAR** with SG-2's trigger band and closed-eye
shading; **closure duration** against the 1.20 s override line; **PERCLOS and
drowsy_score** against all four thresholds; and the **state track**. `--from/--to` accepts
either seconds-from-start or the raw timestamps printed in the log.

### Collecting data you can score

```bash
python datasets/scripts/record_clip.py --list-devices
python datasets/scripts/record_clip.py --name s01_awake_day_01 --seconds 30
python datasets/scripts/make_manifest.py --clip datasets/clips/s01_awake_day_01.mp4 \
    --name s01_awake_day_01 --split train --subject s01 \
    --closed "12.4-14.1" --yawn "19.2-21.0" --drowsy "12.4-14.1"
python evaluation/run_eval.py --manifest datasets/manifests/s01_awake_day_01.json \
    --out module_sg5/results/s01_awake_day_01_eval.json
```

A live run shows **that** it reacts. Only a labelled recording shows **how often it is
right** — you cannot go back and check a live stream. See [datasets/README.md](../datasets/README.md).

---

## 9. Known defects — both upstream

### 9.1 ⚠ The stuck alarm is only half fixed (issue #16)

`8c9c079` is recorded as fixing it. Measured end to end with `tools/recovery_check.py`
(real SG-4 → real SG-5, shipped configs), **it does not**. The tool exits 1 by design — it
is a regression gate and the verdict is currently a failure.

| Mock | Live run (177 s, real camera) |
|---|---|
| Alarm cleared **3.900 s** after the eyes reopened, against a 1.50 s latch | **All 9 ALERT episodes** outlived their closure, by **2.05 s to 13.36 s**. Alarm sounding for **35.8 %** of the run |

The override half genuinely works: `current_closure_s` drops to 0 on the frame after the
eyes reopen and the override lets go. But the check runs a **counterfactual arm**
reproducing the pre-fix behaviour, and both arms leave `ALERT` at the *identical instant* —
so the override was never what held the alarm on.

**The cause is upstream, in the score.** `module_sg4/src/temporal.py` fuses
`w_closure * min(1, longest_closure_s / closure_ref_s)`. Once that term saturates it stays
saturated for a full `window_s` after the eyes reopen, and PERCLOS stays high over the same
window. On the live run `drowsy_score` sits at **exactly 0.90 for 15.5 % of the run** —
that is `0.60` (PERCLOS maxed) + `0.30` (closure maxed), both at the ceiling at once, so
the score carries no information and cannot fall. After a ≥1.2 s closure ends it takes a
mean of **3.94 s** to drop below `alert_off`.

**No threshold on our side can fix this.** Hysteresis has nothing to de-escalate from. It
needs SG-4 to decay the closure term or shorten the window. **Owner: SG-4 with SG-5.**

### 9.2 ⚠ `WARN` — reachable after all (issue #13)

We recorded `WARN` as unreachable dead code. That was true of the **synthetic mock** and
false of a real person:

| Mock | Live run |
|---|---|
| 12 of 300 frames in the WARN band — exactly one 0.40 s dwell window, so the candidate never survived to be adopted | **12 entries, 739 frames, 17.4 % of the run**, longest stretch 3.48 s |

Measuring also corrected *why*: it is the **dwell timer**, not the override, that kills
`WARN` on the mock — the score reaches `ALERT` at 6.267 s and the override only starts
firing at 6.367 s.

**The question is now purely actuation:** does SG-6 give `WARN` a distinct cue? Our alarm
tool already demonstrates one (a soft chime). If nobody wants it, `WARN` should leave the
contract rather than ship as a state nobody can hear — and that must be settled **before
the interface freeze**, since removing an enum member afterwards is a breaking change.

### 9.3 A finding for SG-2

24 % of all `CLOSED` frames had an EAR inside the 0.19–0.23 hysteresis band — held closed
by the trigger rather than by a shut eye — and the blink rate peaked at **143/min**
(humans blink 10–20 times a minute). PERCLOS and the closure term both derive from these
closures, so **SG-2's calibration propagates straight into our alarms.** Worth testing:
`normalise_by_baseline: true`; this subject's open-eye EAR median is 0.258, not the 0.30
the fixed threshold assumes.

### 9.4 Ours, still open

`src/decision.py` low-confidence branch: both arms of the conditional return
`self._state`, so it freezes the state instead of decaying toward `OK` as the comment
above it claims. A `WARN` held through a long low-coverage stretch never falls back.
One-line change, but it alters safety semantics — **owner's call**, not applied.

---

## 10. GitHub — issues and the board

Project board: **Driver Drowsiness — CV Face-Off**, milestone **Midterm Stage 1 (Week 8)**.

| Issue | What | Waiting on |
|---|---|---|
| [#16](https://github.com/fahadnaseerhs/Driver-Drowsiness/issues/16) | Stuck alarm only half fixed — score stays saturated | **SG-4** |
| [#13](https://github.com/fahadnaseerhs/Driver-Drowsiness/issues/13) | Does `WARN` get its own cue, or leave the contract? | **SG-6** |
| [#14](https://github.com/fahadnaseerhs/Driver-Drowsiness/issues/14) | 19 interface questions, as tick-boxes per sub-group | all |
| [#15](https://github.com/fahadnaseerhs/Driver-Drowsiness/issues/15) | Clean-clone check: dependencies and run instructions | all |
| [#5](https://github.com/fahadnaseerhs/Driver-Drowsiness/issues/5) | SG-5: compare two decision rules | **done — §6** |
| [#7](https://github.com/fahadnaseerhs/Driver-Drowsiness/issues/7) | Record and label live clips | team |

Answer interface questions **in a comment on #14**, not in chat — Component B gives 2 marks
for documented coordination, and a WhatsApp reply is not documentation.

---

## 11. Jetson Orin Nano (Component C, 5 marks — SG-6 leads)

Not our module, but every sub-group is expected to understand the deployment dependency.

What the midterm asks for: the board **boots**, its operating environment and storage are
identified, the core stack is documented (Python, Git, OpenCV; CUDA/PyTorch where needed),
and a **camera connection or tested video-acquisition path** is demonstrated, with
outstanding blockers recorded. A prerecorded-video fallback shows software readiness but
**does not prove live camera integration**.

Where SG-5 stands in that:

- Our decision code is **pure standard library** — it ports with no work at all. We are
  not the deployment risk.
- **SG-1 is.** Measured on a laptop: ~35 ms/frame, a 24 fps ceiling, and it shares 8 GB
  with everything else on the board. The Jetson will be slower.
- If the ML arm ever wins, `scikit-learn` must install on JetPack aarch64 — ask at Lab 9,
  not Lab 11. Our exported-coefficients design exists so the answer can be "no" without
  costing us the comparison.
- `latency_ms` is left `None` on purpose: **the pipeline owns the clock**, so SG-6 fills
  it. Alert latency is a graded KPI.
- SG-6 must call `reset()` between clips — our dwell, latch and alert counters are
  stateful, and a missed reset means clip 2 starts mid-alert.

**Stage 1 does not require the full camera-to-decision system on the Jetson.** Integration
is Lab 8, Jetson module deployment Lab 9, the complete embedded pipeline Lab 11.

---

## 12. Interface contract

```
TemporalResult  ->  DecisionResult
```

**In** — `TemporalResult` from SG-4: `drowsy_score`, `perclos`, `longest_closure_s`,
`current_closure_s`, `confidence` and the supporting fields for the evidence string.

**Out** — [`interfaces.contracts.DecisionResult`](../interfaces/contracts.py):

| Field | Units | Meaning |
|---|---|---|
| `state` | enum | `OK` / `WARN` / `ALERT` |
| `alert` | bool | `True` **if and only if** `state == ALERT` (enforced by `validate`) |
| `drowsy_score` | [0, 1] | the score this decision came from |
| `evidence` | string | human-readable justification, e.g. `"ALERT: score 0.93, PERCLOS 0.88, closure 1.77s"` |
| `latency_ms` | ms | capture→decision, filled in by the pipeline, which owns the clock |

**Empty behaviour:** a decision **always exists**, even when upstream is invalid — there is
always an answer to "should the alarm be sounding". With invalid input we return
`valid=False` with a reason, while holding a latched `ALERT` through the gap.

Schema version `1.0.1`. Changing a field after the Lab 3 freeze requires team agreement and
a version bump — see [documentation/interface_change_policy.md](../documentation/interface_change_policy.md).

---

## 13. Tests and measured performance

**28 tests** (`pytest module_sg5/tests -q`) — 22 on the decision logic, 6 on the alarm.
Deliberately weighted toward **not** alerting: single-spike rejection, boundary chattering,
low-confidence refusal, latch hold, latch expiry, gap survival, override immediacy,
override release on reopen, reset between clips, threshold validation.

On `mock_temporal.json`, 300 frames, Windows AMD64, CPython 3.12:

| Metric | Value |
|---|---|
| Latency, mean | **0.008 ms/frame** |
| Latency, p95 | 0.015 ms |
| Alarm fired at | 6.27 s (closure ran 5.20 → 7.00 s → **1.07 s lag**) |
| False alarms in the awake opening | 0 ✓ |
| State transitions over 10 s | 1 — `OK → ALERT`, and it **never clears**; see §9.1 |
| Contract violations | 0 |

> Re-measured 2026-10-26 on `mock_temporal.json`, so 6.27 s / 1.07 s lag is right for it.
> `run_pipeline.py --source mock` and `recovery_check.py` drive the real SG-4 from
> `mock_eye.json` + `mock_yawn.json` instead, and alarm at **6.20 s / 1.00 s lag**. Both are
> correct: they're different inputs, not a disagreement — see [GUIDE.md](GUIDE.md) §6.
> What *was* wrong was the earlier "2 state transitions (no chattering)": on both inputs
> there is **1** transition, `OK → ALERT`, and the run ends in `ALERT`. That tidy number is
> the never-clearing alarm in disguise.

On the live camera run (177 s, 4257 frames): 98.7 % face detection, **24.0 fps effective**,
0 contract violations, 9 ALERT episodes.

| Metric | Target | Measured |
|---|---|---|
| **False alarms / hour, awake driver** | **< 1** | — |
| Drowsy-episode recall | > 0.90 | — |
| Alert latency from episode onset | < 2 s | 1.07 s (synthetic) |

**No accuracy figure exists yet** — nobody has written down when the subject was genuinely
drowsy, so there is nothing to score against. Use
[evaluation/src/metrics.py](../evaluation/src/metrics.py), which scores **episodes, not
frames**, because frame accuracy flatters a detector that misses every microsleep.

---

## Still owed

- [ ] **#13** — `WARN`'s cue, with SG-6, before the contract freeze
- [ ] **#16** — the stuck alarm, with SG-4
- [ ] **#14** — chase the remaining interface answers
- [ ] Labelled clips → the first real recall and false-alarms-per-hour figures
- [ ] §9.4 — decide on the low-confidence branch
- [ ] Threshold study: how recall and false alarms trade off (Lab 5)
- [ ] **Build the learned scorer** (Labs 5–6) — blocked on the clips
- [ ] Alert modality and repeat-alert policy with SG-6 (Lab 9)
