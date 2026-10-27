"""SG-5 alarm actuator tests.

The actuator is the only part of SG-5 with a thread in it, and the failure modes
are the embarrassing kind: an alarm that chimes once per frame instead of once per
event, or one still sounding after the program has exited. Both are tested here.

Every test uses ``backend="silent"``, so the suite stays runnable on CI with no
audio device -- and so running the tests never makes a noise.
"""

from __future__ import annotations

from interfaces.contracts import DrowsinessState
from module_sg5.tools.alarm_demo import Beeper

OK, WARN, ALERT = DrowsinessState.OK, DrowsinessState.WARN, DrowsinessState.ALERT


def test_warn_chimes_on_entry_not_once_per_frame() -> None:
    """A chime per frame would be 30 chimes a second. The WARN cue is an event,
    not a level, so entering WARN once must count once however long it holds."""
    b = Beeper(backend="silent")
    for state in (OK, WARN, WARN, WARN, WARN):
        b.set_state(state)
    assert b.warn_entries == 1


def test_leaving_and_re_entering_warn_counts_twice() -> None:
    """The opposite failure: collapsing two separate WARN events into one, which
    would hide a driver repeatedly drifting in and out of drowsiness."""
    b = Beeper(backend="silent")
    for state in (OK, WARN, OK, WARN):
        b.set_state(state)
    assert b.warn_entries == 2


def test_alert_entries_count_episodes_not_frames() -> None:
    """ALERT episodes are what the evaluation metrics score, so the actuator's
    own count must agree with that definition."""
    b = Beeper(backend="silent")
    for state in (OK, ALERT, ALERT, ALERT, OK, ALERT):
        b.set_state(state)
    assert b.alert_entries == 2


def test_going_straight_from_ok_to_alert_raises_no_warn_chime() -> None:
    """The gentle cue must not fire on the way into an emergency -- on this mock
    the state does exactly this jump (README section 7)."""
    b = Beeper(backend="silent")
    b.set_state(OK)
    b.set_state(ALERT)
    assert b.warn_entries == 0
    assert b.alert_entries == 1


def test_the_alarm_thread_stops_and_close_is_idempotent() -> None:
    """An alarm still sounding after the demo ends is its own bug, and close()
    runs from a finally block, so calling it twice must be harmless."""
    with Beeper(backend="silent") as b:
        b.set_state(ALERT)
        thread = b._thread
        assert thread is not None and thread.is_alive()
    assert not thread.is_alive()
    b.close()


def test_silent_backend_binds_no_audio_device() -> None:
    """The guard that keeps CI quiet. The silent backend still *counts* what it
    would have played -- that is what makes it useful for a smoke test -- so the
    thing to assert is that no audio module was ever bound, not that the counters
    stayed at zero (they are incremented by the alarm thread, and asserting on
    them from here would race it)."""
    b = Beeper(backend="silent")
    assert b.backend == "silent"
    assert b._winsound is None
