# SG-5 — Midterm demo run-sheet

**Target:** Stage 1 Component A, 15 marks. **Length:** ~5 minutes of running, then questions.
**Rule from the sheet:** *"The demonstration must clearly show actual module functionality
rather than slides alone"* — so everything below is a command, not a claim.

Plan and rationale: [ALGORITHM_PLAN.md](ALGORITHM_PLAN.md) · module detail: [README.md](README.md)

---

## 0. Before they arrive

```bash
cd "C:\Users\USER\OneDrive\Desktop\Driver Drowniness"
.venv\Scripts\activate
python -m pytest module_sg5/tests -q
```

22 tests, all green. If anything is red, **stop and fix it before the demo** — a failing
test on screen costs more than the feature it covers.

Have these open in tabs, not scrolling for them live:
- `module_sg5/src/decision.py`
- `module_sg5/results/ablation.md`
- `module_sg5/results/recovery_check.json`
- `module_sg5/README.md` §7 and §7b

---

## 1. "What does this module do?" (30 s, no command)

> SG-5 is the last stage. SG-4 hands me a summary of the driver's last three seconds —
> PERCLOS, longest closure, current closure, blink and yawn rates, a fused score and a
> confidence — and I answer the system's one safety-relevant question: OK, WARN or ALERT,
> plus a human-readable reason. My output goes to SG-6's buzzer and to the logs.
>
> Half this module's job is *not* alerting. A system that cries wolf gets switched off,
> and a switched-off system detects nothing.

Point at `interfaces/contracts.py` — `TemporalResult` in, `DecisionResult` out, schema
1.0.1, and `alert` is `True` **if and only if** `state == ALERT`, enforced by `validate()`.

---

## 2. It runs (45 s)

```bash
python module_sg5/run.py
```

Then the whole pipeline, which is the more convincing one:

```bash
python integration/run_pipeline.py --source mock --check-scenario
```

What to say while it runs:

> 300 frames, 10 seconds of synthetic input. Mean decision latency is about 0.007 ms a
> frame — this module is not where the frame budget goes. Zero contract violations. The
> alarm fires at 6.27 s for a closure that began at 5.20 s, so a 1.07 s lag against a
> 2 s target.

**Do not say "0 false alarms, so it works."** The mock has no noise. The next command is
where the evidence is.

---

## 3. The ablation — the centrepiece (2 min)

```bash
python module_sg5/tools/ablation.py
```

Then open `module_sg5/results/ablation.md`.

Lead with the honest part, because it is the strongest thing you have:

> We first ran this on the shipped mock and **four of the five safety mechanisms made no
> difference at all** — removing hysteresis, the latch, the override or the confidence
> gate gave byte-identical output. That is in the write-up. The reason is the fixture:
> confidence never drops below 0.667 and the gate triggers at 0.50, so the gate could
> never fire, and only 12 of 300 frames sit in the WARN band.
>
> So we built a fixture that puts each mechanism in a situation where it decides
> something — a boundary-hovering score, isolated one-frame spikes, a long closure with
> the score suppressed, a low-coverage stretch, and an observation gap mid-alert.

Now the numbers from the stress track (975 frames, 32.5 s, contract-clean):

| Config | Transitions | ALERT episodes | False alarms |
|---|:--:|:--:|:--:|
| **full** | **8** | **2** | **0** |
| no_hysteresis | 19 | 2 | 0 |
| no_dwell | 15 | 5 | 75 |
| no_latch | 10 | 3 | 0 |
| no_override | 6 | **1** | 0 |
| no_confidence_gate | 10 | 3 | 120 |
| rules_only (`experiment_a.yaml`) | **30** | **7** | 4 |

One sentence per mechanism — this is the part to have by heart:

- **Hysteresis** — 8 state transitions become 19, all the extra chatter on the
  boundary-hovering segment where the score alternates 0.47 / 0.43.
- **Dwell timer** — four one-frame spikes become real alarms: 75 false-alarm frames on an
  awake driver, and the first alarm moves from 15.3 s to 11.4 s.
- **Latch** — a 0.3 s observation gap silences the live alarm; the alarm stutters off
  mid-episode and re-fires, 2 episodes become 3.
- **Override** — **the decisive row.** A 2.5 s eye closure with the score held at 0.50
  produces 53 ALERT frames with the override and **zero without it.** No alarm at all for
  a two-and-a-half-second closure.
- **Confidence gate** — a low-coverage stretch (confidence 0.30, score 0.80) produces 120
  false-alarm frames without it.
- **All brakes off** — 30 transitions and 7 alarms, against 8 and 2.

If you only get to say one thing about this module, say the override row. It is the
clearest answer to *"why not just a threshold?"*

Also volunteer the costs, because they asked for comparative rationale, not a sales pitch:

> Two mechanisms cost us something. The dwell timer costs 0.43 s of latency. Hysteresis
> costs recovery time — 20 extra ALERT frames after the episode has ended. Both are
> deliberate trades against nuisance alerts.

