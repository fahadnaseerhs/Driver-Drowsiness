---
tags: [driver-drowsiness, home]
---
# Driver Drowsiness Monitoring System

Real-time computer-vision system that watches a driver's face, detects drowsiness
(eye closure, slow blinking, yawning) and raises an **OK / WARN / ALERT** alarm.
Target hardware: **NVIDIA Jetson Orin Nano 8GB**, 720p @ 30 FPS.

Start here → [[Driver Drowsiness Index]]

## The pipeline at a glance

```
Camera → SG-1 (face + 68 landmarks) → SG-2 (eyes/EAR) ┐
                                     → SG-3 (yawn/MAR) ┴→ SG-4 (temporal) → SG-5 (decision) → Alarm
```

- **SG-1** face & landmark detection
- **SG-2** eye state, blink, closure duration (EAR)
- **SG-3** yawn detection (MAR)
- **SG-4** temporal analysis — PERCLOS, rates, fused `drowsy_score`
- **SG-5** decision with hysteresis → OK / WARN / ALERT
- **SG-6** Jetson deployment, camera, alarm output, profiling

Every arrow is a frozen data contract in `interfaces/contracts.py`.

## Our approach — parallel, not sequential

We **do not** build the modules in order (SG-1 then SG-2 then SG-3…). We freeze the
interfaces first, generate deterministic **mock data** for every stage, and build all
six modules **at the same time**, each against the mock output of its upstream
neighbour. Integration is then continuous: mock → real modules on PC → full pipeline
on the Jetson, all on one `main` branch.

See [[1 - Pipeline SG-1 to SG-5]] for module detail and [[3 - Process Flow Map]] for diagrams.

## Notes
1. [[1 - Pipeline SG-1 to SG-5]] — modules, contracts, how to implement each one
2. [[2 - Jetson SG-6 Deploy]] — embedded deployment on the Jetson Orin Nano
3. [[3 - Process Flow Map]] — runtime, failure-handling, and build/deploy diagrams
4. [[4 - Week 5 First Tasks]] — what each sub-group does first this week, and how to research it
