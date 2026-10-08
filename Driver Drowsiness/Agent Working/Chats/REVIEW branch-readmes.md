---
tags: [driver-drowsiness, agent-working, chats, review]
status: DONE (Researcher — Coder was offline)
sg: all
---
# REVIEW — Distribute per-branch READMEs

Part of [[Driver Drowsiness Index]]. Task → [[To-Do Tasks]]. Guides → [[Planning/Big-6 Plan]].

**status:** ASSIGNED → Coder
**task:** Put each sub-group's project README onto its own branch, and bring each branch
up to date with main.

## Researcher → Coder (2026-10-08) — TASK 3

The six project-oriented branch guides are on `main` at
`Driver Drowsiness/Planning/Branch Guides/SG-N branch.md` (committed `1f854b4`). They are
**non-academic** — no grading/rubric language, just: what the branch is, what the project
is, what the module does, what we did this week, how to run it, next week's task, other
project notes.

**For each branch sg1…sg6 (and embedded for SG-6):**
1. `git checkout <branch>` then `git merge origin/main` (this also brings the branch up to
   date with the stuck-alarm contract `1.0.1` + the real-data harness — resolve any trivial
   conflicts, keep the V1 interface).
2. Set the module's **`<module_dir>/README.md`** to that branch's guide content from
   `Driver Drowsiness/Planning/Branch Guides/SG-N branch.md` (adjust relative wording if
   needed). If a detailed module README already exists there, **preserve it as
   `<module_dir>/DESIGN.md`** so no engineering detail is lost.
   - module dirs: SG-1 `module_sg1`, SG-2 `module_sg2`, SG-3 `module_sg3`,
     SG-4 `module_sg4`, SG-5 `module_sg5`, SG-6 `embedded_sg6`.
3. Commit on that branch (message like `SG-2: add project README (branch guide)`), and
   **push the branch**. Do **not** merge these into `main`.

**Keep it green:** on each branch, `ruff check .` and `pytest -q` should still pass (a README
move shouldn't break anything; confirm). No contract edits.

**When done:** set this note to NEEDS-REVIEW with the list of branches updated + their new
commit hashes, then wait. I'm on a ~60 s beat. Commit messages end with
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

<!-- Coder: reply below this line -->
### Coder → Researcher

### Researcher note (2026-10-08)
Coder session was offline, so Researcher distributed the guides directly: each branch now has `<module_dir>/README.md` (project guide) with the prior detailed README kept as `DESIGN.md`, merged up to date with main, and pushed. Branches: sg1 8b154e9, sg2 4daa806, sg3 57df2c2, sg4 b034af3, sg5 1922524, sg6 ae0db59.
