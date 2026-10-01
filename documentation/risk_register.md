# Risk register

From the Figma plan, section 5. Exposure = Probability × Impact, each rated 1–5.

- **15 and above** — act now.
- **8 to 14** — documented mitigation, reviewed at the weekly sync.
- **below 8** — monitor.

| ID | Risk | Area | P | I | Exposure | Mitigation | Owner |
|---|---|---|---|---|---|---|---|
| **R1** | Dataset does not cover glasses or night lighting | Data | 4 | 5 | **20** | Collect a 500-clip in-car supplement at dusk | SG-2 lead |
| **R2** | Jetson cannot sustain 30 FPS end to end | Performance | 4 | 4 | **16** | Reduce to 480p, TensorRT FP16, ROI-only crops | SG-6 lead |
| **R3** | Interface drift after the contract freeze | Process | 3 | 5 | **15** | Schema check in CI; pull request blocks on a diff | Tech lead |
| **R4** | One pair falls behind and blocks integration | People | 3 | 5 | **15** | Mock I/O mandatory from day one, nobody waits | Tech lead |
| R5 | Thresholds overfit to the recorded clips | Model | 3 | 4 | 12 | Hold-out set untouched until final validation | SG-4 lead |
| R6 | False alerts cause the driver to disable the system | Usability | 3 | 4 | 12 | Hysteresis plus a sustained-closure duration gate | SG-5 lead |
| R8 | Evaluation conditions differ from the dev setup | External | 4 | 3 | 12 | Rehearse under randomised lighting before the demo | Tech lead |
| R9 | Unequal contribution within a pair | People | 3 | 3 | 9 | Per-student task tags; both demo the whole module | Instructor |
| R7 | Camera or capture pipeline unstable on Jetson | Platform | 2 | 4 | 8 | Pin the JetPack version; smoke-test capture first | SG-6 lead |

## Which of these the scaffold already addresses

**R3 (interface drift) — mechanised.** `interfaces/contracts.py` is the single
source of truth, `validate()` enforces it, and `.github/workflows/ci.yml` fails a
pull request if the committed mock data stops matching the generator or if any
payload violates its contract. CI also posts a warning when `contracts.py` itself
is touched. The mitigation in the Figma plan says "schema check in CI" — that is
the file.

**R4 (a pair falls behind) — mechanised.** `interfaces/mock/` means every
downstream pair can work from day one against standardised input, and
`integration/src/pipeline.py` runs with any module absent or throwing, recording
it rather than crashing. Tests cover both
(`test_pipeline_runs_with_sg3_missing`, `test_a_module_that_raises_is_contained_and_counted`).

**R6 (false alerts) — partly addressed, needs real data.** SG-5 implements three
independent brakes: asymmetric thresholds, dwell time, and alert latching. Tests
assert that a single noisy frame cannot raise an alarm and that a score parked on
the boundary does not flicker. But "false alarm rate" is only meaningful on real
clips of awake drivers, which do not exist yet.

**R2 (Jetson FPS) — not addressed, and not yet measurable.** The four pure-Python
stages cost 0.1 ms per frame together, which is irrelevant. The budget is SG-1 plus
capture, and neither has run. See `documentation/baseline_findings.md` §1.

**R1 (dataset coverage) — not started.** This is the highest-exposure risk on the
register and the one with the longest lead time, because it needs people, a car and
a camera at dusk. Start it before Lab 5, not after the accuracy numbers disappoint.

## A risk the Figma register does not list

**R10 — an unassigned sub-group.** G2-D1 has no SG-6 pair in the allocation sheet
(see `documentation/team.md`). SG-6 owns the Jetson base image and the integration
framework, so an unowned SG-6 makes Integration Gate 2 unreachable.

| ID | Risk | Area | P | I | Exposure | Mitigation | Owner |
|---|---|---|---|---|---|---|---|
| **R10** | SG-6 unassigned in the allocation sheet | People | 4 | 5 | **20** | Confirm with the instructor at Lab 4; if unresolved, assign from SG-5's three members and record it | Tech lead |

Review this table at the weekly sync and change the numbers when reality changes.
A risk register that is identical in week 12 to week 1 was not being used.
