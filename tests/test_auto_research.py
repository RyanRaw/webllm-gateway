from __future__ import annotations

import json
from pathlib import Path

from webai_gateway.auto_research import build_auto_research_status, collect_failure_fixtures, run_replay_report, write_failure_fixtures
from webai_gateway.tool_bridge_replay import run_replay_case


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")


def test_collects_failed_read_write_regression_from_claude_transcript(tmp_path: Path) -> None:
    transcript = tmp_path / "claude.jsonl"
    _write_jsonl(
        transcript,
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "/using-superpowers 按计划落地改进"},
                "timestamp": "2026-04-30T04:40:00Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_1",
                            "name": "Read",
                            "input": {"file_path": "E:/ProjectX/mindcraft/config/settings.py"},
                        }
                    ],
                },
                "timestamp": "2026-04-30T04:40:18Z",
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_1",
                            "is_error": True,
                            "content": "File does not exist. cookie=qwen_session_secret",
                        }
                    ],
                },
                "toolUseResult": "Error: File does not exist. cookie=qwen_session_secret",
                "timestamp": "2026-04-30T04:40:19Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_2",
                            "name": "Write",
                            "input": {
                                "file_path": "E:/ProjectX/mindcraft/tests/integration/test_full_workflow.py",
                                "content": "# unrelated guessed test",
                            },
                        }
                    ],
                },
                "timestamp": "2026-04-30T04:42:49Z",
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_2",
                            "content": "File created successfully at: E:/ProjectX/mindcraft/tests/integration/test_full_workflow.py",
                        }
                    ],
                },
                "timestamp": "2026-04-30T04:42:50Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_3",
                            "name": "Write",
                            "input": {"file_path": "config/settings.py", "content": "# guessed config"},
                        }
                    ],
                },
                "timestamp": "2026-04-30T04:46:48Z",
            },
        ],
    )

    cases = collect_failure_fixtures(transcript)

    assert [case.payload["id"] for case in cases] == ["claude_write_after_failed_read_without_discovery_044648"]
    payload = cases[0].payload
    assert payload["expected"]["error"] == "write_after_failed_read_without_discovery"
    assert payload["expected"]["tool_calls"] == []
    assert "qwen_session_secret" not in json.dumps(payload, ensure_ascii=False)
    actual = run_replay_case(cases[0])
    assert actual["error"] == "write_after_failed_read_without_discovery"


def test_writes_collected_fixtures_and_reports_replay_status(tmp_path: Path) -> None:
    transcript = tmp_path / "claude.jsonl"
    fixture_dir = tmp_path / "fixtures"
    _write_jsonl(
        transcript,
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "/using-superpowers 审查项目"},
                "timestamp": "2026-04-30T05:00:00Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_1",
                            "name": "Bash",
                            "input": {"command": "pip install -r requirements.txt"},
                        }
                    ],
                },
                "timestamp": "2026-04-30T05:00:20Z",
            },
        ],
    )

    written = write_failure_fixtures(collect_failure_fixtures(transcript), fixture_dir)
    report = run_replay_report(fixture_dir)

    assert len(written) == 1
    assert written[0].name == "claude_unsafe_local_shell_command_050020.json"
    assert report.total == 1
    assert report.passed == 1
    assert report.failed == 0
    assert report.failures == []


def test_builds_dashboard_status_from_replay_fixtures(tmp_path: Path) -> None:
    transcript = tmp_path / "claude.jsonl"
    fixture_dir = tmp_path / "fixtures"
    _write_jsonl(
        transcript,
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "/using-superpowers 审查项目"},
                "timestamp": "2026-04-30T05:00:00Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_1",
                            "name": "Bash",
                            "input": {"command": "pip install -r requirements.txt"},
                        }
                    ],
                },
                "timestamp": "2026-04-30T05:00:20Z",
            },
        ],
    )
    write_failure_fixtures(collect_failure_fixtures(transcript), fixture_dir)

    status = build_auto_research_status(fixture_dir)

    assert status["available"] is True
    assert status["total"] == 1
    assert status["passed"] == 1
    assert status["failed"] == 0
    assert status["passRate"] == 1
    assert status["failureKinds"] == [{"kind": "unsafe_local_shell_command", "count": 1}]
    assert status["taxonomy"] == {"unsafe_local_shell_command": 1}
    assert status["knownFixtureIds"] == ["claude_unsafe_local_shell_command_050020"]
    assert status["recent"][0]["id"] == "claude_unsafe_local_shell_command_050020"
    assert "collect" in status["collectCommand"]
