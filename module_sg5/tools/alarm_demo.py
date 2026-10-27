"""SG-5 audible alarm -- the demo actuator for OK / WARN / ALERT.

    python module_sg5/tools/alarm_demo.py                      # stress track, hear it alarm and clear
    python module_sg5/tools/alarm_demo.py --input interfaces/mock/mock_temporal.json
    python module_sg5/tools/alarm_demo.py --source mock        # through the whole pipeline
    python module_sg5/tools/alarm_demo.py --source 0           # LIVE CAMERA (needs SG-1 + a webcam)
    python module_sg5/tools/alarm_demo.py --silent --fast      # no sound, no pacing (CI / smoke test)

WHY THIS LIVES HERE, AND WHAT IT IS NOT
---------------------------------------
By the V1 contract, SG-5 emits a ``DecisionResult`` and **SG-6 owns the physical
alert** -- buzzer, LED, GPIO, screen overlay. That boundary is deliberate: the
decision must be testable without a speaker, and the actuator must be swappable
without touching the safety logic. Nothing in this file is imported by
``src/decision.py``, and the decision path gains no dependency from it.

So this is a *demo actuator*: it consumes ``DecisionResult`` exactly as SG-6's
hardware path will -- ``state`` for what to play, ``evidence`` for what to show --
so it doubles as a working specification of the actuation SG-6 has to build.

It also answers two questions that are currently open in writing:

  * Issue #13, "is WARN distinguishable from ALERT in the actuation?" -- here it
    is: WARN is a single soft chime on entry, ALERT is an urgent repeating beep.
    If the team keeps that distinction, WARN has a purpose and stays in the
    contract; if nobody wants the chime, WARN should leave it.
  * Issue #12/#13, the repeat-alert policy -- this implements "pulse while the
    state holds" (beep, short gap, beep) rather than one continuous tone, because
    a continuous tone is what drivers reach over and switch off.

THE SOUND NEVER TOUCHES THE DECISION LOOP
-----------------------------------------
``winsound.Beep`` is blocking, and ~180 ms of blocking per frame inside a 30 fps
pipeline would wreck both the frame rate and every latency number this module
reports. So the beeping happens on a daemon thread and ``Beeper.set_state`` only
flips a flag. Measure the decision latency with ``tools/ablation.py``, not here.
"""

from __future__ import annotations

import argparse
import csv
import platform
import statistics
import sys
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.config import load_config  # noqa: E402
from common.jsonio import read_sequence, write_sequence  # noqa: E402
from interfaces.contracts import DrowsinessState  # noqa: E402
from module_sg5.src.decision import DrowsinessDecider  # noqa: E402

MODULE = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = MODULE / "fixtures" / "stress_track.json"
DEFAULT_CONFIG = MODULE / "configs" / "default.yaml"

# Alarm shape. Frequencies are a compromise: high enough to cut through road and
# engine noise, low enough not to be painful in a closed cabin. Tune with SG-6 on
# the real buzzer -- these are right for laptop speakers, which is not the target.
ALERT_HZ = 1000       # urgent
ALERT_BEEP_MS = 180
ALERT_GAP_S = 0.12    # pulse, don't drone -- a continuous tone invites switching off
WARN_HZ = 660         # gentler, and clearly a different sound
WARN_BEEP_MS = 140


