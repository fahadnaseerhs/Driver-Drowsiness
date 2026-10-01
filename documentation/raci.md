# Team responsibility — RACI matrix

From the Figma plan, section 4.

- **R** — Responsible, does the work.
- **A** — Accountable, one person signs it off.
- **C** — Consulted, asked for input *before* action.
- **I** — Informed, told afterwards.

| Deliverable | SG-1 Face | SG-2 Eye | SG-3 Yawn | SG-4 Temporal | SG-5 Decision | SG-6 Jetson | Tech Lead | Instr. |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Frozen interface contracts | R | R | R | R | R | C | **A** | I |
| Dataset selection and labelling | C | R | R | C | C | I | **A** | I |
| Per-module baseline algorithm | R | R | R | R | R | I | C | I |
| Mock input / output for downstream | R | R | R | R | R | C | **A** | I |
| Jetson base image and dependencies | I | I | I | I | I | R | **A** | I |
| Multi-module integration | R | R | R | R | R | R | **A** | I |
| Jetson deployment of each module | R | R | R | R | R | C | **A** | I |
| FPS, latency and memory profiling | C | C | C | C | C | R | **A** | I |
| End-to-end pipeline validation | R | R | R | R | R | R | **A** | C |
| Alert thresholds and failure analysis | C | R | R | R | R | C | **A** | I |
| Demo rehearsal and rollback plan | R | R | R | R | R | R | **A** | I |
| Escalation of a blocking module | R | R | R | R | R | R | **A** | C |

## Reading this honestly

**The Tech Lead is Accountable for nearly everything.** That is a real workload, not
a title. It does not transfer the *work* — every R stays where it is — but it does
mean one person has to notice when something is not happening. Choose accordingly,
and consider the monthly rotation the guide offers (§3.1) so it does not burn one
person out.

**"Jetson deployment of each module" is R for every algorithm sub-group**, not just
SG-6. This matches the guide: SG-6 owns the common environment and integration
framework, but *"every algorithm sub-group remains responsible for making its module
deployable and benchmarkable on the target platform"* (§3.4). You cannot hand your
module to SG-6 and call it done.

**"Mock input / output for downstream" is R for everyone.** This is the row that
makes concurrent development possible, and it is why `interfaces/mock/` exists in
this repo before any real algorithm does. If your mock output is missing or wrong,
you are blocking someone whether or not your own module works.

> ## ⚠ SG-6 is currently unassigned for G2-D1
>
> The allocation sheet lists no SG-6 pair for this team. Four rows in this matrix
> have SG-6 as **R** — including the Jetson base image, which everything else
> depends on. Until that is resolved this matrix is aspirational.
>
> See `documentation/team.md` and risk **R10** in `documentation/risk_register.md`.

## Keeping it current

Update this file whenever ownership moves, and date the change. A RACI that no
longer matches who is actually doing the work is worse than none, because people
will rely on it to decide who to ask.
