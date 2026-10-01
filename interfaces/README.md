# interfaces/ — the frozen contracts and the mock data

The most important folder in the repository. Everything else depends on it, and it is
owned by **the whole team**, not any one sub-group.

```
interfaces/
  contracts.py          the agreement, written as code
  mock/
    generate_mocks.py   builds the synthetic driver
    mock_face.json      SG-1 output    -> input for SG-2, SG-3
    mock_eye.json       SG-2 output    -> input for SG-4
    mock_yawn.json      SG-3 output    -> input for SG-4
    mock_temporal.json  SG-4 output    -> input for SG-5
    scenario.json       the ground truth the above were built from
  tests/
    test_contracts.py   the Lab 3 Interface Gate, automated
```

## Why the contract is code and not a document

The guide requires each interface to fix six things by Lab 4: data format, units,
coordinate convention, confidence representation, error/empty-output behaviour, and
example test data.

Written as prose, those get interpreted differently by five pairs and the mismatch
surfaces at Integration Gate 1. Written as dataclasses with a `validate()` function, a
computer checks them on every push instead.

That is also the mitigation for risk **R3** (interface drift, exposure 15): *"schema
check in CI; pull request blocks on a diff."*

## The six things, as implemented

| Requirement | Where |
|---|---|
| Data format | the dataclasses in `contracts.py` |
| Units | stated per field, in comments |
| Coordinate convention | pixels, origin **top-left of the full frame**, x right, y down |
| Confidence | float in `[0.0, 1.0]`, checked by `validate()` |
| Empty behaviour | `.empty()` on every payload: `valid=False` + a non-empty `reason` |
| Example payloads | `mock/*.json` |

## The empty-behaviour rule

Every module, on every failure, returns its payload with `valid=False` and a `reason`
string. **Never `None`. Never an exception.** `validate()` rejects `valid=False` with an
empty reason.

This is why the pipeline survives a missing face, a module that has not been written
yet, and a module that throws. Downstream groups must tolerate `valid=False` on every
frame without crashing — that is what the contract tests assert.

## The mock data

Synthetic, deterministic — no randomness, no seeds — so two students on two machines
get byte-identical files and can compare results meaningfully.

A scripted 10-second scenario, 300 frames at 30 FPS:

| Time | What happens |
|---|---|
| 0.0–2.0 s | alert driver, two normal blinks |
| 2.2–3.4 s | a yawn, eyes still mostly open |
| 4.0–5.0 s | alert, one more blink |
| 5.2–7.0 s | **sustained closure, 1.8 s** — must end in `ALERT` |
| 7.0–8.0 s | microsleeps, repeated long closures |
| 8.0–9.0 s | **no face** — exercises the empty-behaviour rule |
| 9.0–10.0 s | recovery, eyes open |

The landmarks are synthetic but **geometrically consistent**: the eye hexagons are laid
out so the standard EAR formula evaluates to exactly the scripted aperture, and the lip
ellipse likewise for MAR. Verified to within 0.00003 (EAR) and 0.00012 (MAR).

So SG-2 and SG-3 can run their **real** maths on `mock_face.json` and recover the
scripted curve. That is the difference between useful practice data and a trap.

### Regenerating

```bash
python interfaces/mock/generate_mocks.py
```

**Never hand-edit the JSON.** Change the generator and re-run it. CI fails if the
committed files and the generator disagree — if that fails, somebody changed a contract
or a labelling rule and the committed reference data is now a lie.

### What the mock is not

No camera noise, no motion blur, no glasses, no lighting variation, one perfectly
frontal synthetic face.

**It is for interface tests and unit tests. No graded accuracy number may come from
it** — it will flatter any method, including a bad one. See `datasets/README.md`.

`scenario.json` also carries a `target_behaviour` block: what the team *wants* SG-5 to
output. That is a design goal for Labs 5–7, **not** a description of what the baseline
currently does. The baseline differs, and `documentation/baseline_findings.md` says how.

## Changing a contract

After the Lab 3 freeze, `contracts.py` needs team agreement, a `SCHEMA_VERSION` bump,
regenerated mocks and updated consumers — in one pull request.

Read `documentation/interface_change_policy.md`. There are three changes worth arguing
for **now, before the freeze**, listed at the bottom of that file.

## Running the gate

```bash
pytest interfaces/tests -q
```

24 tests: geometry, the empty-behaviour rule on all five payloads, JSON round-trips,
enum serialisation, schema-version mismatch, and negative checks that `validate()`
actually rejects bad values. Plus a check that every committed mock file satisfies the
contract it claims to implement, and that the sequences stay frame-aligned.

A checker that passes everything is worse than none, because it manufactures false
confidence — so several of those tests exist purely to confirm it still says no.
