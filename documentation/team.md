# Team G2-D1 — Driver Drowsiness Monitoring

Section/Group: **Gp 2**, project **Driver Drowsiness Monitoring**, team code **G2-D1**.
Source: `Semester_Project_Topic_Sub_Group_Allocations_Section_A_B.pdf`, rows 75–85.

> ## ⚠ Two things to confirm before relying on this file
>
> **1. The name-to-NUST-ID pairing is not reliable.** The allocation PDF's table
> cells extract in an order that does not preserve rows, and two independent
> extraction methods disagreed — for example whether `457506` is Abdul Wahid or
> Anss Ahmad. The *set* of people in G2-D1 and the *number per sub-group* are
> solid; the exact pairing is not. **Check the original PDF and fix this table at
> the first team meeting.**
>
> **2. G2-D1 has no SG-6 pair listed.** The allocation ends at SG-5 (row 85).
> Every other Driver Drowsiness team (G1-D1, G1-D2) has 2–3 people on SG-6.
> SG-6 owns the Jetson environment, the integration framework and the real-time
> alert execution — per the project guide, §3.4. **Raise this with the instructor
> immediately**; see "If SG-6 stays unassigned" below.

---

## Sub-group allocation

NUST IDs per sub-group are reliable. Names need confirming (see warning above).

| Sub-group | Module | NUST IDs | Names appearing in the G2-D1 block |
|---|---|---|---|
| SG-1 | Driver Face & Landmark Detection | 466391, 464775 | Muhammad Hassan, Muhammad Hashir Arif |
| SG-2 | Eye State & Blink Analysis | 457506, 455712 | Abdul Wahid, Anss Ahmad |
| SG-3 | Yawn & Facial-Cue Analysis | 456020, 456910 | Abdul Sammi Khan, Shaheer Asghar, Tayyaba Naveed |
| SG-4 | Temporal Behaviour Analysis | 459631, 481329 | Rija Shah, Muhammad Hamza Jehangir |
| SG-5 | Drowsiness Decision & Alert Logic | 472195, 403897, 459305 | Eman Rana, Fahad Naseer, Syed Muhammad Dawar Raza Zaidi |
| SG-6 | Embedded Deployment & Integration | **none listed** | — |

11 IDs and 12 names appear in the block, so at least one row's ID did not extract.
That is another reason to reconcile against the original.

---

## Roles to fill at the Lab 4 meeting

The guide (§3.1) requires these decided by end of Lab 4:

- [ ] **Technical Team Lead / Coordinator** — one person, system-level
      coordination. Does not remove any sub-group's responsibility. The RACI in
      the Figma plan makes this role **Accountable** for almost every deliverable,
      so pick someone who will actually chase things.
- [ ] Decide: one lead for the semester, or rotate monthly.
- [ ] Confirm the name/ID table above against the original PDF.
- [ ] GitHub repository created, with a project board.
- [ ] Freeze the V1 interfaces — already drafted in `interfaces/contracts.py`,
      needs the team to *agree* it, not just inherit it.
- [ ] Resolve the SG-6 gap.

---

## If SG-6 stays unassigned

Do not let this drift. SG-6 owns the common Jetson environment, and nobody can
reach Integration Gate 2 (Lab 11) without it. If the instructor does not assign a
pair:

1. **Ask first.** It is most likely a clerical omission in the allocation sheet.
2. If the team must cover it, the guide already states that *"every algorithm
   sub-group remains responsible for making its module deployable and
   benchmarkable on the target platform"* (§3.4) — so the work is distributable,
   but someone still has to own the base image and the integration framework.
3. SG-5 has three people and the smallest code surface (`decision.py` is the
   shortest module in the repo). That is the most natural place to find capacity.
4. Whatever is decided, write it in this file with a date, and update the RACI in
   `documentation/raci.md`. An unowned module is the single most common way a
   project like this fails its integration gate.

---

## Weekly technical sync

Required by the guide (§3.4). Keep it short and focused on four things only:

1. **Interface status** — is your V1 contract still being met?
2. **Blockers** — anything stopping another pair.
3. **Integration readiness** — can your module take real upstream input yet?
4. **Jetson constraints** — anything that will not fit in 8 GB or 30 FPS.

Maintain a one-word status per module, and put it in the pull request description:

| Status | Meaning |
|---|---|
| 🟢 GREEN | on track |
| 🟡 AMBER | at risk, mitigation in progress |
| 🔴 RED | **blocking integration** — escalate the same day |

The guide is explicit that *"a blocking issue must be escalated early"* and that
*"teams should not silently compensate for an inactive pair until the final
integration phase."* Escalating is not a complaint; covering silently is the
behaviour that gets penalised.

---

## Individual accountability

Both students in a pair are expected to understand the **whole** module. At
demonstrations either one may be asked to explain the algorithm, the experiments,
the interface or the code. Individual marks can differ where contribution or
understanding clearly differs.

Practical consequence: **tag your commits with who did what**, and make sure both
people in a pair have written some of the module. Git history is listed in the
guide as evidence of individual contribution (§4.4).
