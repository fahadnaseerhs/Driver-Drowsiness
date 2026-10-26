# SG-5 — Algorithm Selection, Explanation & Implementation Plan

**Module:** Drowsiness Decision & Alert Logic (the last stage, `TemporalResult → DecisionResult`)
**Owner:** Fahad Naseer (SG-5) · **Branch:** `sg5/fusion-rules`
**Written for:** CS-477 Midterm Project Evaluation — Stage 1, Component **A** (15 marks)
**Code:** [decision.py](src/decision.py) · [default.yaml](configs/default.yaml) · [README](README.md)

---

## 0. The decision, in four lines

| Role | Choice | Why |
|---|---|---|
| **Primary (CV path, shipping now)** | **Weighted evidence score + hysteresis finite-state machine** — asymmetric thresholds, dwell timer, alert latch, sustained-closure override, confidence gate | Deterministic, explainable to an examiner line by line, ~0.008 ms/frame, needs **no training data**, and it is the mitigation for risk **R6** (nuisance alerts make the driver switch the system off) |
| **Alternative / comparison (ML path, Labs 5–6)** | **Learned risk scorer** over SG-4's temporal features: **logistic regression → SVM (RBF) → small MLP**, in that order | Replaces hand-set fusion weights (0.60/0.30/0.10) and hand-set thresholds with values *fitted to labelled clips*; produces a calibrated probability that drops into the same `drowsy_score` slot |
| **Documented backup (degenerate fallback)** | Plain rule-based thresholds, no hysteresis | What we fall back to if the FSM is ever suspected of hiding a bug; also the ablation baseline that proves the FSM earns its complexity |
| **Rejected** | LSTM / 1D-CNN over raw frame cues, end-to-end CNN on frames | Temporal modelling belongs to SG-4 by contract; an end-to-end model would dissolve the module boundary and make the safety decision unexplainable |

**The key architectural idea:** the ML model replaces only the **scoring** step. The
**safety layer** (hysteresis, dwell, latch, override, confidence gate) sits *after* the
score and is **model-agnostic**. So swapping rules → ML changes one object and no
interface field. `DecisionResult` is untouched either way.

```
SG-4 features ──► [ SCORER ]  ──► risk in [0,1] ──► [ SAFETY LAYER ] ──► OK / WARN / ALERT
                   rules  (now)                      hysteresis + dwell
                   logreg (Lab 5)                    + latch + override
                   SVM/MLP (Lab 6)                   + confidence gate
                        ▲                                   ▲
                 this is what we swap              this NEVER changes
```

---

## 1. What Stage 1 actually marks, and what we show for each item

Component A is 15 marks, split as follows. This is the checklist the demo is built around.

| Criterion | Marks | Our evidence |
|---|:--:|---|
| Working prototype: live or from saved inputs, observable correct output | **7** | `python module_sg5/run.py` on `mock_temporal.json`; `python integration/run_pipeline.py --source mock --check-scenario` end-to-end with the overlay; `pytest module_sg5/tests -q` (19 tests) |
| Primary selection + backup/alternative with comparative rationale | **4** | §3 of this file + the scored matrix in [algorithm_selection.md](../documentation/algorithm_selection.md); two configs run side by side (`default.yaml` vs `experiment_a.yaml`) |
| V1 I/O contract, reproducibility, role of the module | **2** | [contracts.py](../interfaces/contracts.py) `TemporalResult → DecisionResult`, schema `1.0.1`; pinned [requirements.txt](../requirements.txt); README §3 |
| Preliminary testing/results, known limitations, failure cases | **2** | JSON dumps in [results/](results/) + README §7 (`WARN` unreachable) and §9 (latency, 0 false alarms, 2 transitions) |

Two notes that matter for marks:

* "A working prototype may run on a development PC at this stage" — so the demo is on
  the laptop, and the Jetson is Component C (SG-6 leads).
* "Mock upstream inputs are acceptable when a neighbouring module is unavailable" — our
  `interfaces/mock/mock_temporal.json` path is explicitly allowed. **But** no graded
  *accuracy* number may come from it (see [datasets/README.md](../datasets/README.md));
  the mock proves the methodology, not the numbers.

