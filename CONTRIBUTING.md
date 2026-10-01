# Working practice

Twelve people, one repository, six modules. These rules exist so you can work
without standing on each other.

## Branches

```
main                        protected, integrated, always green
  feature/sg2-ear-baseline   your work
  feature/sg4-perclos-window
  fix/sg3-stuck-mouth-latch
```

- **Never commit to `main` directly.** Merge through a reviewed pull request.
- Branch naming: `feature/sgN-short-description` or `fix/sgN-...`.
- One pull request per logical change. A PR touching three modules is a PR nobody
  reviews properly.
- **Tag at every integration gate** (`lab08-gate1`, `lab11-gate2`). The guide asks
  for this explicitly so a later failed change cannot destroy the last known-good
  system — and at Lab 14 you want something you *know* works to fall back on.

## Who may change what

| Path | Owner | Rule |
|---|---|---|
| `module_sg1/` … `module_sg5/` | that sub-group | your module, your call |
| `embedded_sg6/` | SG-6 | coordinate before changing |
| `interfaces/contracts.py` | **the whole team** | frozen — see below |
| `interfaces/mock/` | the whole team | regenerate, never hand-edit |
| `integration/` | SG-6 + Tech Lead | PR review from an affected group |
| `common/`, `evaluation/` | shared | PR review from one other group |

Changing `interfaces/contracts.py` after the Lab 3 freeze needs team agreement,
a `SCHEMA_VERSION` bump and regenerated mocks. **Read
`documentation/interface_change_policy.md` first.** CI will warn on any PR that
touches it.

Never hand-edit the JSON in `interfaces/mock/` — change `generate_mocks.py` and
re-run it. CI fails if the committed files and the generator disagree.

## Before you open a pull request

```bash
ruff check .                                            # lint
pytest -q                                               # all tests
python integration/run_pipeline.py --source mock --check-scenario
```

All three must pass. The last one proves you have not broken anybody else's module.

## Commit messages

Describe the **technical change**, not the activity:

```
good:  SG-2: reject closures over 500ms as blinks, so microsleeps reach SG-4 as PERCLOS
good:  SG-4: exclude invalid frames from PERCLOS instead of counting them as open
bad:   updated files
bad:   fixed bug
bad:   work in progress
```

> Commit count is **not** a grading metric (guide §3.2), so there is nothing to gain
> from padding it. Git history *is* listed as evidence of individual contribution
> (§4.4), so there is something to lose from one person committing everything.

Both students in a pair must have real commits. Either of you can be asked to
explain any part of your module at a demo.

## Pull request description

Keep it short and answer these:

```markdown
## What and why
One or two sentences.

## Module status
🟢 GREEN / 🟡 AMBER / 🔴 RED  — and why if not green

## Interface impact
None  |  additive only  |  BREAKING (link the agreement)

## Evidence
What you measured, and where the numbers are (results/*.json).

## Checklist
- [ ] ruff check . passes
- [ ] pytest -q passes
- [ ] run_pipeline.py --source mock --check-scenario passes
- [ ] module README updated (performance table, dependencies)
- [ ] mocks regenerated if a contract or labelling rule changed
```

## Every module README must contain

Required by the guide (§3.2). The templates are already in place — keep them
current, especially the performance table:

1. **Purpose** — what this module solves.
2. **Dependencies** — including anything awkward on aarch64.
3. **Input/output interface** — the contract classes, with units.
4. **How to run** — a copy-pasteable command.
5. **Test data** — what it was evaluated on.
6. **Current performance** — accuracy, FPS, memory, and *on what hardware*.

A performance number without the hardware it was measured on is not a result.

## What never gets committed

- raw datasets, video clips, extracted frames
- model weights (`*.pt`, `*.onnx`, `*.engine`, `*.trt`, …)
- virtual environments
- large profiling captures (`*.nsys-rep`)

`.gitignore` covers these. If you need to share a weights file, put it somewhere
else and add a download script to `datasets/scripts/`.

## Escalating

Use the status words, and use them early:

- 🟡 **AMBER** — at risk. Say so at the weekly sync with a mitigation.
- 🔴 **RED** — blocking another module. Escalate the **same day**, to the Tech Lead.

The guide is direct about this: *"a blocking issue must be escalated early"* and
*"teams should not silently compensate for an inactive pair until the final
integration phase."*

Raising a blocker is not a complaint about a teammate. Quietly absorbing it for six
weeks and then missing Integration Gate 2 is the outcome everybody loses from —
including the pair that fell behind.
