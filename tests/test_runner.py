"""RunManager single-slot guard — the core concurrency constraint (one active run at a time).

Builds a fake 'running' slot directly (no model/thread) so the guard is tested deterministically.
"""
import time

import pytest

from ai_engineer_research.webui.runner import RunBusy, RunManager, _Slot


def test_second_start_raises_run_busy():
    rm = RunManager()
    rm._slot = _Slot(
        run_id="dra-x-m",
        topic="t",
        brief="",
        multi_agent=True,
        thoroughness="standard",
        started_at=time.time(),
        status="running",
    )
    with pytest.raises(RunBusy):
        rm.start("another topic")


def test_active_reports_running_slot():
    rm = RunManager()
    rm._slot = _Slot(
        run_id="dra-y-l",
        topic="hello",
        brief="",
        multi_agent=False,
        thoroughness="light",
        started_at=time.time(),
        status="running",
    )
    active = rm.active()
    assert active is not None
    assert active["run_id"] == "dra-y-l" and active["status"] == "running"
    assert active["multi_agent"] is False


def test_slot_fanout_and_backlog():
    slot = _Slot(run_id="r", topic="t", brief="", multi_agent=False, thoroughness="standard", started_at=0.0)
    q, snap = slot.subscribe()
    assert snap == []
    slot.emit({"type": "status", "text": "hi"})
    assert q.get_nowait() == {"type": "status", "text": "hi"}
    # a late subscriber replays the backlog
    _, snap2 = slot.subscribe()
    assert {"type": "status", "text": "hi"} in snap2
