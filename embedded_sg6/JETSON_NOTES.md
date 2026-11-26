# Jetson bring-up notes — SG-6 (embedded team)

Local testing record from 2026-11-26. **Not merged process** — official procedure stays
`embedded_sg6/README.md`; commit anything from here only through a normal reviewed PR.

## 1. The device

| Thing | Value |
|---|---|
| Board | NVIDIA Jetson Orin Nano 8GB (`Selected Device: Orin`) |
| JetPack / L4T | **R36 REVISION 4.4** (JetPack 6) |
| CUDA | 12.6 (`/usr/local/cuda-12.6`) |
| TensorRT | **10.3.0** (`libnvinfer` 10.3.0.30, python `tensorrt` importable) |
| Python | 3.10.12 — matches the repo target |
| OpenCV | 4.8.0 — **CPU build**: `cv2.cuda.getCudaEnabledDeviceCount()` → 0 |
| numpy | 1.21.5 (system) |
| Disk | 233 GB, ~203 GB free |
| Camera | **none attached** (`/dev/video*` empty) |
| Power mode for all numbers below | `nvpmodel -m 0` + `jetson_clocks` |

## 2. SSH access

```bash
ssh tauseef@10.7.176.210          # password: shared in the team group, NOT here (public repo)
```

Key-based auth is already set up for the lab PC (`someone@` dev machine) — from there
plain `ssh tauseef@10.7.176.210` needs no password. To add your own machine:

```bash
ssh-copy-id tauseef@10.7.176.210
```

`tauseef` is a sudoer (same password as SSH). Hostname is `gmaildotcom`.

## 3. What is installed / where things live

| What | How / where |
|---|---|
| Repo working copy | `~/Driver-Drowsiness` (rsynced from the lab PC, **not a git clone** — re-sync or clone fresh before relying on it) |
| `python3-pip` | installed via apt (pip 22.0.2) |
| `PyYAML==6.0.2`, `jsonschema==4.23.0`, `tqdm==4.66.5` | `pip install --user`, per `requirements-jetson.txt` |
| `cuda-python==12.6.2.post1` | `pip install --user` — see gotcha G2 |
| TensorRT test artefacts | `~/trt_test/`: `mobilenetv2-7.onnx` (ONNX model zoo), `mobilenetv2_fp16.engine`, `run_engine.py` |
| **NOT installed** | mediapipe (the Lab 9 aarch64 decision is still open), numpy/opencv via pip (forbidden — would shadow JetPack's builds) |

## 4. Test runs and results

### 4.1 Mock pipeline on-device — PASS

```bash
cd ~/Driver-Drowsiness
python3 integration/run_pipeline.py --source mock --check-scenario
```

Result: 0 contract violations, both scenario checks PASS.
SG-2..SG-5 combined: **mean 0.203 ms / frame, p95 0.236 ms** (ceiling ~4900 FPS).
Confirms the SG-6 README's claim that the budget is entirely SG-1 + capture.

### 4.2 TensorRT FP16 engine build + benchmark — PASS

MobileNetV2 (the SG-2 alternative eye-classifier architecture) as the representative model:

```bash
cd ~/trt_test
/usr/src/tensorrt/bin/trtexec --onnx=mobilenetv2-7.onnx --fp16 --saveEngine=mobilenetv2_fp16.engine
```

| Metric | Value |
|---|---|
| GPU compute, mean | **1.546 ms** (1x3x224x224) |
| Host latency, mean | 1.609 ms |
| Throughput | **644.9 inf/s** |
| H2D / D2H copies | 0.054 ms / 0.010 ms |

Conditions: FP16, batch 1, `nvpmodel -m 0` + `jetson_clocks`, TensorRT 10.3, R36.4.4.

### 4.3 Python-side inference through the TensorRT runtime — PASS

```bash
cd ~/trt_test && python3 run_engine.py     # prints "GPU INFERENCE OK"
```

Deserialises the saved engine, `cudaMalloc` + async copies + `execute_async_v3` via
`cuda-python`, and checks the output: shape (1, 1000), all values finite, sane softmax.
This is the path a real TensorRT-deployed module (e.g. RetinaFace+PFLD fallback) would use.

## 5. Gotchas

- **G1 — `cuda-python` 13.x fails on JetPack 6.** pip's default is 13.x, which dies with
  `cudaErrorInsufficientDriver` (needs a CUDA 13 driver; the board has 12.6). Pin
  `cuda-python==12.6.*`. The 12.6 import is `from cuda import cudart`, not
  `from cuda.bindings import runtime`.
- **G2 — the cuda-python 12.6 install is slow** (~several minutes, builds on-device).
  Don't assume a hung terminal.
- **G3 — `trtexec --shapes` needs the real tensor name.** `--shapes=input:1x3x224x224`
  fails hard on this model; its input tensor is `data`. Omit `--shapes` for a
  fixed-shape ONNX, or read the name from the log first.
- **G4 — JetPack's OpenCV here is CPU-only** (`cv2.cuda` → 0 devices), contrary to what
  `requirements-jetson.txt` assumes. GStreamer capture still needs to be verified once a
  camera exists. Either way the standing rule holds: **never pip install numpy or
  opencv-python on the Jetson** — pip wheels would shadow the system build and lose
  GStreamer.
- **G5 — trtexec is not on PATH.** It lives at `/usr/src/tensorrt/bin/trtexec`.
- **G6 — pip warns `~/.local/bin` is not on PATH** — add it if you need the installed
  entry-point scripts.
- **G7 — mediapipe on aarch64 remains undecided** (Lab 9). Nothing on the device proves
  SG-1's baseline runs here yet; today's GPU proof covers the TensorRT fallback path.

## 6. Still open on hardware

- [ ] Attach the USB-UVC camera, run `python3 -m embedded_sg6.src.smoke_capture` (risk R7)
- [ ] mediapipe-on-aarch64 decision (install wheel vs. RetinaFace+PFLD via TensorRT)
- [ ] `python3 integration/run_pipeline.py --source 0 --display` with real SG-1
- [ ] `embedded_sg6/profiling/profile_pipeline.py` + `tegrastats` for the KPI table
- [ ] Copy §1 of this file into the README §2 platform table via a proper PR
