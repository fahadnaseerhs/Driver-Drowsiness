---
tags: [driver-drowsiness, agent-working, chats, review]
status: PASS
sg: shared
---
# REVIEW — Real-data evaluation harness

Part of [[Driver Drowsiness Index]]. Task → [[To-Do Tasks]]. How-to → [[How To Do These Tasks]].

**status:** NEEDS-REVIEW (branch `harness/real-data`, commit `2683fa4`, local, not pushed)
**task:** Build the real-data evaluation harness so every sub-group can run baseline vs
alternative on real driver clips (not just mock). Unblocks the Week 5 experiments and all
of Week 6.

## Researcher → Coder (2026-10-08) — TASK 2

`main` is updated (stuck-alarm fix merged, `8c9c079`). **Branch `harness/real-data` from
the latest `main`.** One task, shared infra — this one is allowed to add `datasets/` and
`evaluation/` scaffolding, but **do not change `interfaces/contracts.py`**.

**Build:**
1. **Dataset layout** — define and document under `datasets/`: a `clips/` location for real
   driver videos, a per-clip ground-truth label format (frame ranges for eyes-closed /
   yawn / drowsy, or a CSV), and a `manifests/` entry that lists clips + their label files.
   Put the spec in `datasets/README.md`. Do NOT commit real video; add a `.gitkeep` +
   `.gitignore` rule and document where clips go.
2. **Eval runner** — a script (e.g. `evaluation/run_eval.py`) that: takes a clip + its
   ground-truth, runs the pipeline (`integration/run_pipeline.py --source <clip>`), and
   reports the Week-3 metrics (detection/accuracy, false-alarm rate, missed-alarm rate,
   alert latency), writing a results JSON/table under the sub-group's `results/`.
3. **Runnable without real data yet** — since `datasets/clips/` is empty, make the harness
   runnable on a tiny synthetic/sample input (reuse the mock or a generated short clip) so
   it is testable now; document how to swap in real clips later. Clearly separate
   "methodology works" from "graded accuracy" (which needs real clips).
4. **Tests** — a smoke test that the eval runner produces a metrics file on the sample.

**Before NEEDS-REVIEW, paste real output for:** `ruff check .`, `pytest -q`,
and one successful `python evaluation/run_eval.py ...` run on the sample.

**Loop:** work on `harness/real-data`, set this note to NEEDS-REVIEW when done, then wait.
I check on a ~60 s beat. Commit messages end with
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do not merge to main.

<!-- Coder: reply below this line -->
### Coder → Researcher (2026-10-08) — NEEDS-REVIEW

Built on `harness/real-data` branched from latest `main` (`8c9c079`); commit `2683fa4`,
local, **not pushed**, not merged. `interfaces/contracts.py` untouched.

**What I built**
1. **Dataset layout** — `datasets/clips/` added (gitkeep; `.gitignore` now `datasets/clips/*`
   so the dir is tracked but every real video/frame under it stays ignored — verified
   `foo.mp4` and `frames/x.png` are ignored, `.gitkeep` is not). Ground-truth + manifest
   format were already specified in `datasets/README.md`; I added a "Running the evaluation
   harness" section with real-clip swap-in instructions. `drowsy_episodes_s` is what gets
   scored.
2. **Eval runner** — `evaluation/run_eval.py`: reads a manifest, runs the *same* pipeline as
   `run_pipeline.py` (SG-2..SG-5 on the mock source, SG-1..SG-5 on a real clip), collapses
   the ALERT track with `to_intervals`, scores vs `drowsy_episodes_s` with `score_events`,
   and writes a per-clip + aggregate JSON (recall, precision, F1, false-alarms/hour, alert
   latency, plus processing-latency ms). Reuses `evaluation/src/metrics.py` — one shared
   metric impl. `--out` defaults to `evaluation/reports/<manifest>_eval.json`; point it at
   `module_sgN/results/` for a sub-group experiment.
3. **Runnable now** — `datasets/manifests/sample_mock.json` replays `interfaces/mock` (GT
   mirrors `scenario.json`). Synthetic runs are flagged `graded_accuracy: false` with a loud
   "no graded figure from the mock" note. Real clips absent on the machine are **skipped
   (reported), not crashed**, so the harness runs before any real data lands.
4. **Tests** — `evaluation/tests/test_run_eval.py` (added `evaluation/tests` to
   `pytest.ini` testpaths): methodology-runs smoke test, writes-a-metrics-file test, and an
   absent-real-clip-is-skipped test.

**Checks (real output)**
- `ruff check .` → `All checks passed!`
- `pytest -q` → `109 passed, 1 skipped in 1.92s` (was 105 + 4 new)
- `python evaluation/run_eval.py --manifest datasets/manifests/sample_mock.json` →
  ```
  [SYNTHETIC] mock: recall 1.0 precision 1.0 f1 1.0 FA/hr 0.0 alert_latency 1.0s (TP 1 FN 0 FP 0)
  aggregate : recall 1.0 precision 1.0 f1 1.0 FA/hr 0.0 over 1 clip(s), 9.967s
  graded accuracy : False
  metrics -> evaluation/reports/sample_mock_eval.json
  ```

**please check:** (1) manifest/label schema is what you want sub-groups to fill in;
(2) output location — I defaulted to `evaluation/reports/`; say if you'd rather the default
land elsewhere; (3) the methodology-vs-graded split (synthetic `graded_accuracy:false`).
Committed sample report: `evaluation/reports/sample_mock_eval.json`. Holding for review;
not pushing/merging.

### Researcher → Coder (2026-10-08) — VERDICT: PASS ✅
Re-ran and inspected everything on `2683fa4`.
- **Verified:** `interfaces/contracts.py` untouched (not in the commit — the grep hit was
  the message line); ruff clean; `pytest` 109 passed / 1 skipped; `run_eval.py --manifest
  datasets/manifests/sample_mock.json` exits 0 and writes the report; real video is
  git-ignored (`datasets/clips/foo.mp4`, `frames/x.png` ignored, only `.gitkeep` tracked);
  no real data committed; report captures the Week-3 metrics + `module_errors` +
  `contract_violations` + per-clip metadata, with a loud `graded_accuracy:false` note.
- **Your 3 questions:** (1) **schema approved** — `ground_truth{eyes_closed_s, yawn_s,
  drowsy_episodes_s}` + subject/glasses/lighting is exactly what sub-groups fill in.
  (2) **default `evaluation/reports/` is fine**; for a sub-group experiment point `--out`
  at `module_sgN/results/`, as you documented. (3) **methodology-vs-graded split is
  correct** and important — keep it.
- Nice touch keeping the R5 hold-out note.

**Approved. Do NOT merge to main yet** (user's integration call — I'll recommend it).
Please **STAND BY**: the next tasks (per-branch READMEs, Week 6 recommendation) are gated
on the user approving the Week 6 plan and on real clips being recorded. I'll assign once
the user clears that.
