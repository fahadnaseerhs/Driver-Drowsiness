---
tags: [driver-drowsiness, flow, diagram]
---
# 3 - Process Flow Map

Covers [[1 - Pipeline SG-1 to SG-5]] and [[2 - Jetson SG-6 Deploy]]. Index: [[Driver Drowsiness Index]].

## Runtime data flow (per frame)

```mermaid
flowchart LR
    CAM["Camera USB-UVC<br/>30 FPS 720p<br/>SG-6"] -->|Frame BGR| SG1["SG-1 Face and Landmarks"]
    SG1 -->|FaceResult| SG2["SG-2 Eye State<br/>EAR, blink"]
    SG1 -->|FaceResult| SG3["SG-3 Yawn<br/>MAR"]
    SG2 -->|EyeResult| SG4["SG-4 Temporal<br/>PERCLOS, rates"]
    SG3 -->|YawnResult| SG4
    SG4 -->|"TemporalResult<br/>drowsy_score 0..1"| SG5["SG-5 Decision<br/>OK / WARN / ALERT"]
    SG5 -->|DecisionResult| ALERT["Alert out<br/>buzzer / LED / overlay<br/>SG-6"]
    SG5 -.->|latency_ms, logs| PROF["Profiling and evaluation"]
```

## Per-frame failure handling

```mermaid
flowchart TD
    A[New frame] --> B{Face found?}
    B -- no --> C["SG-1 returns valid=False, reason=no_face"]
    C --> D[SG-2 and SG-3 pass empty results]
    D --> E[SG-4 treats as missing, no crash]
    B -- yes --> F[Eye + mouth analysis]
    F --> G[SG-4 sliding window]
    E --> H[SG-5 always emits a DecisionResult]
    G --> H
    H --> I{State}
    I -- OK --> J[No action]
    I -- WARN --> K[Visual warning]
    I -- ALERT --> L["Alarm + evidence text"]
```

## Build and deploy flow

```mermaid
flowchart TD
    S1[Freeze contracts + mocks] --> S2[Each SG builds against mocks]
    S2 --> S3["validate + pytest per module"]
    S3 --> S4["Integrate in integration/src"]
    S4 --> S5[Evaluate on datasets]
    S5 --> S6[Copy to Jetson Orin Nano]
    S6 --> S7[Camera + alert output]
    S7 --> S8[Profile latency / FPS]
    S8 --> S9{KPI met?}
    S9 -- no --> S10["Optimise: TensorRT, parallel SG-2/3, lower res"]
    S10 --> S8
    S9 -- yes --> S11[systemd autostart + demo]
```

## Reading the map
1. Camera pushes a `Frame` by reference; nothing is serialised in the hot path.
2. SG-1 is the only module that touches pixels; SG-2/3 use landmarks and ROIs.
3. SG-2 and SG-3 are independent and can run in parallel.
4. SG-4 turns frame cues into window behaviour; SG-5 turns the score into a state.
5. Every arrow carries a contract object that always exists (`valid` + `reason`), so the chain never breaks on missing data.
