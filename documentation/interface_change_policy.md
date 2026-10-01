# Interface change policy

`interfaces/contracts.py` is **frozen at the Lab 3 gate**. After that it is shared
property, and changing it unilaterally breaks other people's work silently.

This exists because of risk **R3** — interface drift after the freeze, exposure 15.

## What counts as a breaking change

Breaking (needs the full process below):

- removing or renaming a field
- changing a field's type, units, or coordinate convention
- changing the meaning of an existing value (e.g. redefining EAR)
- changing an enum's members
- making a previously optional field required

Not breaking (just do it, mention it in the pull request):

- adding a new **optional** field with a safe default
- improving a docstring or comment
- adding a new validation rule that existing compliant data already passes

The test for "safe default": every existing consumer must behave identically if it
ignores the new field entirely. `yaw_deg` defaulting to `None` is safe. A new field
defaulting to `0.0` that SG-4 is expected to read is not.

## Process for a breaking change

1. **Raise it at the weekly sync**, not in a pull request. Say what you need and
   why your module cannot meet the current contract.
2. **Get agreement from every affected sub-group.** Both neighbours minimum; the
   Tech Lead signs off (they are **A** for interface contracts in the RACI).
3. **Bump `SCHEMA_VERSION`** in `contracts.py`. Patch for additive, minor for a
   breaking change. `from_dict` refuses mismatched payloads loudly rather than
   mis-parsing them — that is deliberate, do not weaken it.
4. **Regenerate the mocks**: `python interfaces/mock/generate_mocks.py`, and commit
   the result. CI fails if the committed mock data and the generator disagree.
5. **Update every affected module and its tests** in the *same* pull request. A
   contract change that lands without its consumers is how Lab 8 fails.
6. **Record it in the log below**, with a date and who agreed.
7. **Tag the previous commit** so the last known-good system survives (guide §3.2).

## Why `from_dict` is strict about versions

It raises rather than best-effort parsing. A silently mis-parsed payload produces
plausible-looking wrong numbers, and you find out weeks later when the accuracy is
inexplicably poor. A loud failure costs five minutes.

The same reasoning drives the strictness elsewhere: SG-4 rejects mismatched
`frame_id`s instead of averaging over them, and SG-5 refuses to escalate on low
upstream coverage instead of guessing.

## Change log

| Date | Version | Change | Raised by | Agreed by |
|---|---|---|---|---|
| 2026-10-01 | 1.0.0 | Initial V1 draft, pre-freeze. Eye sides corrected to the iBUG convention (36–41 = driver's **right** eye) before any module consumed them. | scaffold | **pending team agreement at Lab 3/4** |

> The V1 contract has **not yet been agreed by the team** — it was drafted from the
> project guide and the Figma pipeline diagram. Agreeing it is a Lab 3/4 action, and
> the right time to argue with it is before the freeze, not after.
>
> Specifically worth arguing about now:
>
> - Should `FaceResult` carry 68 landmarks, or would SG-2/SG-3 rather receive the
>   ROIs and compute from the full FaceMesh? 68 was chosen so EAR/MAR indices are
>   stable and documented, but it does discard mesh detail.
> - Should `TemporalResult` also expose `current_closure_s` as well as
>   `longest_closure_s`? `documentation/baseline_findings.md` §2 shows this is
>   probably needed — and it is **much** cheaper to add before the freeze.
> - Is `WARN` a real state with a real behaviour, or should the contract carry only
>   OK and ALERT? See `baseline_findings.md` §3.
