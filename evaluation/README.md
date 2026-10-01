# evaluation/ — system-level measurement

Shared. One implementation of each metric, so every report in the repo is comparable.

"Experimentation & Quantitative Evaluation" is **25%** of each sub-group's mark, and
"System-Level Accuracy & Robustness" is 10% of the overall project mark.

```
evaluation/
  src/metrics.py    episode-level detection metrics
  reports/          committed results, one file per experiment
```

## Episode-level, not frame-level

This is the key decision, and it is worth understanding before you report anything.

**Frame accuracy is misleading for this problem.** Closed-eye frames are rare, so a
detector that always says "awake" scores extremely well per frame and is worthless. A
system can be 97% frame-accurate and miss every single microsleep.

So the primary metrics match **episodes**: did we alarm during each genuine drowsy
episode, and how many alarms did we raise when nothing was happening.

```python
from evaluation.src.metrics import score_events, to_intervals, false_alarms_per_hour

alarms = to_intervals(timestamps, [d.alert for d in decisions])
m = score_events(ground_truth_episodes, alarms, tolerance_s=1.0)
print(m.as_dict())
print(false_alarms_per_hour(m.false_positives, duration_s))
```

A ground-truth episode counts as detected if an alarm overlaps it or starts within
`tolerance_s` after it ends — any temporal method needs a moment to accumulate evidence,
and penalising that would be measuring the wrong thing.

Note that `to_intervals` bridges gaps shorter than `max_gap_s`: an alarm that drops for
one frame and returns is **one** alarm, not two. Counting it as two would wrongly inflate
the false-positive count.

## Report false alarms per hour, always

Precision alone hides the thing that matters. "Precision 0.80" sounds acceptable until it
turns out to mean twelve spurious alarms an hour — at which point a real driver switches
the system off and it detects nothing. That is risk **R6**.

So report both, and put the per-hour figure where people will actually read it.

## What every report must state

| Field | Why |
|---|---|
| dataset + split | and confirmation the hold-out was untouched (risk R5) |
| config files used | committed, so the run is reproducible |
| hardware | a number without the device it came from is not a result |
| power mode (Jetson) | whether `nvpmodel -m 0` was set changes everything |
| git commit | so the run can be reconstructed |

Reporting an FPS figure without saying whether max clocks were set is the most common way
these numbers become unusable to everyone including you.

## The four questions

Every checkpoint answers them (guide §3.5), and reports should be structured around them:

1. What did you try?
2. What did you measure?
3. What did you learn?
4. What engineering decision follows?

The fourth earns the mark. A metrics table with no decision attached is an observation,
not engineering.

## Not from the mock data

`interfaces/mock/` is synthetic and geometrically perfect. **No graded accuracy figure may
come from it.** It is for interface and unit tests only. See `datasets/README.md`.
