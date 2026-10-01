# 14-Lab roadmap and integration gates

From the project guide §5, with what each lab means *for this repository*.
Today is **Lab 1 territory** — the scaffold exists, the real work does not.

| Lab | Focus | Deliverable | In this repo |
|---|---|---|---|
| 1 | Problem & system definition | Technical problem, system role, I→P→O, data needs | `README.md`, `interfaces/contracts.py` |
| 2 | Research & candidate algorithms | Survey, 2–3 candidates, limitations, baseline proposal, Jetson suitability | `documentation/algorithm_selection.md` |
| 3 | **Interface gate** | Frozen V1 interface, mock inputs, metrics, experiment plan | `interfaces/` + CI green ⟵ **PHASE-I EXIT** |
| 4 | Baseline prototype | First working algorithm on standardised input, reproducible | `module_sgN/src/`, `results/baseline.json` |
| 5 | Alternative / parameter experiments | Second approach or parameter study, controlled comparison | `module_sgN/configs/experiment_*.yaml` |
| 6 | Quantitative comparison | Metrics table, analysis, evidence-based method selection | `module_sgN/results/comparison.md` |
| 7 | Improved module & robustness | Selected method hardened against failure cases | `module_sgN/results/failure_analysis.md` |
| 8 | **Integration gate 1** | Mocks replaced by real neighbours; multi-module pipeline on PC | `integration/` tests green on real modules |
| 9 | Jetson module deployment | Each module runs on the Jetson; camera integration live | `embedded_sg6/` |
| 10 | Jetson profiling & optimisation | FPS, latency, memory profiling; decisions documented | `embedded_sg6/profiling/` |
| 11 | **Integration gate 2** | Full camera-to-decision pipeline on the embedded target | `run_pipeline.py --source 0` on Jetson |
| 12 | End-to-end optimisation | Bottlenecks, thresholds, scheduling, reliability | `integration/reports/` |
| 13 | Controlled / blind validation | Held-out evaluation, final failure analysis | `evaluation/reports/` |
| 14 | **SEECS CV Face-Off 2026** | Final embedded demonstration | tagged release |

## The three formal gates

**Lab 3 — Interface gate.** Mock input → module → correct interface output. In this
repo that is literally `pytest interfaces/tests` plus
`python module_sgN/run.py`. If those pass, you are through.

**Lab 8 — Integration gate 1.** Real neighbouring modules replace mocks.
`integration/tests/test_pipeline.py` already encodes what this checks — swap the
mock face source for real SG-1 output and the same tests must still pass.

**Lab 11 — Integration gate 2.** The complete camera-to-decision pipeline running
on the Jetson. `python integration/run_pipeline.py --source 0` on the device.

> **Labs 12–14 optimise and validate an existing integrated system.** The guide is
> explicit that first-time integration must not begin here. If you are still
> wiring modules together at Lab 12, the project is already capped at 30/40 for
> the overall component.

## What the completion level is worth

| Final status | Max overall score |
|---|---|
| Complete end-to-end system demonstrated on Jetson | 40 / 40 |
| Partially integrated, an essential module incomplete | 30 / 40 |
| Modules only, no functional end-to-end system | 20 / 40 |

Grade = **60%** sub-group + **40%** overall + up to **5%** Face-Off bonus.

This is why the mock data matters so much: it means "integration" is something you
do continuously from Lab 3, not a thing you attempt once in Lab 11.

## Standard experimental discipline

Every checkpoint answers four questions (guide §3.5): **What did you try? What did
you measure? What did you learn? What engineering decision follows?**

The sequence the guide expects per module:

1. Define the technical question.
2. Research 2–3 candidate approaches.
3. Implement a baseline.
4. Run controlled experiments, tune parameters.
5. Measure with the agreed quantitative metrics.
6. Compare accuracy and robustness *against computational cost*.
7. Select using evidence, not convenience.

Step 6 is the one teams skip. On a Jetson Orin Nano, the most accurate method that
cannot hold frame rate is the wrong method, and you need the numbers to say so.
