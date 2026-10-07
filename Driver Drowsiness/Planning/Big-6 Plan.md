---
tags: [driver-drowsiness, planning, big-6]
---
# Big-6 Plan — the whole system across six branches

Part of [[Driver Drowsiness Index]]. Week 6: [[Week 6 Plan (APPROVED)]]. Recommendation: [[Week 6 Recommendation]].

The project is one pipeline built by six pairs in parallel, wired through a **frozen data
contract** (`interfaces/contracts.py`) and **deterministic mock data**. Nobody waits for
anybody: each module is built against the mock output of its upstream neighbour, then the
real modules replace the mocks one at a time.

```
Camera → SG-1 (face+68 landmarks) → SG-2 (eyes/EAR) ┐
                                   → SG-3 (yawn/MAR) ┴→ SG-4 (temporal) → SG-5 (decision) → Alarm
                                                                         SG-6 = Jetson + integration
```

## Branch map
| Branch | Module | Owns | Consumes | Produces |
|---|---|---|---|---|
| `sg1/landmark-detector` | Face & landmarks | MediaPipe FaceMesh → 68 iBUG | `Frame` | `FaceResult` |
| `sg2/eye-threshold` | Eye state & blink | EAR | `FaceResult` | `EyeResult` |
| `sg3/yawn-cues` | Yawn & cues | MAR | `FaceResult` | `YawnResult` |
| `sg4/temporal-window` | Temporal | PERCLOS + window + fusion | `EyeResult`+`YawnResult` | `TemporalResult` |
| `sg5/fusion-rules` | Decision & alert | hysteresis + override | `TemporalResult` | `DecisionResult` |
| `sg6/jetson-integration` | Deploy & integrate | Jetson, full pipeline | all | on-device run |

## The rules that keep parallel work safe
1. Edit only your own `module_sgN/` folder. Never touch `interfaces/` alone — contract
   changes are additive + team-agreed (`documentation/interface_change_policy.md`).
2. Build against `interfaces/mock/*.json`; the mock is for interface/unit tests only.
3. Before any push: `ruff check .`, `pytest -q`,
   `python integration/run_pipeline.py --source mock --check-scenario`.
4. Merge to `main` via review; `main` always stays green.

## Status (2026-10-08)
- `main` green, with the **stuck-alarm fix** and the **real-data harness** merged.
- Branches created for all six sub-groups; each should `git merge origin/main` to pick up
  the harness + contract (`SCHEMA_VERSION 1.0.1`).
- Done: SG-4/SG-5 stuck-alarm fix (`current_closure_s`), real-data eval harness.
- Pending: each sub-group's Week 5 experiment + live clips; SG-6 owner; Week 6 runs.

## How the two agents work
- **Researcher** — plans, reviews, files outputs, maintains [[To-Do Tasks]] and the Chats.
- **Coder** — implements one task at a time on a branch, then requests review in Obsidian.
See [[Coder Prompt]] and the loop in [[Chats/_index|Chats]].

## Week 6 in one line
Each pair runs baseline vs its selected candidate on **live-recorded** clips with
`evaluation/run_eval.py`, picks the winner by the metrics, and SG-6 integrates them for a
live Jetson run. Details: [[Week 6 Plan (APPROVED)]].
