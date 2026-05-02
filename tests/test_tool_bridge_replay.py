from __future__ import annotations

from pathlib import Path

import pytest

from webai_gateway.tool_bridge_replay import ReplayCase, load_replay_cases, run_replay_case


REPLAY_ROOT = Path(__file__).parent / "fixtures" / "tool_bridge_replays"


def test_tool_bridge_replay_suite_covers_minimum_real_failures() -> None:
    assert len(load_replay_cases(REPLAY_ROOT)) >= 10


@pytest.mark.parametrize("case", load_replay_cases(REPLAY_ROOT), ids=lambda case: case.id)
def test_tool_bridge_replay_case(case: ReplayCase) -> None:
    actual = run_replay_case(case)
    expected = case.payload["expected"]
    assert actual["error"] == expected["error"], case.id
    assert actual["tool_calls"] == expected["tool_calls"], case.id
    warning_contains = expected.get("warning_contains")
    if warning_contains:
        assert actual["warning"] and warning_contains in actual["warning"], case.id
    else:
        assert actual["warning"] is None, case.id
