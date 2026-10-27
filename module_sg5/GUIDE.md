# SG-5 Guide — Decision & Alert

A guide for someone who has **never touched this project**: a new team member, or an
examiner who wants to reproduce the results. It explains what the project and SG-5 are,
how to set up from zero, what every command does and what you'll see, where every result
lives and how to read it, and what to do when something looks wrong.

Words like EAR, PERCLOS or hysteresis are explained in the [glossary](#12-glossary) at the
end.

| If you want… | Read |
|---|---|
| Every measured number, in detail | [README.md](README.md) |
| Why these two algorithms were chosen | [ALGORITHM_PLAN.md](ALGORITHM_PLAN.md), [documentation/algorithm_selection.md](../documentation/algorithm_selection.md) |
| What to run and say in the demo | [DEMO.md](DEMO.md) |

---

## 1. The project in one paragraph

A driver drowsiness monitor. A camera watches the driver; the system reads the eyes and
mouth, decides whether the driver is getting drowsy, and sounds an alarm. The final target
is an NVIDIA Jetson Orin Nano 8 GB at 720p, 30 fps. Six sub-groups each own one stage, and
the stages talk through a fixed data contract
([interfaces/contracts.py](../interfaces/contracts.py), schema 1.0.1), so no group waits on
another.

```
camera ─► SG-1 face ─► SG-2 eyes ─► SG-3 mouth ─► SG-4 last 3 s ─► SG-5 decision ─► SG-6 alarm
          MediaPipe,   EAR → OPEN/  MAR → yawns   PERCLOS,         OK / WARN /      Jetson,
          68 points    CLOSED                     closures, score  ALERT + reason   buzzer
```

## 2. What SG-5 does

**SG-5 makes the system's one safety decision.** Every frame, SG-4 hands us a summary of
the last three seconds. We turn it into `OK`, `WARN` (getting sleepy) or `ALERT` (danger,
sound the alarm), plus an `evidence` sentence saying why — for example
`"ALERT: score 0.93, PERCLOS 0.88, closure 1.77s"`.

What we read from SG-4 (`TemporalResult`):

| Field | Meaning |
|---|---|
| `drowsy_score` | 0–1, SG-4's weighted summary: 0.60 × PERCLOS term + 0.30 × closure term + 0.10 × yawn term |
| `perclos` | fraction of the last 3 s with the eyes closed |
| `current_closure_s` | how long the eyes have been shut **right now** |
| `longest_closure_s` | longest closure anywhere in the last 3 s |
| `confidence` | how much of the window had a usable face, 0–1 |

What we send out (`DecisionResult`): `state`, `alert` (true only in `ALERT`),
`drowsy_score`, `evidence`, and `latency_ms` (left empty — the pipeline owns the clock, so
SG-6 fills it).

**The idea behind everything in this module:** an alarm that goes off for no reason gets
switched off by the driver, and then it protects nobody (risk R6). So most of SG-5's logic
exists to *not* sound the alarm unless the evidence is real.

---

## 3. The two algorithms (and the backup people confuse with them)

The course asks for a primary method plus an alternative to compare against. Both were
scored on the team's weighted matrix (accuracy and FPS ×3, memory and robustness ×2,
licence ×1).

| | **Algorithm 1 — running** | **Algorithm 2 — comparison** |
|---|---|---|
| Method | Weighted score + hysteresis state machine | Learned scorer: logistic regression, then SVM, then a small MLP |
| How the weights are set | By hand, from reasoning | Fitted to labelled video |
| Matrix score | 54 | **56** |
| Needs training data | No | Yes — labelled in-car clips |
| Cost per frame | 0.008 ms, pure standard library | One dot product |
| Status | **Built, tested, run on a live camera** | **Designed, not built — blocked on labelled data** |

**Why we ship the one that scores lower:** we have no labelled footage. A model trained on
our synthetic data would look excellent and be worthless. The paper score isn't the
deciding factor — the missing data is.

**Why swapping later is cheap:** Algorithm 2 would replace only the *scoring* step. The
five safeguards of Algorithm 1 stay on top, unchanged:

