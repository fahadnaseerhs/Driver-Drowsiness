# SG-6 — Embedded Deployment & System Integration

**Owners:** ⚠ **UNASSIGNED for G2-D1.** See `documentation/team.md` and risk R10.
**Status:** 🔴 RED — scaffolding only. Nothing here has run on hardware.

> This sub-group has no pair in the allocation sheet, while four rows of the RACI have
> SG-6 as **Responsible** — including the Jetson base image, which everything else
> depends on. **Raise it with the instructor at Lab 4.** Nobody reaches Integration
> Gate 2 without this module.

## 1. Purpose

Own the common Jetson environment and the integration framework: camera, base image,
dependencies, profiling, optimisation, and real-time alert execution.

Per the guide (§3.4), SG-6 owns the environment, but *"every algorithm sub-group remains
responsible for making its module deployable and benchmarkable on the target platform."*
You are not a porting service for four other pairs.

## 2. Target platform

**NVIDIA Jetson Orin Nano 8GB** · CUDA · TensorRT FP16 · GStreamer · Python 3.10 · OpenCV

| Thing | Value | Recorded by |
|---|---|---|
| JetPack / L4T version | *to be filled in* | — |
| OpenCV version, CUDA enabled | — | — |
| TensorRT version | — | — |
| Camera model | USB-UVC, 720p30 per the plan | — |
| Power mode used for measurements | — | — |

**Fill this in at Lab 9 and keep it current.** Risk **R7** is *"camera or capture
pipeline unstable on Jetson"*, mitigated by *"pin the JetPack version"* — which only
works if somebody writes the version down.

## 3. Contents

```
embedded_sg6/
  requirements-jetson.txt          NOT the same as the PC list -- read the comments
  jetson/setup_jetson.sh           surveys the device and reports what to do
  src/capture_jetson.py            GStreamer capture (USB-UVC and CSI pipelines)
  profiling/profile_pipeline.py    latency + FPS report, with platform metadata
```

## 4. How to run

```bash
# 1. Survey the device. Paste the output into the table in section 2.
bash embedded_sg6/jetson/setup_jetson.sh
```

```bash
# 2. Max clocks. ALWAYS, before any measurement.
sudo nvpmodel -m 0 && sudo jetson_clocks
```

```bash
# 3. Smoke-test capture ON ITS OWN, before wiring anything to it (risk R7).
python3 -m embedded_sg6.src.smoke_capture
```

```bash
# 4. The pipeline. Mock first, then real.
python3 integration/run_pipeline.py --source mock
python3 integration/run_pipeline.py --source 0 --display
```

```bash
# 5. Profile. Run tegrastats alongside in a second terminal.
python3 embedded_sg6/profiling/profile_pipeline.py --source 0 --limit 900
tegrastats --interval 1000 --logfile tegrastats.log
```

## 5. Three things that will cost you a day each

**Do not pip install numpy or opencv-python on the Jetson.** JetPack ships both, built
against CUDA and GStreamer. pip will shadow them with slower CPU-only builds, and the
symptom is "the pipeline got mysteriously slower", not an error message.

**Do not use `cv2.VideoCapture(0)`.** It works, but goes through a slow path and often
will not hold 30 FPS at 720p. Use the GStreamer pipelines in `src/capture_jetson.py`. The
`drop=true max-buffers=1` on the appsink is deliberate: if the pipeline falls behind you
want the newest frame, not a backlog. An alert computed from a two-second-old frame is
worse than useless — it warns about a hazard that has already happened.

**MediaPipe on aarch64 is the real risk.** There is no official Jetson wheel, and SG-1's
baseline depends on it. Options are listed in `requirements-jetson.txt`. **Decide at
Lab 9.** If it slips to Lab 11 it becomes the thing that stops Integration Gate 2, and
the fallback — deploying RetinaFace + PFLD through TensorRT — is not a one-evening job.

## 6. Measurement discipline

A number without its conditions is not a result. Every profiling report must state the
power mode, the JetPack version, the resolution and the git commit.
`profile_pipeline.py` records the platform automatically — do not strip it out.

The Figma KPI set is **FPS, false-alarm rate and alert latency**.
`profile_pipeline.py` covers latency and FPS; `tegrastats` covers utilisation, memory and
power; `evaluation/` covers the false-alarm rate. You need all three.

## 7. Current performance

Nothing measured on hardware.

For reference, the four pure-Python stages cost **0.103 ms per frame combined** on a
development PC. That tells you the budget is entirely SG-1 plus camera capture, and that
optimising SG-2 through SG-5 would be wasted effort until measurement says otherwise.

| Metric | Target | Measured |
|---|---|---|
| End-to-end FPS | ≥ 30 (R2 fallback: 480p) | — |
| Capture→alert latency | < 200 ms | — |
| Peak memory | < 8 GB with headroom | — |
| Power | — | — |
| Sustained run without degradation | 30 min | — |

## Still owed

- [ ] **Get this sub-group assigned** (Lab 4, risk R10)
- [ ] Device survey, versions recorded in §2 (Lab 9)
- [ ] Capture smoke-tested standalone (Lab 9, risk R7)
- [ ] MediaPipe-on-aarch64 decision (Lab 9)
- [ ] Each module running on the device (Lab 9)
- [ ] Profiling, with optimisation decisions documented (Lab 10)
- [ ] TensorRT FP16 conversion where it pays for itself (Lab 10)
- [ ] Full camera-to-decision pipeline on the device (Lab 11, **Gate 2**)
- [ ] Alert modality agreed with SG-5: sound, visual, or both (Lab 9)
- [ ] Demo runbook and rollback plan (Lab 14)
