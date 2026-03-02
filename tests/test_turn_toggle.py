"""Tests for per-item tool call/result toggle via Enter key."""

import json
from pathlib import Path

import pytest

from eavesdrop.app import EavesdropApp
from eavesdrop.widgets.turn import ToolCallBlock, ToolResultBlock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, lines: list[dict]) -> None:
    with open(path, "w") as f:
        for obj in lines:
            f.write(json.dumps(obj) + "\n")


def _session_with_tool_call(path: Path) -> None:
    """Write a session with one assistant turn containing a tool call + result."""
    _write_jsonl(path, [
        {"type": "session", "id": "s1", "timestamp": "2026-03-01T12:00:00.000Z", "cwd": "/tmp"},
        {"type": "model_change", "id": "mc1", "parentId": None,
         "timestamp": "2026-03-01T12:00:01.000Z", "provider": "test", "modelId": "test-model"},
        {
            "type": "message", "id": "u1", "parentId": None,
            "timestamp": "2026-03-01T12:00:02.000Z",
            "message": {"role": "user", "content": [{"type": "text", "text": "run something"}], "timestamp": 1},
        },
        {
            "type": "message", "id": "a1", "parentId": "u1",
            "timestamp": "2026-03-01T12:00:03.000Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "toolCall", "id": "tc1", "name": "exec", "arguments": {"command": "ls"}},
                    {"type": "text", "text": "done"},
                ],
                "model": "test-model", "provider": "test",
                "usage": {"input": 10, "output": 5, "cacheRead": 0, "cacheWrite": 0,
                          "totalTokens": 15, "cost": {"input": 0, "output": 0,
                          "cacheRead": 0, "cacheWrite": 0, "total": 0}},
                "stopReason": "toolUse", "timestamp": 1,
            },
        },
        {
            "type": "message", "id": "tr1", "parentId": "a1",
            "timestamp": "2026-03-01T12:00:04.000Z",
            "message": {
                "role": "toolResult", "toolCallId": "tc1", "toolName": "exec",
                "content": [{"type": "text", "text": "file1.txt\nfile2.txt"}],
                "isError": False, "details": {}, "timestamp": 1,
            },
        },
    ])


# ---------------------------------------------------------------------------
# Unit: ToolCallBlock focusability and toggle
# ---------------------------------------------------------------------------

class TestToolCallBlockToggle:
    def test_can_focus_is_true(self):
        block = ToolCallBlock("exec", {"cmd": "ls"})
        assert block.can_focus is True

    def test_starts_collapsed(self):
        block = ToolCallBlock("exec", {"cmd": "ls"})
        assert block.expanded is False

    def test_toggle_method_expands(self):
        block = ToolCallBlock("exec", {"cmd": "ls"})
        block.toggle()
        assert block.expanded is True

    def test_toggle_method_collapses(self):
        block = ToolCallBlock("exec", {"cmd": "ls"})
        block.toggle()
        block.toggle()
        assert block.expanded is False

    def test_action_toggle_expands(self):
        block = ToolCallBlock("exec", {"cmd": "ls"})
        block.action_toggle()
        assert block.expanded is True

    def test_action_toggle_collapses(self):
        block = ToolCallBlock("exec", {"cmd": "ls"})
        block.action_toggle()
        block.action_toggle()
        assert block.expanded is False

    def test_has_enter_binding(self):
        keys = {b.key for b in ToolCallBlock.BINDINGS}
        assert "enter" in keys


# ---------------------------------------------------------------------------
# Unit: ToolResultBlock focusability and toggle
# ---------------------------------------------------------------------------

class TestToolResultBlockToggle:
    def _make_block(self):
        from eavesdrop.parser import Message, ContentBlock
        msg = Message(
            id="tr1", parent_id=None, timestamp="t", role="toolResult",
            content=[ContentBlock(type="text", text="output")],
            tool_call_id="tc1", tool_name="exec",
        )
        return ToolResultBlock(msg)

    def test_can_focus_is_true(self):
        assert self._make_block().can_focus is True

    def test_starts_collapsed(self):
        assert self._make_block().expanded is False

    def test_toggle_method_expands(self):
        block = self._make_block()
        block.toggle()
        assert block.expanded is True

    def test_action_toggle_expands(self):
        block = self._make_block()
        block.action_toggle()
        assert block.expanded is True

    def test_has_enter_binding(self):
        keys = {b.key for b in ToolResultBlock.BINDINGS}
        assert "enter" in keys


# ---------------------------------------------------------------------------
# Integration: Enter key toggles focused tool block in the running app
# ---------------------------------------------------------------------------

class TestPerItemToggleIntegration:
    @pytest.mark.asyncio
    async def test_enter_on_tool_call_block_toggles_it(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _session_with_tool_call(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            # Find the ToolCallBlock and focus it
            block = app.query_one(ToolCallBlock)
            assert block.expanded is False
            block.focus()
            await pilot.press("enter")
            assert block.expanded is True
            # Press again to collapse
            await pilot.press("enter")
            assert block.expanded is False

    @pytest.mark.asyncio
    async def test_enter_on_tool_result_block_toggles_it(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _session_with_tool_call(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            block = app.query_one(ToolResultBlock)
            assert block.expanded is False
            block.focus()
            await pilot.press("enter")
            assert block.expanded is True

    @pytest.mark.asyncio
    async def test_tool_block_toggle_independent_of_global_expand(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _session_with_tool_call(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            tc = app.query_one(ToolCallBlock)
            tr = app.query_one(ToolResultBlock)

            # Expand just the tool call individually
            tc.focus()
            await pilot.press("enter")
            assert tc.expanded is True
            assert tr.expanded is False  # result unaffected

    @pytest.mark.asyncio
    async def test_global_expand_collapses_all_on_second_press(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _session_with_tool_call(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            tc = app.query_one(ToolCallBlock)
            tr = app.query_one(ToolResultBlock)

            # First 'e' expands all
            await pilot.press("e")
            assert tc.expanded is True
            assert tr.expanded is True

            # Second 'e' collapses all, regardless of individual state
            await pilot.press("e")
            assert tc.expanded is False
            assert tr.expanded is False

    @pytest.mark.asyncio
    async def test_enter_without_focus_on_block_loads_session(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _session_with_tool_call(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            # Focus the browser, Enter should load (not crash)
            browser = app.query_one("#browser")
            browser.focus()
            tc = app.query_one(ToolCallBlock)
            was_expanded = tc.expanded
            await pilot.press("enter")
            # Tool block state should be unchanged by browser Enter
            assert tc.expanded == was_expanded