```
SG-4 features ─► [ SCORER ] ─► risk 0..1 ─► [ SAFETY LAYER ] ─► OK / WARN / ALERT
                 rules now                  hysteresis, dwell, latch,
                 logreg later               override, confidence gate
```

Swapping touches one object and zero interface fields.

**The backup is not Algorithm 2.** [configs/experiment_a.yaml](configs/experiment_a.yaml) is
Algorithm 1 with its safeguards switched off — a plain threshold. It's what we compare
Algorithm 1 against *today*, while Algorithm 2 waits for data.

---

## 4. How Algorithm 1 works

Code: [src/decision.py](src/decision.py). Settings: [configs/default.yaml](configs/default.yaml).

Every frame goes through these steps, in this order:

**Step 0 — Is the input usable?** If SG-4's result is invalid (no face), we can't judge.
If an `ALERT` is already sounding, it is **held** through the gap — losing the face must
not silence an alarm. Otherwise we report "no decision" with the reason.

**Step 1 — Emergency override** (`closure_override_s: 1.20`). If the eyes have been shut
*continuously* for 1.2 s or more, go straight to `ALERT` and skip every other step. A closed
eye at speed is an emergency. It reads `current_closure_s`, not `longest_closure_s` — the
window maximum stays high for 3 s after the eyes reopen, and keying on it was a bug (fixed
in `8c9c079`).

**Step 2 — Confidence gate** (`min_confidence: 0.50`). If less than half the window had a
usable face, refuse to escalate. PERCLOS worked out from three good frames is not evidence.

**Step 3 — Hysteresis: pick a target state from the score.** Going up needs a higher score
than coming back down:

```
              go up at    come down below
WARN            0.45           0.35
ALERT           0.70           0.55
```

