"""Tests for follow/live mode (Milestone 2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eavesdrop.app import EavesdropApp
from eavesdrop.widgets.conversation import ConversationView


def _write_jsonl(path: Path, lines: list[dict]) -> None:
    with open(path, "w") as f:
        for obj in lines:
            f.write(json.dumps(obj) + "\n")


def _minimal_session(path: Path) -> None:
    _write_jsonl(path, [
        {"type": "session", "id": "test-id", "timestamp": "2026-03-01T12:00:00.000Z", "cwd": "/tmp"},
        {
            "type": "message", "id": "u1", "parentId": None, "timestamp": "2026-03-01T12:00:02.000Z",
            "message": {"role": "user", "content": [{"type": "text", "text": "hello"}], "timestamp": 1},
        },
        {
            "type": "message", "id": "a1", "parentId": "u1", "timestamp": "2026-03-01T12:00:03.000Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "hi"}],
                "model": "test-model", "provider": "test",
                "usage": {"input": 10, "output": 5, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 15,
                          "cost": {"input": 0.001, "output": 0.0005, "cacheRead": 0, "cacheWrite": 0, "total": 0.0015}},
                "stopReason": "end_turn", "timestamp": 1,
            },
        },
    ])


# ---------------------------------------------------------------------------
# append_new_lines unit tests
# ---------------------------------------------------------------------------

class TestAppendNewLines:
    @pytest.mark.asyncio
    async def test_append_adds_new_user_message(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _minimal_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            from eavesdrop.widgets.turn import UserTurn
            initial_user_count = len(list(conv.query(UserTurn)))

            # Append a new user message to the file
            with open(p, "a") as f:
                new_msg = {
                    "type": "message", "id": "u2", "parentId": "a1",
                    "timestamp": "2026-03-01T12:00:10.000Z",
                    "message": {"role": "user", "content": [{"type": "text", "text": "more"}], "timestamp": 2},
                }
                f.write(json.dumps(new_msg) + "\n")

            conv.append_new_lines(p)
            await pilot.pause()
            new_user_count = len(list(conv.query(UserTurn)))
            assert new_user_count == initial_user_count + 1

    @pytest.mark.asyncio
    async def test_append_noop_when_file_unchanged(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _minimal_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            from eavesdrop.widgets.turn import UserTurn
            initial_count = len(list(conv.query(UserTurn)))
            conv.append_new_lines(p)
            await pilot.pause()
            assert len(list(conv.query(UserTurn))) == initial_count

    @pytest.mark.asyncio
    async def test_append_adds_tool_result(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _minimal_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            from eavesdrop.widgets.turn import ToolResultBlock
            initial_count = len(list(conv.query(ToolResultBlock)))

            with open(p, "a") as f:
                tr = {
                    "type": "message", "id": "tr1", "parentId": "a1",
                    "timestamp": "2026-03-01T12:00:11.000Z",
                    "message": {
                        "role": "toolResult", "toolCallId": "tc1", "toolName": "exec",
                        "content": [{"type": "text", "text": "result"}],
                        "isError": False, "details": {}, "timestamp": 2,
                    },
                }
                f.write(json.dumps(tr) + "\n")

            conv.append_new_lines(p)
            await pilot.pause()
            assert len(list(conv.query(ToolResultBlock))) == initial_count + 1


# ---------------------------------------------------------------------------
# Follow mode toggle tests
# ---------------------------------------------------------------------------

class TestFollowMode:
    @pytest.mark.asyncio
    async def test_follow_toggle_starts_disabled(self, tmp_path):
        app = EavesdropApp(sessions_dir=tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            assert app._follow_mode is False

    @pytest.mark.asyncio
    async def test_f_key_enables_follow_mode(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _minimal_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("f")
            assert app._follow_mode is True

    @pytest.mark.asyncio
    async def test_f_key_toggles_follow_off(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _minimal_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("f")
            await pilot.press("f")
            assert app._follow_mode is False

    @pytest.mark.asyncio
    async def test_follow_subtitle_shows_indicator(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _minimal_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("f")
            assert "[FOLLOW]" in app.sub_title

    @pytest.mark.asyncio
    async def test_follow_subtitle_clears_on_disable(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _minimal_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("f")
            await pilot.press("f")
            assert "[FOLLOW]" not in app.sub_title


# ---------------------------------------------------------------------------
# is_near_bottom tests
# ---------------------------------------------------------------------------

class TestIsNearBottom:
    @pytest.mark.asyncio
    async def test_near_bottom_true_when_at_top_of_empty(self, tmp_path):
        app = EavesdropApp(sessions_dir=tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            assert conv._is_near_bottom() is True