---

## 2. Where SG-5 sits

```
CAMERA ─► SG-1 face+68 landmarks ─┬─► SG-2 EAR / eye state ─┐
                                  └─► SG-3 MAR / yawn ──────┴─► SG-4 PERCLOS window ─► SG-5 DECISION ─► SG-6 alert
```

SG-5 owns the system's **only safety-relevant output**, and therefore owns **risk R6**.
Half this module's job — the harder half — is **not** alerting. A system that cries wolf
gets switched off, and a switched-off system detects nothing.

---

## 3. Algorithm selection

### 3.1 Scored candidates

Weights follow the team matrix in [algorithm_selection.md](../documentation/algorithm_selection.md):
accuracy ×3, on-device FPS ×3, memory ×2, robustness ×2, licence ×1. Scores 1–5.
The ML rows are new, added by this plan so the ML arm is *scored* rather than assumed.

| Candidate | Acc ×3 | FPS ×3 | Mem ×2 | Robust ×2 | Lic ×1 | Weighted | Decision |
|---|:--:|:--:|:--:|:--:|:--:|:--:|---|
| Rule-based thresholds (no hysteresis) | 3 | 5 | 5 | 3 | 5 | 49 | Documented backup / ablation floor |
| **Weighted score + hysteresis FSM** | 4 | 5 | 4 | 4 | 5 | **54** | **PRIMARY — implemented** |
| **Logistic regression on SG-4 features** | 4 | 5 | 5 | 4 | 5 | **56** | **ML arm, first model (Lab 5)** |
| SVM (RBF) on SG-4 features | 4 | 4 | 4 | 4 | 5 | 50 | ML arm, second model (Lab 6) |
| Small MLP (≤2 hidden layers) | 4 | 4 | 4 | 4 | 5 | 50 | ML arm, only if the SVM shows the boundary is non-linear |
| LSTM / 1D-CNN on frame-cue history | 5 | 3 | 3 | 5 | 5 | 49 | Rejected for SG-5 — this is SG-4's stretch goal |
| End-to-end CNN, frames → state | 5 | 2 | 2 | 5 | 5 | 44 | Rejected — destroys the module boundary and all explainability |

Logistic regression scores *above* the current primary on paper. That is exactly why it
is the comparison arm and not yet the baseline: **the score assumes labelled data we do
not have yet.** Until the clips exist, a 56 on a table beats nothing in reality. That is
the honest version of the argument, and it is the one to give in the viva.

### 3.2 Why the hysteresis FSM is primary *today*

1. **Zero training data required.** We have no labelled in-car clips yet (risk R1). Any
   model trained on what exists would be fitted to synthetic mock data and would look
   excellent while being worthless.
2. **Overfitting risk is real.** Risk R5: thresholds overfit to the recorded clips. With a
   handful of subjects, an 8-parameter linear model is near the limit of what can be
   fitted honestly; an MLP is not.