---

## 4. A bug we found and have not fixed (1 min)

Volunteer this. The rubric has 2 marks for known limitations and failure cases, and being
the one to raise it is worth more than being asked.

```bash
python module_sg5/tools/recovery_check.py
```

It **exits 1**, by design — it is a regression gate and the verdict is currently a fail.

> Our team records the stuck-alarm bug as fixed in commit `8c9c079`. Measured end to end,
> it is not. The alarm hangs on for **3.9 seconds** after the driver's eyes reopen,
> against a 1.5 s latch.
>
> The fix did work at the override: `current_closure_s` drops to zero on the frame after
> the eyes reopen and the override lets go immediately. This tool also runs a
> counterfactual arm reproducing the pre-fix behaviour, and both arms leave ALERT at the
> *identical* instant — so the override was never what held the alarm on.
>
> The cause is upstream in the score. SG-4 fuses the closure term from
> `longest_closure_s`, which stays saturated for a full window after recovery, so
> `drowsy_score` sits at 0.84–0.90 flat against our de-escalation threshold of 0.55.
> Hysteresis never gets the chance to act, because there is nothing to de-escalate from.
> No threshold change on our side can fix it — it needs SG-4 to decay the closure term or
> shorten the window. It is logged as issue #16 with the measured track.

That answer demonstrates you can measure, you can read another module's code, and you do
not mark your own homework. Say the clearing time comes from appending synthetic
eyes-open frames, because the mock clip ends before the closure leaves the window — it is
flagged `synthetic_tail: true` in the JSON.

---

## 5. The second known limitation: `WARN` never happens (30 s)

> `WARN` is in the contract and never occurs. We thought that was the override skipping
> it; measuring showed the score beats the override by 0.17 s, so that was wrong. The real
> cause is the dwell timer: exactly 12 frames sit in the WARN band, which is exactly one
> 0.4 s dwell window, so the candidate state never survives to be adopted. With
> `min_dwell_s: 0` the same input gives a clean OK → WARN → ALERT.
>
> So widening the band is the wrong knob on its own. And the decision isn't ours alone —
> it depends on whether SG-6 can actuate WARN differently from ALERT. If it can't, WARN
> should leave the contract rather than ship as a state that never occurs. That is issue
> #13, and it has to be settled before the interface freeze.

---

## 6. Algorithm selection, if asked (1 min)

Use the paragraph in [ALGORITHM_PLAN.md](ALGORITHM_PLAN.md) §8. The short form:

> Primary is a weighted score driving a hysteresis state machine. The alternative is a
> learned scorer — logistic regression on the same eight temporal features, which is the
> data-fitted version of exactly the same linear form, so it tells us directly whether
> our hand-set fusion weights are any good. It scores *higher* than our baseline on the
> team's matrix, 56 to 54, and we still haven't adopted it, because we have no labelled
> in-car footage yet and a model fitted to synthetic data would look excellent and be
> worthless. The safety layer sits above the scorer and doesn't change when we swap them.

---

## Questions to expect

| Question | Answer |
|---|---|
| "Why not just a threshold?" | The `rules_only` row: 30 transitions and 7 alarms against 8 and 2, and no alarm at all on the 2.5 s closure the override catches. |
| "Why no machine learning?" | There is — as the comparison arm. It needs labelled clips, and we won't train on the mock. §3.2 of the plan. |
| "Are these numbers real?" | **No, and we say so everywhere.** Both fixtures are synthetic, both outputs carry `graded_accuracy: false`. They demonstrate mechanism behaviour, not detection accuracy. The accuracy numbers need the clips, which are issue #7. |
| "What is your worst failure case?" | The 3.9 s stuck alarm, issue #16. Then `WARN` being unreachable, issue #13. |
| "What happens when the face is lost?" | A latched ALERT is held through the gap — losing the face mid-alert must not silence the alarm. Pinned by a test, and it is the latch row in the ablation. |
| "How do you know the override fix works?" | A unit test that fails if it is reverted, plus the counterfactual arm in `recovery_check.py`. |
| "What's your latency?" | ~0.007 ms mean per decision. Alert latency end to end is SG-6's measurement; the contract leaves `latency_ms` for the pipeline to fill. |

---

## What not to claim

- **Not** "the system works" — you have a module that works on synthetic input.
- **Not** any accuracy, recall or false-alarm-per-hour figure. You have none yet, and the
  project's own `datasets/README.md` forbids taking them from the mock.
- **Not** that the stuck alarm is fixed. It is half fixed and you can prove exactly which
  half.
- **Not** a fully integrated camera-to-decision system on the Jetson. Stage 1 explicitly
  does not require it — integration is Lab 8, Jetson deployment Lab 9, the full embedded
  pipeline Lab 11.

## One-line summary, if they only give you a minute

> It decides OK / WARN / ALERT with five independent brakes on false alarms, I can show
> you in numbers what each brake buys, and I can show you the one bug we have not fixed
> and whose fault it is.
