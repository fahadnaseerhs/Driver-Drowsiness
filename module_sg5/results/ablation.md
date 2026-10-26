# SG-5 Phase 1 ablation -- what each safety mechanism buys

> ## SYNTHETIC INPUT -- NOT AN ACCURACY RESULT
> Synthetic input. These numbers describe MECHANISM BEHAVIOUR (chattering, spurious alerts, recovery, observation-gap handling) only. No graded accuracy figure may come from them -- see datasets/README.md.
>
> This study measures what *changes* when one mechanism is removed from an otherwise identical run over identical input. That difference is real evidence about the mechanism. The absolute values are properties of a synthetic fixture, not of a driver.
>
> **Both** fixtures below are synthetic, and the stress track is synthetic *by construction* -- it is engineered to provoke each mechanism, which makes it less like a real driver, not more. It demonstrates mechanism behaviour (chattering, spurious alerts, recovery, observation-gap handling). It demonstrates nothing about detection accuracy.

- Baseline config: `module_sg5/configs/default.yaml`
- `graded_accuracy: false`
- Fixtures: `interfaces/mock/mock_temporal.json`, `module_sg5/fixtures/stress_track.json`

Two fixtures, because one was not enough. The shared mock is the honest first thing to try and it left four of five mechanisms inert -- which is itself the finding that motivated the second fixture. The mock section is kept so that motivation stays visible rather than being quietly replaced by a better-looking input.

## Fixture: `interfaces/mock/mock_temporal.json`

The shared reference input every module develops against.

- 300 frames, 9.9667 s (0 frames with `valid=False`)
- Closure onset **t = 5.2 s**; the episode lag is measured from there to the first ALERT frame *inside* a genuine episode. `First ALERT` is the first ALERT frame anywhere, so a configuration whose first alarm is spurious shows the two apart. A NEGATIVE episode lag means the alarm was already ringing when the episode began -- carried in from an earlier spurious alert, not earned.
- Genuine drowsy episodes (s): 5.2-9.9667. An ALERT frame outside them is counted as a false alarm.
- `graded_accuracy: false`. The score here rises monotonically and cleanly: no jitter, no boundary hovering, confidence never below 0.667 against a 0.50 gate, and the clip ends mid-alert. Most mechanisms are never put in charge of a decision, so most rows read `unchanged`. That is a statement about this fixture, not a verdict on the mechanisms -- and it is why the stress track exists.

### Comparison

| Configuration | Transitions | ALERT episodes | First ALERT (s) | First in-episode ALERT (s) | Episode lag (s) | Last clear (s) | OK | WARN | ALERT | False alarms | Mean ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `full` | 1 | 1 | 6.2667 | 6.2667 | 1.0667 | never | 188 | 0 | 112 | 0 | 0.0038 | 0.0044 |
| `no_hysteresis` | 1 | 1 | 6.2667 | 6.2667 | 1.0667 | never | 188 | 0 | 112 | 0 | 0.0036 | 0.0041 |
| `no_dwell` | 2 | 1 | 5.8333 | 5.8333 | 0.6333 | never | 163 | 12 | 125 | 0 | 0.0036 | 0.0040 |
| `no_latch` | 1 | 1 | 6.2667 | 6.2667 | 1.0667 | never | 188 | 0 | 112 | 0 | 0.0036 | 0.0040 |
| `no_override` | 1 | 1 | 6.2667 | 6.2667 | 1.0667 | never | 188 | 0 | 112 | 0 | 0.0037 | 0.0040 |
| `no_confidence_gate` | 1 | 1 | 6.2667 | 6.2667 | 1.0667 | never | 188 | 0 | 112 | 0 | 0.0038 | 0.0060 |
| `rules_only` | 2 | 1 | 5.8333 | 5.8333 | 0.6333 | never | 163 | 12 | 125 | 0 | 0.0036 | 0.0041 |

### What removing each mechanism did

#### Hysteresis (asymmetric thresholds)

A score hovering on a threshold should not flicker the state. With the dead band removed, any chattering shows up as extra transitions.

Versus `full` it **changed nothing measurable on this fixture.**

State transitions unchanged; ALERT episodes unchanged; first ALERT unchanged; first in-episode ALERT unchanged; episode lag unchanged; last clear unchanged; ALERT frames 112 -> 112; false alarms unchanged.

#### Dwell timer (min_dwell_s)

A candidate state must persist before it is adopted, so a single noisy frame cannot raise an alarm. Removing it should let spikes through.

