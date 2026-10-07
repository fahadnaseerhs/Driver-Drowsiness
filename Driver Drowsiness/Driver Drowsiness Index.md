---
tags: [driver-drowsiness, index]
---
# Driver Drowsiness Index

Home: [[Welcome]]

Driver Drowsiness Monitoring System — a camera-to-alarm pipeline for the
**NVIDIA Jetson Orin Nano**. Built in parallel across six sub-groups (SG-1 … SG-6),
wired together through frozen data contracts and shared mock data.

## Notes
1. [[1 - Pipeline SG-1 to SG-5]] — modules, contracts, how to implement each one
2. [[2 - Jetson SG-6 Deploy]] — embedded deployment on the Jetson Orin Nano
3. [[3 - Process Flow Map]] — runtime, failure-handling, and build/deploy diagrams
4. [[4 - Week 5 First Tasks]] — what each sub-group does first this week, and how to research it
5. [[Week 1 - Tasks & Status]] — this week's task checklist and what is / isn't done yet

## Agent Working (Researcher)
- [[To-Do Tasks]] — the live task checklist
- [[How To Do These Tasks]] — how to run each task, expected output, red flags
- [[Chats/_index|Chats]] — ask the **Researcher** here (research/assess, no coding)
- [[Coder Prompt]] — prompt + review-loop for the **Coder** agent (implements tasks)

## Planning
- [[Big-6 Plan]] — the whole system across the six branches
- [[Week 6 Plan (APPROVED)]] — approved; data source = live recording
- [[Week 6 Recommendation]] — candidate per sub-group to carry into Week 6
- Branch guides: [[Branch Guides/SG-1 branch|SG-1]] · [[Branch Guides/SG-2 branch|SG-2]] · [[Branch Guides/SG-3 branch|SG-3]] · [[Branch Guides/SG-4 branch|SG-4]] · [[Branch Guides/SG-5 branch|SG-5]] · [[Branch Guides/SG-6 branch|SG-6]]

## Key files in the repo
- `interfaces/contracts.py` — the frozen data shapes every module speaks (schema `1.0.0`)
- `interfaces/mock/generate_mocks.py` — the deterministic mock-data generator
- `integration/run_pipeline.py` — runs the whole chain (`--source mock | 0 | clip.mp4`)
- `documentation/roadmap.md` — the work plan and integration milestones
