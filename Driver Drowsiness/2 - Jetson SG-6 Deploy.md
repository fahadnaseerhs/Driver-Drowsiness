---
tags: [driver-drowsiness, jetson, embedded, implementation]
---
# 2 - Jetson (SG-6) Deploy

Part of [[Driver Drowsiness Index]]. Pipeline being deployed: [[1 - Pipeline SG-1 to SG-5]]. Diagram: [[3 - Process Flow Map]].

Target: **Jetson Orin Nano**, JetPack, **Python 3.10**. Folders: `embedded_sg6/jetson`, `embedded_sg6/profiling`, `embedded_sg6/src`.

## Responsibilities
- Run the full SG-1 → SG-5 pipeline on-device at the target 30 FPS / 720p.
- Own the camera (USB-UVC) and the physical alert output (buzzer / LED / display overlay).
- Profile latency per stage; the contract's `DecisionResult.latency_ms` (capture → decision) is the KPI.

## How to implement

### Step 1 - Environment
- Do **not** use the root `requirements.txt`; use `embedded_sg6/requirements-jetson.txt`.
- Use JetPack's OpenCV (not the pip wheel); keep numpy 1.26.x.
- Copy the repo (`interfaces/`, `module_sg1..5`, `integration/`, `embedded_sg6/`) to the board.

### Step 2 - Smoke test on device
```bash
python -m pytest interfaces/tests
python integration/src/main.py --source mock
```
Contracts must pass on ARM too; the mock run needs no camera. (`main.py` and `--source` are the planned entry point - adjust to what integration actually exposes.)

### Step 3 - Camera capture (`embedded_sg6/src`)
- OpenCV `VideoCapture` (V4L2 / GStreamer) at 1280x720, 30 FPS, MJPG.
- Build `Frame(frame_id, time.monotonic(), image)`; drop old frames instead of queueing (keeps latency low).

### Step 4 - Alert output
- Consume `DecisionResult`; drive GPIO / buzzer / overlay when `alert=True`; show `evidence` on screen.
- Fail-safe: if the pipeline stalls (no decision for N ms), raise a "system fault" indicator.

### Step 5 - Profile and optimise (`embedded_sg6/profiling`)
- Time each stage per frame; log p50/p95 latency and FPS.
- If under target: lower resolution for SG-1 only, use TensorRT/GPU delegate, run SG-2 and SG-3 in parallel, reuse landmarks between frames.

### Step 6 - Run on boot
Create a `systemd` service that starts the app, restarts on failure and logs to a file.

## Acceptance checklist
- [ ] Contract tests pass on the Jetson
- [ ] 25-30 FPS or better sustained for 10 min
- [ ] Alert latency within the KPI
- [ ] Alert fires on a recorded drowsy clip, stays quiet on an alert-driver clip
- [ ] Recovers from camera unplug / replug