A score of 0.50 while `OK` makes `WARN` the target (it's above 0.45). A score of 0.40
while already in `WARN` keeps `WARN` (it's still above 0.35) — only below 0.35 does it
drop back to `OK`. The gap stops a score sitting near a line from flickering every frame.

**Step 4 — Dwell timer** (`min_dwell_s: 0.40`). A new target must hold for 0.4 s
(~12 frames) before it's adopted. One noisy frame can't raise an alarm.

**Step 5 — Latch** (`alert_latch_s: 1.50`). Once `ALERT` fires it stays on for at least
1.5 s, so the alarm doesn't stutter off when the eyes flick open for a moment.

**Step 6 — Explain.** Build the `evidence` sentence from the numbers behind the decision.

### A worked example

On the shared mock ([interfaces/mock/mock_temporal.json](../interfaces/mock/mock_temporal.json)),
the eyes close at 5.20 s:

| Time | What happens | State |
|---|---|---|
| 0–5.2 s | Eyes open, score low | `OK` |
| 5.2 s | Eyes close; PERCLOS and score start climbing | `OK` |
| ~5.9 s | Score crosses 0.70 → `ALERT` becomes the candidate | `OK` (dwelling) |
| 6.27 s | Candidate has held 0.4 s → adopted | **`ALERT`**, alarm sounds |
| 6.37 s | Closure passes 1.2 s → override also on | `ALERT` |
| 7.0 s | Eyes reopen; latch keeps it on ≥ 1.5 s | `ALERT` |
| after | Should leave `ALERT` once the score falls under 0.55 — but on this mock **it never does** (see §9) | `ALERT` |

The alarm fires **1.07 s after the eyes closed**. (The ~5.9 s row is inferred from the
0.4 s dwell; the others are measured.)

---

## 5. Setting up from zero

You need Git and Python. The project targets **Python 3.10** to match the Jetson; 3.12
also works on a laptop (it's what the numbers here were measured on).

```bash
git clone https://github.com/fahadnaseerhs/Driver-Drowsiness.git
cd Driver-Drowsiness

python -m venv .venv
.venv\Scripts\activate             # Windows (PowerShell: .venv\Scripts\Activate.ps1)
source .venv/bin/activate          # macOS / Linux -- run only the line for your OS
pip install -r requirements-dev.txt

git fetch origin
git checkout sg5/fusion-rules
git pull origin sg5/fusion-rules
```

`requirements-dev.txt` installs everything in `requirements.txt` plus pytest and ruff.
You'll see `(.venv)` at the start of your prompt when the environment is on. **Turn it on
again in every new terminal** — most "module not found" errors are a forgotten activate.

---

## 6. Your first five minutes

Run these in order. Each one should finish in seconds.

```bash
python module_sg5/run.py
```
Runs Algorithm 1 over the 300-frame, 10-second mock. **You'll see:** frame count, score
range, state counts (`OK: 188, ALERT: 112`), latency, and `contract: OK, 0 violations`.

```bash
python integration/run_pipeline.py --source mock --check-scenario
```
Runs the whole SG-1 → SG-5 chain on synthetic input and **checks** the alarm fired when it
should. **You'll see:** a state track and two `PASS` lines — alarm at 6.20 s during the
closure, and no false alarm in the first 2 s. Exit code 0 = pass, 1 = fail, 2 = couldn't
run. Its alarm time, 6.20 s, differs from `run.py`'s 6.27 s, and both are correct:
`run.py` reads the pre-made SG-4 output in `mock_temporal.json`, while the pipeline runs
the real SG-4 on the mock eye and mouth data, and the two aren't byte-identical.

```bash
python module_sg5/tools/alarm_demo.py
```
Plays the alarm over the stress track. **You'll hear** it alarm twice and clear. `ALERT` is
a fast pulsing 1000 Hz beep; `WARN` is one soft 660 Hz chime when it starts.

```bash
pytest module_sg5/tests -q
```
**You'll see:** 28 dots, all passing (22 decision tests, 6 alarm tests).

If all four work, your setup is good.

---

## 7. Every command

### The module and the system

| Command | What it does |
|---|---|
| `python module_sg5/run.py` | Algorithm 1 over the mock |
| `python module_sg5/run.py --dump module_sg5/results/run01.json` | Same, and saves every `DecisionResult` |
| `python module_sg5/run.py --config module_sg5/configs/experiment_a.yaml` | The backup — all safeguards off. You'll see `WARN: 12` appear and more `ALERT` frames |
| `python integration/run_pipeline.py --source mock --check-scenario` | Whole chain, with a pass/fail check |
| `python integration/run_pipeline.py --source 0 --display` | Whole chain on the live camera, no sound |

### The alarm — `alarm_demo.py`

| Command | What it does |
|---|---|
| `python module_sg5/tools/alarm_demo.py` | Stress track: alarms twice, then clears |
| `python module_sg5/tools/alarm_demo.py --input interfaces/mock/mock_temporal.json` | The shared mock |
| `python module_sg5/tools/alarm_demo.py --source mock` | Through the whole pipeline |
| `python module_sg5/tools/alarm_demo.py --source 0` | **Live camera** |
| `python module_sg5/tools/alarm_demo.py --silent --fast` | Smoke test: no sound, no waiting |

Options you can add:

| Option | What it does |
|---|---|
| `--source 0` | Camera 0. Use `1`, `2`… for others, or a file: `--source clip.mp4` |
| `--display` | Video window with the overlay: face box, landmarks, state, EAR, MAR, PERCLOS |
| `--status-every 0.5` | One status line every 0.5 s instead of a flood |
| `--log PATH.csv` | One row per frame — needed for the graphs |
| `--save-temporal PATH.json` | Saves SG-4's output so the comparison can be replayed over this run |
| `--config PATH.yaml` | Different SG-5 settings (see §8) |
| `--silent` / `--backend auto\|winsound\|bell\|silent` | Sound on or off, and how |
| `--fast` | Don't wait in real time (file/mock input only) |
| `--limit N` | Stop after N frames |

Every run ends with a summary: state changes with their evidence, and a "what to look at"
list that names the likely problem if something looks off.

### The comparison — `ablation.py`

```bash
python module_sg5/tools/ablation.py
```
Runs the decision logic **seven times over identical input**: `full`, `no_hysteresis`,
`no_dwell`, `no_latch`, `no_override`, `no_confidence_gate`, and `rules_only` (the backup).
Nothing in `decision.py` is edited — each variant is `default.yaml` with one number
changed. Writes [results/ablation.md](results/ablation.md),
[results/ablation.json](results/ablation.json), and one PNG per input.

| Option | What it does |
|---|---|
| `--fixture PATH --label NAME` | Add a recorded run (from `--save-temporal`) |
| `--episodes "12.4-14.1,28.0-28.3"` | When you were genuinely drowsy, so false alarms can be counted |
| `--onset S` | When the first real episode starts |
| `--only-fixture` | Report on your recording alone, skip the built-in inputs. Writes `results/ablation_<label>.md` / `.json` / `.png` and leaves the committed `ablation.*` untouched |
| `--out BASENAME` | Write `<BASENAME>.md`, `.json` and `_<fixture>.png` instead of the committed `ablation.*` |
| `--no-plot` | Skip the PNGs |

A plain `ablation.py` run — and `--fixture` *without* `--only-fixture` — rewrites the
committed `results/ablation.md`, `.json` and PNGs. That's how the committed report is made;
with `--fixture` it simply gets your recording appended.

```bash
python module_sg5/fixtures/stress_track.py
```
Regenerates the 975-frame stress input ([fixtures/stress_track.json](fixtures/stress_track.json)).

### The recovery check — `recovery_check.py`

```bash
python module_sg5/tools/recovery_check.py
```
Asks: **does the alarm switch off after the eyes reopen?** It **exits with code 1 and
prints `VERDICT: FAIL` — that is expected, not a broken install.** The alarm currently takes
3.9 s to clear against a 1.5 s latch; it's a known upstream problem (§9). Writes
[results/recovery_check.json](results/recovery_check.json).

### Graphs — `plot_run.py`

```bash
python module_sg5/tools/plot_run.py --log module_sg5/results/live_01.csv
python module_sg5/tools/plot_run.py --log module_sg5/results/live_01.csv --from 67 --to 90
```
Draws a `--log` file as a PNG next to it (or `--out PATH`). `--from/--to` zooms; they take
seconds from the start or the raw timestamps in the log. It also prints an analysis: each
`ALERT` episode, what raised it, and how long it lasted after the eyes reopened.

### Collecting data that can be scored

```bash
python datasets/scripts/record_clip.py --list-devices
python datasets/scripts/record_clip.py --name s01_awake_day_01 --seconds 30
python datasets/scripts/make_manifest.py --clip datasets/clips/s01_awake_day_01.mp4 \
    --name s01_awake_day_01 --split train --subject s01 \
    --closed "12.4-14.1" --yawn "19.2-21.0" --drowsy "12.4-14.1"
python evaluation/run_eval.py --manifest datasets/manifests/s01_awake_day_01.json \
    --out module_sg5/results/s01_eval.json
```
Record a clip, write down when the eyes closed, yawned and when the driver was really
drowsy, then score the system against it. Clips stay off GitHub (`datasets/clips/` is
gitignored); only the manifest is committed. See [datasets/README.md](../datasets/README.md).

### Checks before you push

```bash
ruff check .
pytest -q
```
Should print `All checks passed!` and 119 tests passing (one is skipped).

---

## 8. Running with the live camera

```bash
python module_sg5/tools/alarm_demo.py --source 0 --display
```

Press **`q`** in the video window (or Ctrl-C) to stop. The summary and saved files are
still written. Not sure which number your camera is?
`python datasets/scripts/record_clip.py --list-devices`.

A full recording session, then the graph, then the comparison over that run:

```bash
python module_sg5/tools/alarm_demo.py --source 0 --display --status-every 0.5 \
       --log module_sg5/results/live_02.csv \
       --save-temporal module_sg5/results/track_live_02.json

python module_sg5/tools/plot_run.py --log module_sg5/results/live_02.csv

python module_sg5/tools/ablation.py --only-fixture --fixture module_sg5/results/track_live_02.json --label live_02
```

The last command writes `results/ablation_live_02.md`, `.json` and `.png`, so the committed
comparison isn't touched.

**Why record first and compare afterwards?** You can't do a live run seven times — you
blink differently every take, so each configuration would see different input and the
comparison would mean nothing. Record once with `--save-temporal`, then replay all seven
over the same recording. Without `--episodes`, false alarms and episode lag read **`n/a`**,
not `0` — "we didn't count" and "we counted none" are different claims.

### Turning parameters on and off

All five safeguards live in [configs/default.yaml](configs/default.yaml). **Don't edit the
default** — copy it, change the copy, and pass it with `--config`:

```bash
copy module_sg5\configs\default.yaml module_sg5\configs\my_test.yaml     # Windows
cp module_sg5/configs/default.yaml module_sg5/configs/my_test.yaml       # macOS / Linux

python module_sg5/tools/alarm_demo.py --source 0 --display --config module_sg5/configs/my_test.yaml
```

| Safeguard | Default | To switch it **off** | What happens when it's off |
|---|---|---|---|
| Hysteresis | `warn_off: 0.35`, `alert_off: 0.55` | set `warn_off` = `warn_on` (0.45) and `alert_off` = `alert_on` (0.70) | State flickers when the score sits near a line |
| Dwell timer | `min_dwell_s: 0.40` | `0.0` | One noisy frame can raise an alarm |
| Latch | `alert_latch_s: 1.50` | `0.0` | The alarm stutters off when the eyes flick open |
| Override | `closure_override_s: 1.20` | a huge value, e.g. `999` | Long eye closures may never alarm |
| Confidence gate | `min_confidence: 0.50` | `0.0` | Alarms raised from almost no face data |

To make it **more** or **less** sensitive, move the thresholds: lower `warn_on` /
`alert_on` to alarm earlier, raise them to alarm later. Each "off" value must be at or below
its "on" value — the module refuses to start otherwise.

---

## 9. Where the results live, and how to read them

Everything is in `module_sg5/results/` and committed, so it can be shown without
re-running anything.

| File | What it is |
|---|---|
| [ablation.md](results/ablation.md) / [ablation.json](results/ablation.json) | The seven-configuration comparison |
| [ablation_stress_track.png](results/ablation_stress_track.png) | All seven configurations drawn side by side on the stress input |
| [ablation_mock_temporal.png](results/ablation_mock_temporal.png) | The same on the shared mock |
| [recovery_check.json](results/recovery_check.json) | The alarm-clearing verdict (currently FAIL) |
| [live_01.csv](results/live_01.csv) | First live camera run, one row per frame |
| [live_01.png](results/live_01.png) | The whole 177 s run, four panels |
| [live_01_episode4.png](results/live_01_episode4.png) | Zoom on the worst episode, 67–90 s |
| [live_01_findings.md](results/live_01_findings.md) | What the live run showed, written up |

Elsewhere: the engineered test input [fixtures/stress_track.json](fixtures/stress_track.json),
the settings in [configs/](configs/), evaluation output in
[evaluation/reports/](../evaluation/reports/), and labels in
[datasets/manifests/](../datasets/manifests/).

### Reading the live-run graph

Example: [results/live_01.png](results/live_01.png). Four panels share one time axis. Grey
shading on every panel marks where SG-2 said the eyes were **closed**.

| Panel | What's plotted | How to read it |
|---|---|---|
| **1. EAR** | Eye Aspect Ratio (blue), SG-2's threshold 0.21 (dashed), its band 0.19–0.23 | EAR drops when the eyes close. A dip below the band is a real closure. Hovering *inside* the band means a half-open eye, not a shut one |
| **2. Closure** | `current_closure_s` (green), `longest_closure_s` (brown dotted), override line at 1.20 s (red) | When green crosses red, the override fires. Green drops to 0 the moment the eyes open; brown stays high for 3 s — the window's memory |
| **3. Score** | `drowsy_score` (red), PERCLOS (purple), confidence (grey dotted), four threshold lines | Orange lines are WARN on/off (0.45/0.35), red lines ALERT on/off (0.70/0.55). The score goes up when it crosses a dashed "on" line and comes down when it falls under a dash-dot "off" line |
| **4. State** | Green `OK`, orange `WARN`, red `ALERT` | The decision SG-5 actually made. Line it up with panels 1–3 to see why |

**Reading one alarm:** find a red block in panel 4 and look straight up. Is there grey
shading (eyes closed)? Did the green line cross 1.20 s (override) or the red score cross
0.70 (score)? Then find where the grey ends — the eyes reopened — and see how long the red
block keeps going after it. That gap is the stuck alarm.

### Reading the comparison graph

[results/ablation_stress_track.png](results/ablation_stress_track.png): the score on top,
then **one state row per configuration**. Compare each row with `full`. Extra red blocks are
false alarms that safeguard was preventing; a missing red block is a real alarm it was
responsible for. You can see the override's alarm vanish in `no_override` and the dwell
timer's spikes appear in `no_dwell`.

### Reading the comparison table

On the stress input ([results/ablation.md](results/ablation.md)):

| Config | State changes | Alarms | False alarm frames |
|---|:--:|:--:|:--:|
| **full** | **8** | **2** | **0** |
| no_hysteresis | 19 | 2 | 0 |
| no_dwell | 15 | 5 | 75 |
| no_latch | 10 | 3 | 0 |
| no_override | 6 | **1** | 0 |
| no_confidence_gate | 10 | 3 | 120 |
| rules_only (all off) | **30** | **7** | 4 |

- **State changes** — fewer is calmer. Hysteresis off more than doubles them.
- **Alarms** — the full system raises exactly the 2 real ones. More means false alarms crept
  in; fewer (`no_override`: 1) means a real one was missed.
- **False alarm frames** — the dwell timer and confidence gate are the biggest protections.

**The decisive row:** a 2.5 s eye closure with the score held at 0.50 gives **53 `ALERT`
frames with the override and 0 without it** — a plain threshold would never fire. The costs
are reported too: the dwell timer adds 0.43 s of delay, and hysteresis adds 20 extra
`ALERT` frames after an episode ends.

**A negative result we keep on purpose:** on the shared mock, **four of the five safeguards
made no difference** — identical output with them switched off, because that data never
tested them. It's left in `ablation.md`, and it's why the stress input exists.

### What the first live run showed

177 s, 4257 frames, one subject, laptop webcam: 98.7 % face detection, 24 fps (SG-1 takes
~35 ms a frame, nearly the whole budget), 0 contract violations, 9 alarms.

1. **`WARN` really happens.** We had recorded it as unreachable — true of the mock, false of
   a real person: 12 entries, 17.4 % of the run.
2. **The alarm stays on too long.** All 9 alarms kept sounding 2.05–13.36 s after the eyes
   reopened. Commit `8c9c079` fixed the override but not this. The cause is upstream:
   SG-4's closure term stays maxed for a full 3 s window after a long closure, so
   `drowsy_score` sits at exactly 0.90 for 15.5 % of the run and SG-5 has nothing to come
   down from. [Issue #16](https://github.com/fahadnaseerhs/Driver-Drowsiness/issues/16),
   owner SG-4.
3. **SG-2's eye threshold matters.** A quarter of "closed" frames were half-open eyes inside
   the threshold band, and the blink rate peaked at 143/min (people blink 10–20 times a
   minute). That inflates PERCLOS, and so our alarms.

### What these results do *not* show

**There is no accuracy figure** — no recall, no precision, no false alarms per hour. Nobody
recorded when the subject was actually drowsy, so there's nothing to score against. Both
test inputs are synthetic and carry `graded_accuracy: false`. They prove the
**mechanisms behave as designed**, nothing more. Real accuracy needs labelled clips (§7,
"Collecting data that can be scored").

---

## 10. Troubleshooting

| Problem | What's going on |
|---|---|
| `ModuleNotFoundError` | The virtual environment isn't on. Run the activate line from §5 |
| `recovery_check.py` exits 1 / `VERDICT: FAIL` | Expected. It's a regression gate for the stuck alarm (#16), which is still open |
| The alarm stays on after you open your eyes | The known stuck alarm (#16), upstream in SG-4. Not your setup |
| No sound | Off Windows it falls back to the terminal bell; with no audio device it counts silently. Check you didn't pass `--silent` |
| Camera doesn't open | Try `--source 1`, or list cameras with `record_clip.py --list-devices` |
| `ablation.md` / `.json` show as modified after a run | A plain run, or `--fixture` without `--only-fixture`, regenerates them. The behaviour columns come out identical; only the latency columns move by microseconds, so it's noise. Undo with `git checkout -- module_sg5/results/ablation.md module_sg5/results/ablation.json` unless you mean to commit new results. To compare your own recording, use `--only-fixture` (or `--out`), which never touches them |
| `stress_track.json` shows as modified after regenerating | Line endings only, harmless; `git checkout -- module_sg5/fixtures/stress_track.json` |

**If a live run never alarms**, read the diagnostics block at the end, top to bottom — the
first problem is usually the cause:

| You see | It means |
|---|---|
| `face detected: 0/N` | SG-1 found no face — fix lighting or framing. Nothing after it can work |
| no `CLOSED` in eye-state counts | SG-2's EAR threshold doesn't suit this face — the commonest cause |
| many `UNKNOWN` | Eyes unreadable — glasses, head turned, low light |
| longest closure < 1.20 s | Eyes never shut long enough for the override |
| lowest confidence < 0.50 | The confidence gate refused to escalate |

---

## 11. Working with Git

```bash
git checkout sg5/fusion-rules      # our branch -- never work on main
git pull                           # our branch, from GitHub
git merge origin/main              # everyone else's merged work

git status                         # look before you stage
git add module_sg5                 # our module only
git commit -m "SG-5: <what you did>"
git push
```

Rules, because they're graded: never commit on `main`; small, meaningful commits; never
commit another sub-group's files; never commit video. Answer interface questions as a
comment on [issue #14](https://github.com/fahadnaseerhs/Driver-Drowsiness/issues/14), not in
chat.

**Open issues** (milestone *Midterm Stage 1 (Week 8)*):

| Issue | What | Waiting on |
|---|---|---|
| [#16](https://github.com/fahadnaseerhs/Driver-Drowsiness/issues/16) | The stuck alarm | SG-4 |
| [#13](https://github.com/fahadnaseerhs/Driver-Drowsiness/issues/13) | Does `WARN` get its own sound, or leave the contract? | SG-6 |
| [#14](https://github.com/fahadnaseerhs/Driver-Drowsiness/issues/14) | 19 interface questions | everyone |
| [#15](https://github.com/fahadnaseerhs/Driver-Drowsiness/issues/15) | Clean-clone check | everyone |
| [#7](https://github.com/fahadnaseerhs/Driver-Drowsiness/issues/7) | Record and label clips | team |

**On the Jetson** (SG-6 leads): our code is pure standard library and ports with no work.
SG-1 is the speed risk. SG-6 must call `reset()` between clips, or clip 2 starts mid-alarm.
Stage 1 doesn't need the whole system on the Jetson — that's Labs 8, 9 and 11.

---

## 12. Glossary

| Term | Meaning |
|---|---|
| **EAR** | Eye Aspect Ratio — eye height divided by eye width, from the landmarks. Around 0.25–0.30 open, near 0 shut. SG-2 calls the eye closed below about 0.21 |
| **MAR** | Mouth Aspect Ratio — the same idea for the mouth. A high MAR held for a while is a yawn (SG-3) |
| **PERCLOS** | PERcentage of eyelid CLOSure — the fraction of the last 3 s the eyes were closed. The standard drowsiness measure |
| **Closure** | One continuous stretch of closed eyes. A blink is a short closure; a microsleep is a long one |
| **`drowsy_score`** | SG-4's 0–1 blend of PERCLOS, closure length and yawning. Our main input |
| **Sliding window** | The last 3 s, recalculated every frame |
| **Hysteresis** | Using a higher threshold to go up than to come down, so a value near the line can't flicker |
| **Dwell time** | How long a new state must hold before it's accepted (0.4 s) |
| **Latch** | Once `ALERT` fires, it's held for a minimum time (1.5 s) |
| **Override** | The emergency rule: eyes shut ≥ 1.2 s → `ALERT` immediately |
| **Confidence gate** | Refuse to escalate when less than half the window had a usable face |
| **Ablation** | Switching off one part at a time to measure what it contributes |
| **Fixture** | A saved input file used for repeatable tests |
| **Mock** | Synthetic input made up for testing — never used for accuracy figures |
| **Contract** | The fixed data format between stages ([interfaces/contracts.py](../interfaces/contracts.py)) |
