"""Tests for 'y' yank-to-clipboard on ToolCallBlock."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from eavesdrop.app import EavesdropApp
from eavesdrop.widgets.turn import ToolCallBlock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, lines: list[dict]) -> None:
    with open(path, "w") as f:
        for obj in lines:
            f.write(json.dumps(obj) + "\n")


def _session_with_tool_call(path: Path, arguments: dict) -> None:
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
                    {"type": "toolCall", "id": "tc1", "name": "Bash", "arguments": arguments},
                ],
                "model": "test-model", "provider": "test",
                "usage": {"input": 10, "output": 5, "cacheRead": 0, "cacheWrite": 0,
                          "totalTokens": 15, "cost": {"input": 0, "output": 0,
                          "cacheRead": 0, "cacheWrite": 0, "total": 0}},
                "stopReason": "toolUse", "timestamp": 1,
            },
        },
    ])


# ---------------------------------------------------------------------------
# Unit: binding presence and action_copy logic (no app/pilot needed)
# ---------------------------------------------------------------------------

class TestToolCallBlockCopyUnit:
    def test_y_binding_present(self):
        keys = {b.key for b in ToolCallBlock.BINDINGS}
        assert "y" in keys

    def _mock_app(self):
        mock_app = MagicMock()
        mock_app.copy_to_clipboard = MagicMock()
        mock_app.notify = MagicMock()
        return mock_app

    def test_copy_action_with_command_key(self):
        block = ToolCallBlock("Bash", {"command": "ls -la"})
        mock_app = self._mock_app()
        with patch.object(type(block), "app", new_callable=PropertyMock, return_value=mock_app):
            block.action_copy()
        mock_app.copy_to_clipboard.assert_called_once_with("ls -la")

    def test_copy_action_no_command_key_is_noop(self):
        block = ToolCallBlock("Read", {"path": "/tmp/file.txt"})
        mock_app = self._mock_app()
        with patch.object(type(block), "app", new_callable=PropertyMock, return_value=mock_app):
            block.action_copy()
        mock_app.copy_to_clipboard.assert_not_called()

    def test_copy_action_string_args_is_noop(self):
        block = ToolCallBlock("Bash", "ls -la")
        mock_app = self._mock_app()
        with patch.object(type(block), "app", new_callable=PropertyMock, return_value=mock_app):
            block.action_copy()
        mock_app.copy_to_clipboard.assert_not_called()

    def test_copy_action_none_args_is_noop(self):
        block = ToolCallBlock("Bash", None)
        mock_app = self._mock_app()
        with patch.object(type(block), "app", new_callable=PropertyMock, return_value=mock_app):
            block.action_copy()
        mock_app.copy_to_clipboard.assert_not_called()

    def test_wayland_uses_wl_copy(self, monkeypatch):
        block = ToolCallBlock("Bash", {"command": "ls -la"})
        mock_app = self._mock_app()
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        with patch("subprocess.run") as mock_run, \
             patch.object(type(block), "app", new_callable=PropertyMock, return_value=mock_app):
            block.action_copy()
        mock_run.assert_called_once_with(
            ["wl-copy"], input=b"ls -la", check=True, timeout=2
        )
        mock_app.copy_to_clipboard.assert_called_once_with("ls -la")

    def test_wayland_wl_copy_failure_still_calls_osc52(self, monkeypatch):
        block = ToolCallBlock("Bash", {"command": "ls -la"})
        mock_app = self._mock_app()
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        with patch("subprocess.run", side_effect=FileNotFoundError), \
             patch.object(type(block), "app", new_callable=PropertyMock, return_value=mock_app):
            block.action_copy()
        mock_app.copy_to_clipboard.assert_called_once_with("ls -la")

    def test_no_wayland_skips_wl_copy(self, monkeypatch):
        block = ToolCallBlock("Bash", {"command": "ls -la"})
        mock_app = self._mock_app()
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        with patch("subprocess.run") as mock_run, \
             patch.object(type(block), "app", new_callable=PropertyMock, return_value=mock_app):
            block.action_copy()
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Integration: 'y' key in a running app
# ---------------------------------------------------------------------------

class TestToolCallBlockCopyIntegration:
    @pytest.mark.asyncio
    async def test_y_on_focused_block_copies_command(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _session_with_tool_call(p, {"command": "ls -la /tmp"})
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            block = app.query_one(ToolCallBlock)
            block.focus()
            await pilot.press("y")
            assert app.clipboard == "ls -la /tmp"

    @pytest.mark.asyncio
    async def test_y_on_collapsed_block_copies(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _session_with_tool_call(p, {"command": "echo hello"})
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            block = app.query_one(ToolCallBlock)
            assert block.expanded is False
            block.focus()
            await pilot.press("y")
            assert app.clipboard == "echo hello"

    @pytest.mark.asyncio
    async def test_y_on_expanded_block_copies(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _session_with_tool_call(p, {"command": "echo hello"})
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            block = app.query_one(ToolCallBlock)
            block.focus()
            await pilot.press("enter")
            assert block.expanded is True
            await pilot.press("y")
            assert app.clipboard == "echo hello"

    @pytest.mark.asyncio
    async def test_y_on_block_without_command_key_leaves_clipboard_unchanged(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _session_with_tool_call(p, {"path": "/tmp/file.txt"})
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            block = app.query_one(ToolCallBlock)
            block.focus()
            initial_clipboard = app.clipboard
            await pilot.press("y")
            assert app.clipboard == initial_clipboard