Versus `full` it changed: `transitions`, `first_alert_s`, `alert_lag_s`, `first_episode_alert_s`, `episode_lag_s`, `frames_in_state`.

State transitions 1 -> 2; ALERT episodes unchanged; first ALERT 6.2667 -> 5.8333 s; first in-episode ALERT 6.2667 -> 5.8333 s; episode lag 1.0667 -> 0.6333 s; last clear unchanged; ALERT frames 112 -> 125; false alarms unchanged.

#### Alert latch (alert_latch_s)

Once ALERT fires it holds, so the alarm does not stutter off the moment the eyes flick open -- and survives an observation gap.

Versus `full` it **changed nothing measurable on this fixture.**

State transitions unchanged; ALERT episodes unchanged; first ALERT unchanged; first in-episode ALERT unchanged; episode lag unchanged; last clear unchanged; ALERT frames 112 -> 112; false alarms unchanged.

#### Sustained-closure override (closure_override_s)

Eyes shut past the threshold escalate immediately, bypassing score, dwell and hysteresis. Removing it leaves the alarm to the score alone.

Versus `full` it **changed nothing measurable on this fixture.**

State transitions unchanged; ALERT episodes unchanged; first ALERT unchanged; first in-episode ALERT unchanged; episode lag unchanged; last clear unchanged; ALERT frames 112 -> 112; false alarms unchanged.

#### Confidence gate (min_confidence)

Below the upstream coverage floor the module refuses to escalate, so an alarm is never raised from a PERCLOS computed out of a few frames.

Versus `full` it **changed nothing measurable on this fixture.**

State transitions unchanged; ALERT episodes unchanged; first ALERT unchanged; first in-episode ALERT unchanged; episode lag unchanged; last clear unchanged; ALERT frames 112 -> 112; false alarms unchanged.

#### All brakes off (configs/experiment_a.yaml)

The documented backup: plain thresholds, no hysteresis, no dwell, no latch. The comparison the complexity of the FSM has to justify.

Versus `full` it changed: `transitions`, `first_alert_s`, `alert_lag_s`, `first_episode_alert_s`, `episode_lag_s`, `frames_in_state`.

State transitions 1 -> 2; ALERT episodes unchanged; first ALERT 6.2667 -> 5.8333 s; first in-episode ALERT 6.2667 -> 5.8333 s; episode lag 1.0667 -> 0.6333 s; last clear unchanged; ALERT frames 112 -> 125; false alarms unchanged.

### Mechanisms this fixture does not exercise

The variants `no_hysteresis`, `no_latch`, `no_override`, `no_confidence_gate` changed nothing measurable: identical transitions, episodes, timings, state occupancy and false-alarm counts. So on this input those mechanisms never decided anything, and this fixture is **not** evidence that they work -- only that they are inert here.

## Fixture: `module_sg5/fixtures/stress_track.json`

Built by module_sg5/fixtures/stress_track.py to put each mechanism in a situation where it decides something.

- 975 frames, 32.4667 s (9 frames with `valid=False`)
- Closure onset **t = 14.5 s**; the episode lag is measured from there to the first ALERT frame *inside* a genuine episode. `First ALERT` is the first ALERT frame anywhere, so a configuration whose first alarm is spurious shows the two apart. A NEGATIVE episode lag means the alarm was already ringing when the episode began -- carried in from an earlier spurious alert, not earned.
- Genuine drowsy episodes (s): 14-20, 20-24. An ALERT frame outside them is counted as a false alarm.
- `graded_accuracy: false`. Engineered to provoke, which makes it LESS like a real driver, not more. Every number here is about mechanism behaviour. The two fields set by design rather than derived are stated in the generator's docstring: `drowsy_score` is the fixture's control variable, and `low_coverage` reports a deliberately thin, unfilled window.

### Segments

| Segment | Span (s) | Targets | Genuine episode |
|---|---|---|---|
| `awake_baseline` | 0-4 | nothing -- false-alarm denominator | no |
| `boundary_hover` | 4-10 | hysteresis (warn_off vs warn_on) | no |
| `recover_hover` | 10-11 | nothing -- returns every variant to a settled OK | no |
| `single_frame_spikes` | 11-14 | dwell timer (min_dwell_s) | no |
| `genuine_episode` | 14-20 | alert latch (alert_latch_s), and the score path end to end | yes |
| `override_only` | 20-24 | sustained-closure override (closure_override_s) | yes |
| `recover_override` | 24-25.5 | nothing -- drains the latch and returns every variant to OK | no |
| `low_coverage` | 25.5-29.5 | confidence gate (min_confidence) | no |
| `tail_awake` | 29.5-32.5 | nothing -- makes the final state observable | no |

