# integration/ — wiring the five modules into one system

**Owners:** SG-6 + Tech Lead. Changes here need review from an affected sub-group.

```
integration/
  run_pipeline.py        the entry point you demo with, and the CI gate
  src/pipeline.py        chains the modules, enforces the contract between them
  src/overlay.py         the debug overlay (--display)
  tests/                 Lab 8 / Lab 11 gate behaviour, automated
  reports/               saved timing and state reports
```

## Running it

```bash
# Day one. No camera, no models, no SG-1. Replays the mock driver.
python integration/run_pipeline.py --source mock

# Same, plus assert the alarm fires where the scenario says it should.
python integration/run_pipeline.py --source mock --check-scenario

# A recorded clip, through the real SG-1.
python integration/run_pipeline.py --source datasets/samples/clip01.mp4

# Live camera with the overlay -- the demo path.
python integration/run_pipeline.py --source 0 --display

# Save artefacts for a report.
python integration/run_pipeline.py --source mock --dump integration/reports/decisions.json --report integration/reports/timing.json
```

Exit codes make it usable as a gate:

| Code | Meaning |
|---|---|
| 0 | ran clean, no contract violations, scenario check passed |
| 1 | contract violations, or a missed alarm, or a false alarm |
| 2 | could not run at all |

## Integration is progressive, not a final-week event

That is the whole design. Three ways to run means a pair can integrate on day one:

1. `--source mock` needs nothing installed beyond the standard library.
2. A recorded clip brings in real SG-1 output.
3. A live camera is the demo.

## Degraded operation is deliberate

Any stage may be `None`, and any stage may throw. The pipeline records it in
`PipelineStats.module_errors` and **keeps going** with that module's empty payload.

This is the mitigation for risk **R4** — *"one pair falls behind and blocks
integration"* — made mechanical: *"mock I/O mandatory from day one, nobody waits."*

Two tests pin it: `test_pipeline_runs_with_sg3_missing` and
`test_a_module_that_raises_is_contained_and_counted`.

A module that silently fails is still a problem. The point is that it is **your**
problem, visible in the report, rather than everybody's problem via a crash.

## What the pipeline owns, and what it does not

**Owns: the clock.** `latency_ms` on `DecisionResult` is filled in here, not by SG-5,
because only the pipeline sees capture-to-decision wall time.

**Owns: contract enforcement.** Every payload from every stage goes through
`validate()` when `check_contracts` is on (the default). Violations are collected, not
raised, so one bad frame does not end a 900-frame profiling run.

**Does not own any algorithm.** If a number looks wrong, the bug is in a module.

## reset() between clips — this one bites

SG-2, SG-3, SG-4 and SG-5 all hold temporal state. Running two clips without
`pipeline.reset()` leaks clip N's closure into clip N+1 and **quietly invalidates every
metric you report**.

`run_pipeline.py` calls it. If you drive the pipeline from your own script, you must.
`test_reset_makes_a_second_run_identical` exists to catch this.

## The tests

```bash
pytest integration/tests -q
```

19 tests in two groups.

**Interface compliance** — what Lab 8 actually gates on: every payload on every frame is
contract-compliant, `frame_id` stays aligned through all five stages, no module raised,
and a decision exists for every frame.

**System behaviour** on the scripted scenario: the alarm fires during the sustained
closure; no alarm while the driver is demonstrably awake; the yawn is detected; blinks
are detected and the long closure is not counted as one; the observation gap is reported
rather than silently filled; losing the face mid-alert does not silence the alarm; the
state track is not chattering.

To take these to Integration Gate 1 (Lab 8), swap the mock face source for real SG-1
output. **The same tests must still pass.** That is the gate.

## Current status

Last run on the mock driver: 300 frames, **0 contract violations**, 0 module errors,
alarm at 6.20 s (1.00 s lag behind the closure onset), no false alarms. End to end
0.103 ms mean on a development PC.

**That FPS ceiling is meaningless for the Jetson** — it excludes SG-1 and camera
capture, which will dominate the budget entirely.

Two known problems, both in `documentation/baseline_findings.md`: the alarm never clears
within the clip, and `WARN` is never reached.