3. **Explainability is graded.** The `evidence` string ("`ALERT: score 0.93, PERCLOS 0.88,
   closure 1.77s`") drives both the demo overlay and the failure analysis. A rule engine
   explains itself for free.
4. **Cost.** 0.008 ms/frame, pure standard library, nothing to load into the Jetson's 8 GB
   alongside MediaPipe.
5. It is the documented mitigation for R6 — and R6 is the failure mode that kills the
   product rather than just the score.

### 3.3 Why the ML arm is not optional

"Experimentation & Quantitative Evaluation" is 25% of the sub-group mark, and Stage 1 asks
for "at least one backup/alternative … with comparative rationale/evidence". A comparison
we never ran is worth far less than one we ran and lost. The ML arm also answers a question
the rule engine cannot: **are the fusion weights (0.60 PERCLOS, 0.30 closure, 0.10 yawn)
anywhere near optimal?** Those three numbers came from a planning document, not from data.
Logistic regression gives us the data-fitted version of exactly the same linear form —
which makes it the cleanest possible comparison: *same functional family, hand-set vs
fitted coefficients.*

---

## 4. Explanation of the algorithms

### 4.1 The CV chain feeding us (one paragraph, for the viva)

Classical geometric computer vision, with no learned classifier anywhere before SG-4:

* **SG-1** runs MediaPipe FaceMesh, takes the largest face (the driver) and maps the 468
  mesh points down to the classic 68-point iBUG layout, so downstream code can hard-code
  slices: indices 36–41 = driver's **right** eye, 42–47 = driver's **left** eye, 48–67 =
  mouth.
* **SG-2** computes the **Eye Aspect Ratio**: with the six eye points `p1..p6`,
  `EAR = (‖p2−p6‖ + ‖p3−p5‖) / (2‖p1−p4‖)` — eye height over eye width. It is ~0.3 for an
  open eye and collapses toward 0 as the lid closes, and because it is a *ratio* it is
  invariant to how far the driver sits from the camera. Below a threshold → `CLOSED`; a
  closed run that ends is a blink.
* **SG-3** computes the **Mouth Aspect Ratio** the same way on the mouth points; a
  *sustained* high MAR is a yawn (sustained, because talking also opens the mouth).
* **SG-4** accumulates these over a sliding 3 s window and computes **PERCLOS** — the
  fraction of the window with the eyes closed, the standard automotive fatigue metric —
  plus blink rate, yawn rate, longest closure, current closure and a fused `drowsy_score`.

So by the time SG-5 is called, the computer-vision work has been reduced to roughly eight
numbers describing the last three seconds. **SG-5's problem is no longer vision; it is a
decision under uncertainty with asymmetric costs.**

### 4.2 Primary algorithm — weighted score + hysteresis FSM

#### (a) The score

SG-4 builds it as a saturating weighted sum, each term clipped at its reference level:

```
score = clip01( 0.60 · min(1, PERCLOS / 0.40)
              + 0.30 · min(1, longest_closure_s / 1.50)
              + 0.10 · min(1, yawn_events / 1.0) )
```

Saturation matters: a PERCLOS of 0.80 is not "twice as dangerous" as 0.40 — both are
already an emergency — so each term tops out instead of letting one cue dominate the sum
without limit.

#### (b) Hysteresis: two thresholds per boundary, not one

A single threshold makes a score sitting on the boundary flip state every frame — an alarm
that buzzes 15 times a second. So **rising into** a state costs more than **falling out
of** it:

```
            rising (on)   falling (off)
WARN           0.45           0.35
ALERT          0.70           0.55
                              └─ the 0.15 gap IS the hysteresis
```

This is a Schmitt trigger. Formally the target state is a function of *both* the score and
the current state, which is what makes this a finite-state machine rather than a lookup:

```
from ALERT:  score < 0.55 → (score ≥ 0.35 ? WARN : OK)     else stay ALERT
from WARN :  score ≥ 0.70 → ALERT;  score < 0.35 → OK      else stay WARN
from OK   :  score ≥ 0.70 → ALERT;  score ≥ 0.45 → WARN    else stay OK
```

#### (c) Dwell time — `min_dwell_s = 0.40 s`

A *candidate* state must persist 0.4 s (≈12 frames at 30 fps) before it is adopted. One
noisy frame — a landmark glitch, a hand across the face — cannot raise an alarm. Pinned by
`test_single_spike_does_not_raise_an_alert`.

#### (d) Latch — `alert_latch_s = 1.50 s`

Once `ALERT` fires it is held for at least 1.5 s, so the alarm does not stutter off the
instant the driver's eyes flick open. A latched alert is **also held through an observation
gap** (`valid=False` upstream): losing the face mid-alert must not silence the alarm,
because the driver did not become safe when the camera stopped seeing them.

#### (e) Sustained-closure override — `closure_override_s = 1.20 s`

If the eyes are closed *right now* for ≥ 1.2 s → straight to `ALERT`, bypassing the score,
the dwell timer and the hysteresis. Eyes shut for over a second at speed is an emergency,
and a dwell timer on an emergency is the wrong kind of caution.

This keys on `current_closure_s`, **not** `longest_closure_s` — the fix for the stuck-alarm
bug (commit `8c9c079`). `longest_closure_s` keeps reporting a 1.8 s closure for a whole
window *after the eyes have reopened*, which held `ALERT` ~3 s into recovery: on a demo
that reads as an alarm you cannot switch off, which is a worse failure than a late alarm.
`current_closure_s` drops to 0 the instant the eyes reopen, so the override releases and
normal hysteresis takes over.

#### (f) Confidence gate — `min_confidence = 0.50`

SG-4's `confidence` is **observation coverage** (what fraction of the window was usable).
Below 0.50 the module refuses to *escalate* at all — it may decay toward `OK` but never
jump up. In plain terms: do not raise an alarm from a PERCLOS computed out of three usable
frames.

#### (g) Worked example (from the mock run)

```
t=0.00–5.20  eyes open, score ≈0.05           OK
t=5.20       eyes close
t=5.60       score 0.47 ≥ warn_on 0.45        candidate WARN, dwell timer starts
t=6.00       score 0.72 ≥ alert_on 0.70       candidate ALERT
t=6.20       current_closure 1.20 s ≥ 1.20    OVERRIDE → ALERT, immediate, latch starts
...                                            alert held; the evidence string says why
```

Alarm at 6.20 s for a closure that began at 5.20 s → **1.00 s lag**, 0 false alarms in the
awake opening, 2 state transitions over 10 s (no chattering). Those are the numbers in
README §9 — and they are synthetic, which is stated every time they are quoted.

#### (h) Known limitation, to raise before anyone asks

`WARN` is never reached on the mock run: the override jumps straight to `ALERT`, and the
score crosses 0.45 and 0.70 within a few frames because 0.60 of it is PERCLOS, which climbs
fast once the eyes shut. An unreachable state is dead code. **We decide its purpose in
Phase 0 below** — either it drives a gentler cue (a chime, with its own evidence path and a
band wide enough to sit in) or it leaves the contract. Shipping a state that never occurs is
the one answer that is not defensible.

### 4.3 The ML arm — a learned risk scorer

#### (a) Features

One feature vector per frame, taken straight from `TemporalResult` — no new upstream work
required, which is why this arm is cheap to add:

```
x = [ perclos,              # [0,1]  fraction of window with eyes closed
      longest_closure_s,    # s      longest closure in the window
      current_closure_s,    # s      closure in progress (0 if eyes open)
      blink_rate_per_min,   # /min
      yawn_rate_per_min,    # /min
      avg_ear,              # dimensionless (imputed to the train mean when None)
      window_s,             # s      how much window actually existed
      confidence ]          # [0,1]  observation coverage
```

Standardised with train-split statistics: `z = (x − μ) / σ`. This matters —
`blink_rate_per_min` lives on 0–30 and `perclos` on 0–1, and an unscaled SVM or a
regularised linear model would be dominated by the larger-magnitude feature.

#### (b) Labels

A window is labelled `drowsy = 1` if its timestamp falls inside a ground-truth
`drowsy_episodes_s` interval in the clip's manifest, else `0`. The manifest format already
exists in [datasets/README.md](../datasets/README.md). Crucially, **a blink is a closure but
not a drowsy episode** — the label file already draws that distinction, which is the whole
reason labelled data can beat a hand-set threshold here.

#### (c) Logistic regression — the model, and why it goes first

```
p(drowsy | x) = σ(wᵀz + b),        σ(u) = 1 / (1 + e^(−u))
```

Fitted by minimising class-weighted binary cross-entropy with L2 regularisation:

```
L(w,b) = − Σᵢ c_{yᵢ} [ yᵢ log pᵢ + (1 − yᵢ) log(1 − pᵢ) ] + λ‖w‖²
```

Four properties make it the right first model here:

1. **It is the same functional form as the current baseline** — a weighted sum passed
   through a monotone squash. So the comparison isolates exactly one variable: *weights
   chosen by hand vs weights fitted to data.* Any difference in the result is attributable,
   which is what makes it evidence rather than a horse race.
2. **The output is a calibrated probability in [0,1]**, so it drops straight into the
   `drowsy_score` slot and every downstream threshold keeps its meaning. `p = 0.7` means
   "70% of windows that looked like this were drowsy", which is a far better thing to put a
   threshold on than an arbitrary weighted sum.
3. **The coefficients are readable.** `w` *is* the learned version of SG-4's 0.60/0.30/0.10,
   so we can report "the data wants PERCLOS weighted less and current closure more than we
   assumed" — a presentable finding either way.
4. **Class weighting handles the imbalance.** Drowsy windows will be a small minority of
   frames; unweighted training would learn "always awake", score 97% frame accuracy and
   catch nothing. `c_y ∝ 1/frequency` fixes that, and we report **episode-level recall and
   false alarms per hour**, never frame accuracy.

#### (d) SVM (RBF) and the small MLP

Run only *after* logistic regression, and only to answer one question: **is the decision
boundary non-linear?**

* **SVM with an RBF kernel** maps each point implicitly into a high-dimensional space via
  `K(x, x′) = exp(−γ‖x − x′‖²)` and finds the maximum-margin separator there. It can express
  interaction effects — "a long closure matters more when the blink rate is already low" —
  that a linear model cannot. Costs: it needs `probability=True` (internal Platt scaling) to
  yield a usable score, inference is O(#support vectors) rather than one dot product, and
  the margin tells you nothing readable about which cue mattered.
* **Small MLP** (one or two hidden layers, ≤16 units, ReLU, sigmoid output) is the next step
  up in capacity. With ~6–10 subjects of data this is at serious overfitting risk, so it is
  gated: implement it only if the SVM clearly beats logistic regression on subject-held-out
  validation. If logreg ≈ SVM, that is itself the result — **report it and stop.** "We showed
  the extra capacity bought nothing" is a finding, not a failure.

#### (e) Deployment trick — train with scikit-learn, ship pure Python

`scikit-learn` stays a **dev-time dependency only**. After training we export `μ`, `σ`, `w`,
`b` to a YAML file, and inference on the Jetson is a dot product and one `exp` from the
standard library:

```python
z = [(x[i] - mu[i]) / sd[i] for i in range(len(x))]
p = 1.0 / (1.0 + math.exp(-(sum(w[i] * z[i] for i in range(len(z))) + b)))
```

This keeps SG-5 dependency-free in CI and on the target, leaves the Jetson's 8 GB for
MediaPipe, and makes the model **auditable** — the shipped coefficients are plain text in
git. (The SVM/MLP cannot be exported this cheaply; if either wins, `scikit-learn` goes into
`requirements.txt` and `requirements-jetson.txt`, and SG-6 must be told at Lab 9, not Lab
11. That cost is part of the comparison.)

#### (f) What does *not* change

The safety layer. Hysteresis, dwell, latch, override and the confidence gate stay on top of
the learned score, because they encode a cost asymmetry no classifier knows about: a model
trained on cross-entropy treats a false alarm and a miss as equally bad, and for us they
are not. **The sustained-closure override in particular is never delegated to a model** —
eyes shut for 1.2 s is an emergency as a matter of policy, not of probability.

---

## 5. Implementation plan

Phases are ordered so that **everything Stage 1 needs lands in Phases 0–1**, and the ML arm
(Phases 2–4) accrues credit after the midterm without putting the demo at risk.

### Phase 0 — Clear the AMBER flags (before the demo)

| # | Task | Output | Done when |
|---|---|---|---|
| 0.1 | Decide `WARN`'s purpose with the team: gentler cue, or remove it from the enum | Decision in README §7 + a line in [interface_change_policy.md](../documentation/interface_change_policy.md) | Either `WARN` is reachable on a test clip, or it is gone from `DrowsinessState` with a schema bump |
| 0.2 | If `WARN` stays: widen its band (`warn_on` 0.45 → ~0.35, `alert_on` 0.70 → ~0.75) and give it its own evidence path | `configs/default.yaml`, `_explain()` | A clip shows `OK → WARN → ALERT` in order |
| 0.3 | Confirm the stuck-alarm fix end to end with SG-4 | `results/recovery_check.json` | The alarm clears within `alert_latch_s` of the eyes reopening |
| 0.4 | Check every `reset()` call site — state must not leak between clips | new test in `tests/test_decision.py` | A second clip starts in `OK` |

### Phase 1 — The two-config comparison Stage 1 asks for

| # | Task | Output |
|---|---|---|
| 1.1 | `configs/experiment_a.yaml` — the **no-hysteresis, no-dwell, no-latch** rule-based variant (the documented backup: single thresholds) | config file |
| 1.2 | `results/ablation.md` — run both configs over the same input; report state-transition count, false alarms, alert latency | results file |
| 1.3 | Ablation sweep: remove hysteresis, then dwell, then latch, one at a time | table in `ablation.md` |
| 1.4 | Record the known failure cases: `WARN` unreachable, recovery lag, low-coverage behaviour | README §7 |

> 1.3 is the single most persuasive artefact this module can produce. "Removing the latch
> turned 2 state transitions into 31" is a concrete, measured defence of every line of
> complexity in the FSM, and it answers the examiner's obvious question — *why not just a
> threshold?* — with a number instead of an opinion.

### Phase 2 — Data and feature extraction (the real blocker)

| # | Task | Output |
|---|---|---|
| 2.1 | **Record the awake-driver clips.** 20–60 s each, same camera and mount as the demo; with and without glasses; day / dusk / night; several people | `datasets/clips/` (gitignored) |
| 2.2 | Label as you record: start/end second of every closure, yawn and drowsy episode | `datasets/manifests/<name>.json` |
| 2.3 | Seal the `test` split **by subject**, and write down the date | manifest + README note (risk R5) |
| 2.4 | `src/features.py` — dump one CSV row per frame from `TemporalResult` plus the label | `results/features_<manifest>.csv` |

**This phase has the longest lead time in the whole project** — it needs people, a car, a
camera and the right time of day. Nothing in Phases 3–4 can start without it, and no graded
accuracy figure can come from the mock. Start it the week of the midterm, not after the Lab
6 numbers disappoint.

The one number this module lives or dies by is **false alarms per hour on footage of an
awake driver** — and that is the *cheapest* data in the project to collect, because it needs
no drowsy acting, just someone driving normally.

### Phase 3 — The learned scorer

| # | Task | Output |
|---|---|---|
| 3.1 | Add `scikit-learn==1.5.2` to `requirements-dev.txt` **only** (never `requirements.txt`) | dependency |
| 3.2 | `train/train_scorer.py` — load the features CSV, subject-wise `GroupKFold`, class-weighted logistic regression, L2 sweep over λ | script |
| 3.3 | Export `μ, σ, w, b` → `models/logreg_v1.yaml` plus a model card (data, date, CV scores, coefficient table) | committed model + card |
| 3.4 | `src/scorer.py` — `RuleScorer` and `LogRegScorer` behind one `score(temporal) -> float` method; pure-Python inference; graceful fallback to `RuleScorer` if the model file is missing | code |
| 3.5 | `DrowsinessDecider` reads `engine: rules \| logreg` from config; **safety layer untouched** | `src/decision.py`, `configs/default.yaml` |
| 3.6 | Tests: identical safety behaviour under both engines (spike rejection, latch, override, gate) | `tests/test_scorer.py` |
| 3.7 | Re-tune `warn_on` / `alert_on` on the **val** split for the learned score — the old thresholds were calibrated for a different score scale | config |

### Phase 4 — Evaluation and the comparison write-up

| # | Task | Output |
|---|---|---|
| 4.1 | Run `evaluation/run_eval.py` on the val manifest for every engine | `results/<name>_eval.json` |
| 4.2 | Metrics, episode-level only: recall, precision, F1, **false alarms/hour**, mean alert latency, state-transition count | table |
| 4.3 | ROC / precision–recall across a threshold sweep, so the operating point is a *choice* with a visible cost | plot |
| 4.4 | `results/comparison.md`, in the team's required six-part format | results file |
| 4.5 | Update [algorithm_selection.md](../documentation/algorithm_selection.md) with the measured numbers, and say which decisions changed | doc |
| 4.6 | Only if the SVM is warranted: run it, report it, and state the deployment cost honestly | results |

**Targets to beat** (README §9): false alarms/hour < 1, drowsy-episode recall > 0.90, alert
latency from episode onset < 2 s.

### Phase 5 — Demo, viva and Jetson

| # | Task |
|---|---|
| 5.1 | Scripted 5-minute demo: standalone run → pipeline run with overlay → tests → one deliberate failure case, shown and explained |
| 5.2 | Both members able to explain the FSM, the override, the contract and the test results — *either* student may be asked |
| 5.3 | Latency measured on the Jetson with SG-6 (SG-5's own cost is negligible; the budget is spent upstream) |
| 5.4 | Alert modality agreed with SG-6: sound / LED / overlay, and the repeat-alert policy |

### Commands

```bash
python module_sg5/run.py                                            # standalone, mock input
python module_sg5/run.py --config module_sg5/configs/experiment_a.yaml --dump module_sg5/results/exp_a.json
pytest module_sg5/tests -q                                          # 19 tests
python integration/run_pipeline.py --source mock --check-scenario   # end to end
python evaluation/run_eval.py --manifest datasets/manifests/sample_mock.json
```

---

## 6. What to ask the other sub-groups (integration)

Stage 1 says teams "should be able to identify interface blockers, and provide a clear
integration plan". These are the asks, written as questions with a required answer — not
"let's sync sometime". Everything here is a dependency of SG-5's own marks.

### SG-4 — Temporal (our only upstream; highest priority)

1. **Is `current_closure_s` populated on every valid frame?** Our override keys on it. If it
   is ever left at 0 while the eyes are shut, the override silently never fires and the
   module looks broken in the demo. We need one test clip that proves it.
2. **What exactly does `confidence` mean numerically?** We gate escalation at 0.50. If it is
   "fraction of usable frames in the window", our gate is right; if it is an average detector
   confidence, the threshold means something else and must be re-derived.
3. **What `window_s` are you shipping — 2 s, 3 s or 5 s?** It sets the floor on our alert
   latency and changes how long a recovery takes to register. We need the number fixed, or our
   thresholds are tuned against a moving target. (The `window_2s.json` in your results suggests
   this is still open.)
4. **Will you expose the raw features, or keep fusing?** The ML arm wants `perclos`,
   `longest_closure_s`, `current_closure_s`, `blink_rate_per_min`, `yawn_rate_per_min` and
   `avg_ear` — all already in the contract. Confirm they stay, and that **`drowsy_score`'s
   fusion weights will not change silently** between our runs.
5. **Whose clock is `timestamp`?** We measure dwell and latch in seconds off it. Confirm it is
   `time.monotonic()` at capture, passed through unmodified — not re-stamped per stage.
6. **Joint item: does the alarm clear on a *real* clip?** README §7 on both sides. The fix is
   in; we still owe a shared recovery test on footage rather than on the mock.

### SG-2 — Eye state (indirect, but it defines our emergency)

7. **How is `closure_duration_s` reset?** Everything about the 1.2 s override depends on it
   meaning "seconds the eyes have been *continuously* closed, 0.0 when open".
8. **What happens during a tracking gap mid-closure?** If the face is lost for 200 ms with the
   eyes shut, does the counter continue, restart, or go `UNKNOWN`? Restarting would make one
   long microsleep look like two short blinks, and cost us the detection.
9. **What is the EAR threshold, and does it adapt per subject?** A fixed threshold plus glasses
   is the likeliest source of a false `CLOSED` run — i.e. of *our* false alarm.

### SG-3 — Yawn (lowest weight: 0.10 of the score)

10. **`yawn_event` on completion, or `yawn_flag` per frame?** SG-4 counts events in the window;
    we only need the rate to be stable. Confirm that talking does not generate events.

### SG-1 — Face & landmarks

11. **What is the expected `valid=False` rate on real footage?** It drives how often our
    confidence gate engages and how often a latched alert has to survive a gap. An estimate is
    fine; "we don't know yet" is a blocker worth documenting.

### SG-6 — Jetson & integration (our only downstream)

12. **How is the alert actuated — buzzer, LED, screen overlay, or all three?** And is `WARN`
    distinguishable from `ALERT` in the actuation? *This is the question that decides whether
    `WARN` survives in the contract at all* (Phase 0.1) — we cannot resolve it alone.
13. **What is the repeat-alert policy?** If `ALERT` holds for 30 s, does the buzzer sound
    continuously, pulse, or escalate? That is a decision about the driver, not a software
    detail, and it needs a team answer.
14. **Who fills `latency_ms`?** The contract says the pipeline owns the clock and we leave it
    `None`. Confirm SG-6 measures capture→decision end to end, since alert latency is a graded
    KPI and our own contribution to it is ~0.008 ms.
15. **Do you call `reset()` between clips or sessions?** Our dwell, latch and alert counters are
    stateful. A missed reset means clip 2 starts mid-alert.
16. **If the ML arm wins, can `scikit-learn` be installed on JetPack aarch64?** Ask now, at Lab
    9 — not at Lab 11. (Our exported-coefficients design exists precisely so the answer can be
    "no" without costing us the comparison.)

### Team level (group leader)

17. **Who records and labels the clips, and when?** Phase 2 is the critical path for SG-4, SG-5
    and every Lab 5–6 comparison in the project.
18. **Who seals the `test` split, and on what date?** Risk R5. It needs one owner and a written
    date.
19. **Contract freeze:** anything we add or remove (`WARN`, new scorer fields) needs a
    `SCHEMA_VERSION` bump and team agreement. Put it on the agenda of the next logged meeting —
    removing an enum member after the freeze is a breaking change.

---

## 7. Risks this plan carries

| Risk | Impact | What we do about it |
|---|---|---|
| **R1** — no glasses / night coverage in the data | Thresholds and any trained model are tuned for one lighting condition | Phase 2 records dusk and glasses deliberately; report per-condition metrics, not one pooled number |
| **R5** — overfitting to the recorded clips | The numbers collapse at the Face-Off | Subject-wise splits, a sealed `test` set, logistic regression before anything with more capacity |
| **R6** — false alerts, driver disables the system | The product fails even with perfect detection | The entire safety layer; false alarms/hour is the headline metric, not accuracy |
| No real clips by Lab 5 | The whole ML arm stalls | Phases 0–1 are independent of data and carry the Stage 1 marks on their own; the ML arm is additive |
| `WARN` left unresolved | Dead code in the shipped contract, and a question we cannot answer in the viva | Phase 0.1, with SG-6, before the freeze |
| ML wins but cannot deploy | A comparison we cannot use | Export coefficients to YAML; pure-Python inference; no runtime dependency |

---

## 8. One-paragraph answer, if an examiner asks "what algorithm did you use?"

> SG-5 turns SG-4's temporal summary into the system's one safety output. The primary
> algorithm is a weighted evidence score driving a hysteresis finite-state machine: rising
> and falling thresholds 0.15 apart so the state cannot chatter, a 0.4 s dwell timer so no
> single frame can raise an alarm, a 1.5 s latch so the alarm does not stutter off, a
> confidence gate that refuses to escalate on thin observations, and one hard override —
> eyes closed for 1.2 s goes straight to ALERT, because that is an emergency rather than a
> probability. We chose it over a plain threshold rule because nuisance alerts are the
> documented failure mode that makes a driver switch the system off, and over a learned
> classifier because we have no labelled in-car footage yet and a model fitted to synthetic
> data would look excellent and be worthless. The learned version is the comparison arm:
> logistic regression on the same eight temporal features, which is the data-fitted version
> of exactly the same linear form, so it tells us directly whether our hand-set fusion
> weights were any good. The safety layer sits above the scorer and does not change when we
> swap them — it encodes a cost asymmetry between a false alarm and a missed microsleep that
> no cross-entropy loss knows about.