class Beeper:
    """Turns a drowsiness state into sound, off the decision thread.

    Backends, in order of preference:
      ``winsound`` -- real tones (Windows only, which is the dev platform here)
      ``bell``     -- the terminal bell, for anything else
      ``silent``   -- counts what it would have played, for CI and for a machine
                      with no audio device
    """

    def __init__(self, backend: str = "auto") -> None:
        self.backend = self._pick(backend)
        self._state = DrowsinessState.OK
        self._chime = threading.Event()     # one-shot, set on entry to WARN
        self._wake = threading.Event()      # avoids a busy-wait while OK
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._winsound: Any = None
        self.beeps = 0                      # ALERT pulses actually emitted
        self.chimes = 0                     # WARN chimes emitted
        self.warn_entries = 0               # times the state ENTERED warn
        self.alert_entries = 0              # times the state ENTERED alert
        self.alarm_seconds = 0.0            # total time the alarm was sounding
        if self.backend == "winsound":
            import winsound
            self._winsound = winsound

    @staticmethod
    def _pick(backend: str) -> str:
        if backend != "auto":
            return backend
        if platform.system() == "Windows":
            try:
                import winsound  # noqa: F401
                return "winsound"
            except ImportError:
                pass
        return "bell"

    # ------------------------------------------------------------------ #
    def __enter__(self) -> Beeper:
        self._thread = threading.Thread(target=self._loop, name="sg5-alarm", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Stop the alarm. Safe to call twice, and called on any exit path --
        an alarm left sounding after the program ends is its own bug."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    # ------------------------------------------------------------------ #
    def set_state(self, state: DrowsinessState) -> None:
        """Non-blocking. Call this once per frame from the decision loop."""
        if state is DrowsinessState.WARN and self._state is not DrowsinessState.WARN:
            self._chime.set()               # chime on ENTRY only, not every frame
            self.warn_entries += 1
        elif state is DrowsinessState.ALERT and self._state is not DrowsinessState.ALERT:
            self.alert_entries += 1
        self._state = state
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._state is DrowsinessState.ALERT:
                self._emit(ALERT_HZ, ALERT_BEEP_MS)
                self.beeps += 1
                self.alarm_seconds += ALERT_BEEP_MS / 1000.0
                self._stop.wait(ALERT_GAP_S)
            elif self._chime.is_set():
                self._chime.clear()
                self._emit(WARN_HZ, WARN_BEEP_MS)
                self.chimes += 1
            else:
                self._wake.wait(0.05)
                self._wake.clear()

    def _emit(self, hz: int, ms: int) -> None:
        if self.backend == "winsound":
            try:
                self._winsound.Beep(hz, ms)
                return
            except (RuntimeError, OSError) as exc:
                # No audio device, or a locked-down session. Degrade rather than
                # crash: a demo tool must never take the pipeline down with it.
                print(f"[alarm] sound unavailable ({exc}); falling back to the terminal bell",
                      file=sys.stderr)
                self.backend = "bell"
        if self.backend == "bell":
            sys.stderr.write("\a")
            sys.stderr.flush()
        time.sleep(ms / 1000.0)             # keep the pulse shape in every backend


# --------------------------------------------------------------------------- #
LOG_COLUMNS = (
    "frame_id", "t_s", "face_valid", "face_reason", "ear", "eye_state",
    "closure_s", "blink_event", "mar", "yawn_flag", "perclos",
    "longest_closure_s", "current_closure_s", "blink_rate_per_min",
    "yawn_rate_per_min", "confidence", "drowsy_score", "state", "alert",
    "evidence",
)


class Recorder:
    """Per-frame log plus the diagnostics that answer 'why did it not alarm?'.

    Always accumulates the counters; writes the CSV only when a path is given.
    The counters matter more than the file: on a live run the first question is
    never "what did SG-5 decide" but "did SG-2 ever think my eyes were shut",
    and that is two lines of this summary.
    """

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._fh = None
        self._writer = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = path.open("w", newline="", encoding="utf-8")
            self._writer = csv.DictWriter(self._fh, fieldnames=LOG_COLUMNS)
            self._writer.writeheader()

        self.frames = 0
        self.face_valid = 0
        self.face_reasons: dict[str, int] = {}
        self.eye_states: dict[str, int] = {}
        self.states: dict[str, int] = {"OK": 0, "WARN": 0, "ALERT": 0}
        self.ears: list[float] = []
        self.max_closure_s = 0.0
        self.max_perclos = 0.0
        self.max_score = 0.0
        self.min_confidence = 1.0
        self.transitions: list[tuple[float, str, str, str]] = []

    def write(self, decision: Any, temporal: Any, face: Any = None,
              eye: Any = None, yawn: Any = None) -> None:
        self.frames += 1
        self.states[decision.state.value] = self.states.get(decision.state.value, 0) + 1
        self.max_perclos = max(self.max_perclos, temporal.perclos)
        self.max_score = max(self.max_score, temporal.drowsy_score)
        if temporal.valid:
            self.min_confidence = min(self.min_confidence, temporal.confidence)
        self.max_closure_s = max(self.max_closure_s, temporal.current_closure_s)

        if face is not None:
            if face.valid:
                self.face_valid += 1
            else:
                self.face_reasons[face.reason] = self.face_reasons.get(face.reason, 0) + 1
        if eye is not None:
            key = eye.eye_state.value
            self.eye_states[key] = self.eye_states.get(key, 0) + 1
            if eye.ear is not None:
                self.ears.append(eye.ear)

        if self._writer is not None:
            self._writer.writerow({
                "frame_id": decision.frame_id,
                "t_s": round(decision.timestamp, 4),
                "face_valid": "" if face is None else int(face.valid),
                "face_reason": "" if face is None else face.reason,
                "ear": "" if eye is None or eye.ear is None else round(eye.ear, 4),
                "eye_state": "" if eye is None else eye.eye_state.value,
                "closure_s": "" if eye is None else round(eye.closure_duration_s, 3),
                "blink_event": "" if eye is None else int(eye.blink_event),
                "mar": "" if yawn is None or yawn.mar is None else round(yawn.mar, 4),
                "yawn_flag": "" if yawn is None else int(yawn.yawn_flag),
                "perclos": round(temporal.perclos, 4),
                "longest_closure_s": round(temporal.longest_closure_s, 3),
                "current_closure_s": round(temporal.current_closure_s, 3),
                "blink_rate_per_min": round(temporal.blink_rate_per_min, 2),
                "yawn_rate_per_min": round(temporal.yawn_rate_per_min, 2),
                "confidence": round(temporal.confidence, 4),
                "drowsy_score": round(temporal.drowsy_score, 4),
                "state": decision.state.value,
                "alert": int(decision.alert),
                "evidence": decision.evidence,
            })

    def note_transition(self, decision: Any, previous: DrowsinessState) -> None:
        self.transitions.append((round(decision.timestamp, 3), previous.value,
                                 decision.state.value, decision.evidence))

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    # ------------------------------------------------------------------ #
    def report(self) -> None:
        """The debugging summary. Read it top to bottom: if the face was never
        found, nothing below it means anything."""
        print("\n--- diagnostics " + "-" * 56)
        print(f"frames                : {self.frames}")
        if self.face_valid or self.face_reasons:
            pct = 100.0 * self.face_valid / self.frames if self.frames else 0.0
            print(f"face detected         : {self.face_valid}/{self.frames} ({pct:.1f}%)")
            for reason, n in sorted(self.face_reasons.items(), key=lambda kv: -kv[1]):
                print(f"  not detected        : {n} x {reason}")
        if self.eye_states:
            parts = "  ".join(f"{k} {v}" for k, v in sorted(self.eye_states.items()))
            print(f"eye_state counts      : {parts}")
        if self.ears:
            print(f"EAR min/median/max    : {min(self.ears):.3f} / "
                  f"{statistics.median(self.ears):.3f} / {max(self.ears):.3f}")
        print(f"longest closure seen  : {self.max_closure_s:.2f} s")
        print(f"peak PERCLOS          : {self.max_perclos:.3f}")
        print(f"peak drowsy_score     : {self.max_score:.3f}")
        print(f"lowest confidence     : {self.min_confidence:.3f}")
        parts = "  ".join(f"{k} {v}" for k, v in self.states.items())
        print(f"state frames          : {parts}")

        if self.transitions:
            print("\nstate changes:")
            for t_s, before, after, evidence in self.transitions:
                print(f"  {t_s:8.3f}s  {before:<5} -> {after:<5}  {evidence}")
        else:
            print("\nstate changes         : none -- the state never left OK")

        self._hints()
        print("-" * 72)

    def _hints(self) -> None:
        """Point at the most likely cause rather than leaving you to guess.
        Ordered by where the chain breaks first."""
        hints: list[str] = []
        closed = self.eye_states.get("CLOSED", 0)
        unknown = self.eye_states.get("UNKNOWN", 0)

        if self.frames and self.face_valid == 0 and self.face_reasons:
            hints.append(
                "SG-1 never found a face, so nothing downstream could work. Check lighting, "
                "that you are in frame, and that the camera is not mirrored before SG-1.")
        elif self.eye_states and closed == 0:
            hints.append(
                "SG-2 never reported CLOSED, so no closure ever reached SG-4. If you really "
                "did shut your eyes, SG-2's EAR threshold is wrong for your face -- compare "
                "the EAR range above with module_sg2/configs/default.yaml and tell SG-2.")
        elif unknown > self.frames * 0.3:
            hints.append(
                f"SG-2 returned UNKNOWN on {unknown} frames -- the eye ROI was unusable that "
                "often. Glasses, head pose or low light. This also drags confidence down.")

        if self.max_closure_s and self.max_closure_s < 1.2:
            hints.append(
                f"The longest closure was {self.max_closure_s:.2f} s, under the 1.20 s "
                "override. Hold your eyes shut longer, or lower closure_override_s.")
        if self.min_confidence < 0.5:
            hints.append(
                f"Confidence fell to {self.min_confidence:.2f}, below min_confidence 0.50, so "
                "SG-5 refused to escalate on those frames. That is the gate working, but on a "
                "live run it usually means patchy face detection.")
        if self.states.get("ALERT", 0) and self.max_score >= 0.55:
            hints.append(
                "If the alarm stayed on well after you opened your eyes, that is the known "
                "half-fixed stuck alarm (issue #16), not this tool.")
        if hints:
            print("\nwhat to look at:")
            for hint in hints:
                print(f"  * {hint}")


def _announce(decision: Any, previous: DrowsinessState | None) -> DrowsinessState:
    """Print a line only when the state CHANGES. One line per frame at 30 fps is
    noise that hides the two moments you actually want to see."""
    state = decision.state
    if state is not previous:
        mark = {"OK": "    ", "WARN": "  ! ", "ALERT": " !! "}[state.value]
        print(f"{mark}{decision.timestamp:7.3f}s  {state.value:<5}  {decision.evidence}")
    return state


def replay_temporal(path: Path, config: dict, beeper: Beeper, realtime: bool,
                    limit: int | None = None, recorder: Recorder | None = None) -> dict:
    """Drive SG-5 straight from a TemporalResult fixture.

    No camera, no MediaPipe, no OpenCV -- this path runs anywhere, which is why it
    is the default. Use it to prove the alarm works before blaming the camera.
    """
    records = read_sequence(path)
    if limit is not None:
        records = records[:limit]
    decider = DrowsinessDecider(config)
    decider.reset()
    previous: DrowsinessState | None = None
    started = time.perf_counter()
    episodes = 0

    for temporal in records:
        if realtime:
            # Pace to the fixture's own clock so the alarm is audible in real time
            # instead of a 30 ms blur.
            lag = temporal.timestamp - (time.perf_counter() - started)
            if lag > 0:
                time.sleep(lag)
        decision = decider.process(temporal)
        beeper.set_state(decision.state)
        if recorder is not None:
            recorder.write(decision, temporal)
            if previous is not None and decision.state is not previous:
                recorder.note_transition(decision, previous)
        if decision.state is DrowsinessState.ALERT and previous is not DrowsinessState.ALERT:
            episodes += 1
        previous = _announce(decision, previous)

    return {"frames": len(records), "episodes": episodes,
            "span_s": records[-1].timestamp if records else 0.0}


def replay_pipeline(source_spec: str, beeper: Beeper, limit: int | None,
                    recorder: Recorder | None = None, display: bool = False,
                    status_every: float = 0.0,
                    temporal_out: list | None = None) -> dict:
    """Drive the whole SG-1..SG-5 pipeline and alarm on its decisions.

    ``mock`` replays the synthetic driver and needs nothing installed. A video path
    or a camera index needs the real SG-1, so MediaPipe and OpenCV must import --
    if they do not, the pipeline reports itself DEGRADED and SG-5 will see
    valid=False on every frame, which correctly produces no alarm at all.
    """
    from common.video import MockFaceSource, make_source
    from integration.run_pipeline import load_module_configs
    from integration.src.pipeline import build_default_pipeline

    use_mock = source_spec == "mock"
    pipe = build_default_pipeline(need_sg1=not use_mock, configs=load_module_configs())
    faces = None
    if use_mock:
        src = MockFaceSource()
        faces = src.load()
    else:
        src = make_source(source_spec)

    overlay = None
    if display:
        from integration.src.overlay import OverlayRenderer
        overlay = OverlayRenderer()

    state: dict[str, Any] = {"previous": None, "episodes": 0, "last_status": 0.0}

    def on_frame(frame_output: Any) -> None:
        decision = frame_output.decision
        temporal = frame_output.temporal
        beeper.set_state(decision.state)

        if temporal_out is not None:
            # Keep SG-4's actual output so the comparison can be replayed over
            # this real run later. A live camera cannot be rerun seven times.
            temporal_out.append(temporal)

        if recorder is not None:
            recorder.write(decision, temporal, frame_output.face,
                           frame_output.eye, frame_output.yawn)
            if state["previous"] is not None and decision.state is not state["previous"]:
                recorder.note_transition(decision, state["previous"])

        if (decision.state is DrowsinessState.ALERT
                and state["previous"] is not DrowsinessState.ALERT):
            state["episodes"] += 1
        state["previous"] = _announce(decision, state["previous"])

        # A rolling one-liner, so a live run shows the numbers moving without
        # printing 30 lines a second.
        if status_every > 0 and (decision.timestamp - state["last_status"]) >= status_every:
            state["last_status"] = decision.timestamp
            eye = frame_output.eye
            ear = f"{eye.ear:.3f}" if eye.ear is not None else " -- "
            print(f"  t={decision.timestamp:7.2f}s  face={int(frame_output.face.valid)}"
                  f"  EAR={ear}  {eye.eye_state.value:<7}"
                  f"  closure={temporal.current_closure_s:4.2f}s"
                  f"  PERCLOS={temporal.perclos:4.2f}  score={temporal.drowsy_score:4.2f}"
                  f"  conf={temporal.confidence:4.2f}  {decision.state.value}")

        if overlay is not None:
            overlay.show(frame_output)
            if overlay.stop:
                raise KeyboardInterrupt      # 'q' in the window ends the run

    try:
        outputs = pipe.run(src, faces=faces, limit=limit, on_frame=on_frame)
    finally:
        if overlay is not None:
            overlay.close()
    return {"frames": len(outputs), "episodes": state["episodes"],
            "span_s": outputs[-1].decision.timestamp if outputs else 0.0}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SG-5 audible drowsiness alarm (demo actuator).")
    ap.add_argument("--input", type=Path, default=None,
                    help=f"TemporalResult fixture to replay (default: {DEFAULT_INPUT.name})")
    ap.add_argument("--source", default=None,
                    help="run the full pipeline instead: 'mock', a video path, or a camera index")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="SG-5 config YAML")
    ap.add_argument("--backend", choices=("auto", "winsound", "bell", "silent"), default="auto")
    ap.add_argument("--silent", action="store_true", help="shorthand for --backend silent")
    ap.add_argument("--fast", action="store_true",
                    help="do not pace to the clip's clock (you will not hear much)")
    ap.add_argument("--limit", type=int, default=None, help="stop after N frames")
    ap.add_argument("--log", type=Path, default=None,
                    help="write a per-frame CSV here (EAR, eye state, PERCLOS, score, state)")
    ap.add_argument("--display", action="store_true",
                    help="show the video with the debug overlay (--source runs only)")
    ap.add_argument("--status-every", type=float, default=0.0, metavar="SECONDS",
                    help="print a rolling one-line readout this often (try 0.5 on a live run)")
    ap.add_argument("--save-temporal", type=Path, default=None, metavar="PATH",
                    help="save SG-4's output as a replayable track, so tools/ablation.py "
                         "can compare every configuration over THIS run (--source only)")
    args = ap.parse_args(argv)

    if args.source and args.input:
        ap.error("pass --input (fixture replay) or --source (full pipeline), not both")
    if args.display and not args.source:
        ap.error("--display needs --source: a fixture replay has no video to draw on")
    if args.save_temporal and not args.source:
        ap.error("--save-temporal needs --source: replaying a track cannot produce a new one")

    backend = "silent" if args.silent else args.backend
    realtime = not args.fast
    config = load_config(args.config) if args.config.exists() else {}

    print("SG-5 audible alarm -- WARN = one chime, ALERT = repeating beep.")
    print("State changes only; Ctrl-C to stop.\n")

    beeper = Beeper(backend)
    if beeper.backend == "silent":
        print("[alarm] backend=silent: counting what would have played.\n")
    elif beeper.backend == "bell":
        print("[alarm] backend=bell: terminal bell only; your terminal may ignore it.\n")

    recorder = Recorder(args.log)
    temporal_out: list | None = [] if args.save_temporal else None
    stats = {"frames": 0, "episodes": 0, "span_s": 0.0}
    interrupted = False
    try:
        with beeper:
            if args.source:
                stats = replay_pipeline(args.source, beeper, args.limit, recorder,
                                        args.display, args.status_every, temporal_out)
            else:
                stats = replay_temporal(args.input or DEFAULT_INPUT, config, beeper,
                                        realtime, args.limit, recorder)
    except KeyboardInterrupt:
        # Stopping a live run with Ctrl-C or 'q' is the normal way to end it, so
        # the diagnostics below must still be printed -- they are the whole point.
        interrupted = True
        print("\nstopped", file=sys.stderr)
    finally:
        beeper.close()                      # never leave the alarm sounding
        recorder.close()
        # Written in `finally` so a run stopped with Ctrl-C or 'q' -- which is
        # how a live run normally ends -- still leaves a replayable track.
        if temporal_out:
            write_sequence(args.save_temporal, temporal_out)

    print(f"\n{stats['frames']} frames, {stats['span_s']:.2f} s of input")
    print(f"ALERT episodes      : {stats['episodes']}")
    print(f"WARN entries        : {beeper.warn_entries}")
    print(f"alarm pulses played : {beeper.beeps}")
    print(f"WARN chimes played  : {beeper.chimes}")
    print(f"alarm sounding for  : {beeper.alarm_seconds:.2f} s")
    if args.fast:
        # The alarm runs on its own thread in real time; with pacing off, the
        # replay finishes before the thread can emit much. Say so rather than
        # letting the two "played" lines read as a measurement.
        print("\n--fast: the two 'played' counts above are meaningless -- the replay "
              "outran the\nalarm thread. The 'episodes' and 'entries' counts are real. "
              "Drop --fast to hear it.")
    if beeper.chimes == 0:
        print("\nNo WARN chime: the state never entered WARN. That is the known "
              "unreachable-WARN\nproblem (README section 7, issue #13), not a fault here.")

    recorder.report()
    if args.save_temporal and temporal_out:
        print(f"\nSG-4 track    -> {args.save_temporal}  ({len(temporal_out)} frames)")
        print("  compare every configuration over this real run:")
        print(f"  python module_sg5/tools/ablation.py --fixture {args.save_temporal}")
    if args.log:
        print(f"per-frame log -> {args.log}")
        print("  open it in Excel and sort/filter on eye_state, closure_s or state to see "
              "exactly\n  what the pipeline thought, frame by frame.")
    return 130 if interrupted else 0


if __name__ == "__main__":
    raise SystemExit(main())
