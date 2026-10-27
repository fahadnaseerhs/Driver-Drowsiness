---
tags: [driver-drowsiness, planning, midterm, coordination]
owner: Fahad Naseer
---
# Midterm Stage 1 — message to the team

Part of [[Driver Drowsiness Index]] · plan: [[Big-6 Plan]] · tasks: [[Agent Working/To-Do Tasks]]

Copy the short version into the group chat. The long version is the follow-up for
anyone who asks "what exactly do you need from me". Both point at GitHub so the
answers land somewhere that counts as evidence — Component B gives 2 marks for
*documented* coordination, and a WhatsApp reply is not documentation.

---

## Short version (group chat)

> **Midterm Stage 1 is 30 marks and two-thirds of it is team-wide, not per sub-group.**
> A = your algorithm + a working demo (15, assessed sub-group-wise). B = GitHub and
> project management (10, **shared** — one weak module can pull everyone down).
> C = Jetson + camera readiness (5, SG-6 leads, everyone should understand it).
>
> Three things from everyone, by **<date>**:
>
> **1. Push your work.** Commit on your own branch, then merge main into it so you
> have the stuck-alarm fix and the eval harness:
> ```
> git add -A && git commit -m "SG-N: <what you did>"
> git merge origin/main
> git push
> ```
> Small meaningful commits beat one big dump — "meaningful sub-group commits" is
> literally a marked criterion.
>
> **2. Make your module runnable by a stranger.** Your README needs a command that
> works on a fresh clone with no edits, plus your results in `module_sgN/results/`.
> The sheet says screenshots and claims do not substitute for working evidence.
>
> **3. Answer the interface questions** on issue **#14**. Reply in a comment with your
> sub-group tag. "We don't know yet" is a fine answer and gets logged as a blocker —
> silence is not.
>
> Also: **self-assign your issue on the Project board** and move it to In Progress.
> The board being current is 3 of the 10 marks in B.
>
> **SG-6, one blocker is on you:** issue **#13** — is `WARN` distinguishable from
> `ALERT` in the actuation (chime/amber LED vs the full alarm)? SG-5 cannot decide
> whether `WARN` stays in the contract until you answer, and changing it after the
> freeze is a breaking change.

---

## Long version (per sub-group)

**Everyone**
- Commit and push on your branch; merge `origin/main` in (you need `8c9c079` and `2683fa4`).
- README: purpose, dependencies, a verbatim run command, your current numbers, known limitations.
- Results committed under `module_sgN/results/` — JSON dumps or a short comparison table.
- One alternative config (`configs/experiment_a.yaml`) and a run of it. This is the
  "primary + backup with comparative rationale" criterion, 4 marks, and it is the one
  most sub-groups are currently missing.
- Self-assign your board issue, set its status, note blockers in a comment.

**SG-1 — Face & landmarks** (issue #1)
- Run the MediaPipe baseline; show one valid `FaceResult` with 68 landmarks.
- Alternative config: detector confidence or input resolution. Report FPS and failure cases.
- Answer: expected `valid=False` rate on real footage?

**SG-2 — Eye state** (issue #2)
- Alternative: EAR threshold variants, or EAR vs a classifier.
- Report false-open / false-closed, and behaviour with glasses, head pose and low light.
- Answer: how `closure_duration_s` resets, and what happens to it during a tracking gap
  mid-closure. SG-5's 1.2 s emergency override depends entirely on this.

**SG-3 — Yawn & cues** (issue #3)
- Alternative: MAR threshold or yawn-persistence window.
- Report yawn / non-yawn counts and false positives — especially while talking.
- Answer: `yawn_event` on completion, or `yawn_flag` per frame?

**SG-4 — Temporal** (issue #4) — *SG-5's only upstream, so this pair matters most to me*
- Window-length experiment: 2 s vs 3 s, stability against detection delay.
- Answer, please, before I tune anything: which `window_s` ships; what `confidence`
  means numerically; whether `current_closure_s` is populated on every valid frame;
  whether `drowsy_score`'s fusion weights are going to change.
- Joint with SG-5: confirm the alarm *clears* on a real clip, not just the mock.

**SG-5 — Decision & alert** (issue #5) — *mine, in progress*
- Ablation study: hysteresis, dwell, latch and the override removed one at a time, with
  numbers. `module_sg5/results/ablation.md`.
- End-to-end recovery check for the stuck-alarm fix. `module_sg5/results/recovery_check.json`.
- Blocked on SG-6 for the `WARN` decision (#13).

**SG-6 — Jetson & integration** (issue #6) — *carries 5 of the 30 marks alone*
- Board boots, storage and environment documented; Python / Git / OpenCV verified;
  CUDA / PyTorch where needed.
- Camera capture demonstrated — USB or CSI. A prerecorded-video fallback shows software
  readiness but **does not** prove live camera integration, so get a camera on it.
- Record outstanding blockers and next actions; that is explicitly marked.
- Answer #13 (the `WARN` question), plus: alert modality, repeat-alert policy, who fills
  `latency_ms`, whether `reset()` is called between clips.

**Team lead**
- One logged meeting with decisions and interface changes recorded (2 marks in B, plus a
  bonus item, issue #10).
- Clip recording and labelling: who and when (issue #7). This is the critical path for
  SG-4, SG-5 and every Lab 5–6 comparison in the project — it needs a car, people and
  dusk, so it cannot be done the night before.
- Who seals the `test` split, and on what date (risk R5).

---

## What not to say

Don't promise the evaluator a fully integrated camera-to-decision system on the Jetson.
Stage 1 explicitly does not require it — first multi-module integration is Lab 8, Jetson
module deployment Lab 9, the complete embedded pipeline Lab 11. What Stage 1 wants is
each module working, the interface blockers *identified*, and a clear integration plan.
Claiming more invites questions we cannot answer yet.