### Comparison

| Configuration | Transitions | ALERT episodes | First ALERT (s) | First in-episode ALERT (s) | Episode lag (s) | Last clear (s) | OK | WARN | ALERT | False alarms | Mean ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `full` | 8 | 2 | 15.3333 | 15.3333 | 0.8333 | 23.4333 | 575 | 247 | 153 | 0 | 0.0037 | 0.0045 |
| `no_hysteresis` | 19 | 2 | 15.3333 | 15.3333 | 0.8333 | 23.4333 | 671 | 171 | 133 | 0 | 0.0036 | 0.0042 |
| `no_dwell` | 15 | 5 | 11.4 | 14 | -0.5 | 23.1667 | 485 | 263 | 227 | 75 | 0.0036 | 0.0041 |
| `no_latch` | 10 | 3 | 15.3333 | 15.3333 | 0.8333 | 23.4333 | 597 | 247 | 131 | 0 | 0.0036 | 0.0043 |
| `no_override` | 6 | 1 | 15.3333 | 15.3333 | 0.8333 | 18.6667 | 575 | 300 | 100 | 0 | 0.0037 | 0.0042 |
| `no_confidence_gate` | 10 | 3 | 15.3333 | 15.3333 | 0.8333 | 29.9333 | 455 | 247 | 273 | 120 | 0.0036 | 0.0042 |
| `rules_only` | 30 | 7 | 11.4 | 14.9333 | 0.4333 | 23 | 669 | 192 | 114 | 4 | 0.0036 | 0.0042 |

### ALERT frames per segment

Where each configuration raised its alarm. This is the attribution the aggregate table cannot give.

| Configuration | `awake_baseline` | `boundary_hover` | `recover_hover` | `single_frame_spikes` | `genuine_episode` | `override_only` | `recover_override` | `low_coverage` | `tail_awake` |
|---|---|---|---|---|---|---|---|---|---|
| `full` | 0 | 0 | 0 | 0 | 100 | 53 | 0 | 0 | 0 |
| `no_hysteresis` | 0 | 0 | 0 | 0 | 80 | 53 | 0 | 0 | 0 |
| `no_dwell` | 0 | 0 | 0 | 75 | 107 | 45 | 0 | 0 | 0 |
| `no_latch` | 0 | 0 | 0 | 0 | 78 | 53 | 0 | 0 | 0 |
| `no_override` | 0 | 0 | 0 | 0 | 100 | 0 | 0 | 0 | 0 |
| `no_confidence_gate` | 0 | 0 | 0 | 0 | 100 | 53 | 0 | 107 | 13 |
| `rules_only` | 0 | 0 | 0 | 4 | 70 | 40 | 0 | 0 | 0 |

### What removing each mechanism did

#### Hysteresis (asymmetric thresholds)

A score hovering on a threshold should not flicker the state. With the dead band removed, any chattering shows up as extra transitions.

Versus `full` it changed: `transitions`, `frames_in_state`, `alert_frames_by_segment`.

State transitions 8 -> 19; ALERT episodes unchanged; first ALERT unchanged; first in-episode ALERT unchanged; episode lag unchanged; last clear unchanged; ALERT frames 153 -> 133; false alarms unchanged.

By segment: `genuine_episode` 100 -> 80.

#### Dwell timer (min_dwell_s)

A candidate state must persist before it is adopted, so a single noisy frame cannot raise an alarm. Removing it should let spikes through.

Versus `full` it changed: `transitions`, `alert_episodes`, `first_alert_s`, `alert_lag_s`, `first_episode_alert_s`, `episode_lag_s`, `last_alert_cleared_s`, `frames_in_state`, `false_alarm_frames`, `alert_frames_by_segment`.

State transitions 8 -> 15; ALERT episodes 2 -> 5; first ALERT 15.3333 -> 11.4 s; first in-episode ALERT 15.3333 -> 14 s; episode lag 0.8333 -> -0.5 s; last clear 23.4333 -> 23.1667 s; ALERT frames 153 -> 227; false alarms 0 -> 75.

By segment: `single_frame_spikes` 0 -> 75; `genuine_episode` 100 -> 107; `override_only` 53 -> 45.

#### Alert latch (alert_latch_s)

Once ALERT fires it holds, so the alarm does not stutter off the moment the eyes flick open -- and survives an observation gap.

Versus `full` it changed: `transitions`, `alert_episodes`, `frames_in_state`, `alert_frames_by_segment`.

