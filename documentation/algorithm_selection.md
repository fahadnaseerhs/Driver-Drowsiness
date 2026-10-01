# Algorithm selection — scored decision matrix

From the Figma plan, section 3.

Each candidate is scored 1–5 per criterion. Weights reflect embedded deployment:
**accuracy and on-device FPS count ×3**, memory and robustness ×2, licence ×1. The
highest weighted total becomes the baseline, and **one alternative is always carried
as a comparison**.

| Module | Candidate | Acc ×3 | FPS ×3 | Mem ×2 | Robust ×2 | Lic ×1 | Weighted | Decision |
|---|---|:--:|:--:|:--:|:--:|:--:|:--:|---|
| **Face + landmarks** | MediaPipe FaceMesh | 4 | 5 | 4 | 4 | 5 | **55** | **BASELINE** |
| | RetinaFace + PFLD | 5 | 3 | 3 | 5 | 4 | 50 | Comparison |
| | YOLOv8-face | 5 | 3 | 2 | 5 | 4 | 48 | Rejected — memory cost |
| **Eye state** | Eye Aspect Ratio (EAR) | 3 | 5 | 5 | 3 | 5 | **49** | **BASELINE** — fast, explainable |
| | MobileNetV2 classifier | 5 | 3 | 3 | 5 | 5 | 49 | Comparison — fallback for glasses |
| **Yawn** | Mouth Aspect Ratio (MAR) | 3 | 5 | 5 | 3 | 5 | **49** | **BASELINE** |
| | MobileNet yawn classifier | 5 | 3 | 3 | 5 | 5 | 49 | Comparison |
| **Temporal** | PERCLOS + sliding window | 4 | 5 | 5 | 4 | 5 | **56** | **BASELINE** — industry standard |
| | LSTM over frame cues | 5 | 3 | 3 | 5 | 5 | 49 | Comparison — stretch goal |
| **Decision** | Rule-based thresholds | 3 | 5 | 5 | 3 | 5 | 49 | BASELINE |
| | Weighted score + hysteresis | 4 | 5 | 4 | 4 | 5 | **54** | **Target after baseline** |
| | SVM / small MLP | 4 | 4 | 4 | 4 | 5 | 50 | Comparison |

## What is implemented right now

Every **BASELINE** row above is implemented in the scaffold, plus the weighted-score
decision logic (54) rather than the plain rule-based one — the hysteresis is needed
for risk R6 and there was no reason to write the weaker version first.

**No comparison row has been implemented.** That is Labs 5–6 work, and it is 25% of
each sub-group's mark ("Experimentation & Quantitative Evaluation"), so it is not
optional polish.

## The ties are the interesting part

**Eye state: EAR and MobileNetV2 both score 49.** That is not a reason to pick
either — it is a reason the comparison has to actually be run. EAR is cheap and
explainable but degrades on glasses and in low light. The CNN is robust but costs
memory and frame rate. On this hardware that trade is the whole question, and risk
R1 (no glasses or night coverage in the dataset) means you currently have no data
to settle it with. **Fix the data before arguing about the model.**

**Yawn: same tie, same reasoning.** 49 against 49.

**Decision: three candidates within 5 points.** Start from the weighted score with
hysteresis (54), because nuisance alerts are the documented failure mode. The
SVM/MLP comparison only becomes meaningful once there is enough labelled data to
train on without overfitting — see risk R5.

## Honest caveats about this table

These scores were assigned during planning, from reputation and documentation
rather than measurement on a Jetson Orin Nano 8GB. Specifically:

- **The FPS column is an estimate.** None of these has been profiled on the target.
  MediaPipe scoring 5 assumes a working aarch64 build, which is itself an open
  question — see `embedded_sg6/requirements-jetson.txt`.
- **The memory column is a guess** until something is actually loaded on the 8 GB
  device alongside everything else in the pipeline.

So treat the table as a prioritisation of what to measure first, not as a result.
When you do measure, **update this file with the real numbers** and note which
decisions changed. "We predicted X and measured Y" is exactly the evidence the
guide's §3.5 discipline asks for, and it is worth more marks than a table that
silently agrees with itself all semester.

## Recording a comparison

When a sub-group completes its Lab 5–6 comparison, write
`module_sgN/results/comparison.md` with:

1. The technical question, in one sentence.
2. Both methods, with the exact configs used (`configs/*.yaml`, committed).
3. The dataset and split — and confirmation the hold-out set was untouched (R5).
4. A metrics table: accuracy/F1, FPS, memory, plus the failure cases each method
   loses on.
5. The decision, and what evidence drove it.
6. What you would do differently with more time.

Then update this file's Decision column if the baseline changed.
