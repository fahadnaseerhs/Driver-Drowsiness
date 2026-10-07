# SG-4 / SG-5 stuck-alarm fix — results

**Task:** SG-4 "Fix the stuck-alarm bug (alarm held ~3 s after recovery)."
**Approach:** A (coordinated additive-interface change). Schema `1.0.0 → 1.0.1`.

## Root cause
The alarm hold was **not** a `drowsy_score` problem. It was SG-5's hard override:

```python
override = temporal.longest_closure_s >= self.closure_override_s   # 1.20 s
if override: target = ALERT          # bypasses score, dwell, hysteresis, latch
```

`longest_closure_s` is the **window maximum**, so after a long closure ends it stays
high until it ages out of the (3 s) window — forcing ALERT for ~a full window into
recovery. Changing only SG-4's score (the discarded Approach B) could not fix this,
because the override ignores the score.

## Fix
Additive field `TemporalResult.current_closure_s` — the closure of the **current**
frame, `0.0` the instant the eyes reopen (vs `longest_closure_s`, any closure still in
the window). SG-5 now keys its override on `current_closure_s`:

- escalate on the **current** closure (an ongoing long closure is still an immediate
  emergency — safety preserved),
- **de-escalate** once the eyes reopen (override releases; normal hysteresis + latch
  decide when ALERT clears).

Files: `interfaces/contracts.py` (field + schema bump + validate), `module_sg4/src/temporal.py`
(emit field, score unchanged), `module_sg5/src/decision.py` (override + evidence),
`interfaces/mock/generate_mocks.py` (emit field; mocks regenerated, idempotent).

## Evidence
The fix is proven by a **targeted unit test**, not by the synthetic mock's tail:

- `module_sg5/tests/test_decision.py::test_override_releases_when_the_closure_ends_so_the_alert_can_clear`
  — eyes reopen (`current_closure_s=0`) while `longest_closure_s` still holds 1.5 s in
  the window and the score has fallen → state returns to **OK**. On the old override
  (keyed on `longest_closure_s`) this stayed pinned at ALERT — i.e. it is a true
  regression test for the bug.
- `...::test_window_max_closure_alone_does_not_force_alert` — a lingering window-max
  closure with eyes open now must not fire the override.
- `...::test_an_ongoing_long_closure_still_alerts_immediately` — safety: eyes shut *now*
  ≥ 1.20 s still goes straight to ALERT.
- SG-4: `module_sg4/tests/test_temporal.py::test_current_closure_tracks_the_ongoing_closure_not_the_window_max`.

### End-to-end mock state track (discussion point, NOT tuned)
`python integration/run_pipeline.py --source mock --check-scenario` still reports
`ALERT 6.20 → 9.97 s`, unchanged from the committed baseline. This is expected and is
**not** the override: in this clip the no-face gap (8–9 s) plus microsleeps keep windowed
PERCLOS — and therefore the (unchanged) `drowsy_score` — high into recovery, so SG-5's
score-hysteresis holds ALERT on its own. `documentation/baseline_findings.md` warns
against tuning to this synthetic tail; real-clip recovery is where the override release
matters. Full report: `module_sg5/results/pipeline_after_fix.json`.

## Checks (all pass)
- `ruff check .` → All checks passed!
- `pytest -q` → 105 passed, 1 skipped
- `python integration/run_pipeline.py --source mock --check-scenario` → exit 0,
  0 contract violations, scenario PASS (alarm fires at 6.20 s, no false alarm in first 2 s).