State transitions 8 -> 10; ALERT episodes 2 -> 3; first ALERT unchanged; first in-episode ALERT unchanged; episode lag unchanged; last clear unchanged; ALERT frames 153 -> 131; false alarms unchanged.

By segment: `genuine_episode` 100 -> 78.

#### Sustained-closure override (closure_override_s)

Eyes shut past the threshold escalate immediately, bypassing score, dwell and hysteresis. Removing it leaves the alarm to the score alone.

Versus `full` it changed: `transitions`, `alert_episodes`, `last_alert_cleared_s`, `frames_in_state`, `alert_frames_by_segment`.

State transitions 8 -> 6; ALERT episodes 2 -> 1; first ALERT unchanged; first in-episode ALERT unchanged; episode lag unchanged; last clear 23.4333 -> 18.6667 s; ALERT frames 153 -> 100; false alarms unchanged.

By segment: `override_only` 53 -> 0.

#### Confidence gate (min_confidence)

Below the upstream coverage floor the module refuses to escalate, so an alarm is never raised from a PERCLOS computed out of a few frames.

Versus `full` it changed: `transitions`, `alert_episodes`, `last_alert_cleared_s`, `frames_in_state`, `false_alarm_frames`, `alert_frames_by_segment`.

State transitions 8 -> 10; ALERT episodes 2 -> 3; first ALERT unchanged; first in-episode ALERT unchanged; episode lag unchanged; last clear 23.4333 -> 29.9333 s; ALERT frames 153 -> 273; false alarms 0 -> 120.

By segment: `low_coverage` 0 -> 107; `tail_awake` 0 -> 13.

#### All brakes off (configs/experiment_a.yaml)

The documented backup: plain thresholds, no hysteresis, no dwell, no latch. The comparison the complexity of the FSM has to justify.

Versus `full` it changed: `transitions`, `alert_episodes`, `first_alert_s`, `alert_lag_s`, `first_episode_alert_s`, `episode_lag_s`, `last_alert_cleared_s`, `frames_in_state`, `false_alarm_frames`, `alert_frames_by_segment`.

State transitions 8 -> 30; ALERT episodes 2 -> 7; first ALERT 15.3333 -> 11.4 s; first in-episode ALERT 15.3333 -> 14.9333 s; episode lag 0.8333 -> 0.4333 s; last clear 23.4333 -> 23 s; ALERT frames 153 -> 114; false alarms 0 -> 4.

By segment: `single_frame_spikes` 0 -> 4; `genuine_episode` 100 -> 70; `override_only` 53 -> 40.

### Mechanisms this fixture does not exercise

None. Every mechanism changed at least one behavioural metric on this fixture, which is what it was built for.

## Reading this honestly

Every mechanism changes at least one behavioural metric on at least one fixture, so none of them is dead code on this evidence. That is a claim about behaviour on engineered input, and it is the strongest claim this study can make.

A mechanism's row reading `unchanged` on the mock and changing on the stress track means the mock never asked it to decide anything -- read the stress-track row. A row that changes on both is the stronger result.

Removing a brake is not uniformly bad, and the tables are not arranged to hide that. Two mechanisms cost something measurable:

- **The dwell timer costs latency.** On the mock, `no_dwell` alarms at 5.8333 s instead of 6.2667 s -- 0.4333 s sooner, a real win on a real episode. Its price is on the stress track: 75 ALERT frames across `single_frame_spikes`, four one-frame score spikes turned into alarms on an awake driver (and, because the latch then holds them, one of those alarms is still ringing when the genuine episode starts, which is why its episode lag reads -0.5 s rather than as a head start).
- **Hysteresis costs recovery time.** `no_hysteresis` releases the alarm earlier in `genuine_episode` -- 80 ALERT frames against 100 -- because with `alert_off == alert_on` the alert drops as soon as the score falls under 0.70 instead of waiting for 0.55. Faster recovery is a real benefit. It is bought with 19 state transitions instead of 8, all of them chatter on `boundary_hover`.

Whether 0.4 s of latency is worth four nuisance alarms, or faster recovery is worth a flickering state, is a judgement about risk R6 (false alerts make the driver switch the system off). This table supplies the numbers for that argument; it does not settle it.

What is still owed, and cannot be produced from either file: false alarms per hour on footage of an awake driver (the number this module lives or dies by), drowsy-episode recall, and alert latency on a real onset. Those need the clips of ALGORITHM_PLAN.md Phase 2.

Regenerate: `python module_sg5/fixtures/stress_track.py` then `python module_sg5/tools/ablation.py` (writes `ablation.json` and `ablation.md`).
