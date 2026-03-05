"""Tests for in-conversation search functionality."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eavesdrop.app import EavesdropApp
from eavesdrop.widgets.conversation import ConversationView, _block_text
from eavesdrop.widgets.turn import AssistantTurn, FinalBlock, ToolCallBlock, ToolResultBlock, UserTurn
from eavesdrop.parser import ContentBlock, Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, lines: list[dict]) -> None:
    with open(path, "w") as f:
        for obj in lines:
            f.write(json.dumps(obj) + "\n")


def _write_plain_text_session(path: Path) -> None:
    """Session with user text and plain (non-final) assistant text."""
    _write_jsonl(path, [
        {"type": "session", "id": "s2", "timestamp": "2026-03-01T12:00:00.000Z", "cwd": "/tmp"},
        {
            "type": "message", "id": "u1", "parentId": None,
            "timestamp": "2026-03-01T12:00:02.000Z",
            "message": {"role": "user", "content": [
                {"type": "text", "text": "uniqueuserquery"}
            ], "timestamp": 1},
        },
        {
            "type": "message", "id": "a1", "parentId": "u1",
            "timestamp": "2026-03-01T12:00:03.000Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "uniqueassistantreply"}],
                "model": "test-model", "provider": "test",
                "usage": {"input": 10, "output": 5, "cacheRead": 0, "cacheWrite": 0,
                          "totalTokens": 15, "cost": {"total": 0}},
                "stopReason": "end_turn", "timestamp": 1,
            },
        },
    ])


def _write_search_session(path: Path) -> None:
    """Session with a ToolCallBlock (Bash), a FinalBlock, and a ToolResultBlock."""
    _write_jsonl(path, [
        {"type": "session", "id": "s1", "timestamp": "2026-03-01T12:00:00.000Z", "cwd": "/tmp"},
        {"type": "model_change", "id": "mc1", "parentId": None,
         "timestamp": "2026-03-01T12:00:01.000Z", "provider": "test", "modelId": "test-model"},
        {
            "type": "message", "id": "u1", "parentId": None,
            "timestamp": "2026-03-01T12:00:02.000Z",
            "message": {"role": "user", "content": [{"type": "text", "text": "list files"}], "timestamp": 1},
        },
        {
            "type": "message", "id": "a1", "parentId": "u1",
            "timestamp": "2026-03-01T12:00:03.000Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "toolCall", "id": "tc1", "name": "Bash",
                     "arguments": {"command": "ls -la /tmp"}},
                    {"type": "text", "text": "<final>listing complete</final>"},
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
                "role": "toolResult", "toolCallId": "tc1", "toolName": "Bash",
                "content": [{"type": "text", "text": "total 8\ndrwxrwxrwt 1 root root 4096 Mar  1 12:00 ."}],
                "isError": False, "details": {}, "timestamp": 1,
            },
        },
    ])


# ---------------------------------------------------------------------------
# Unit tests: _block_text
# ---------------------------------------------------------------------------

class TestBlockText:
    def test_tool_call_dict_args(self):
        block = ToolCallBlock("Bash", {"command": "ls -la /tmp"})
        text = _block_text(block)
        assert "Bash" in text
        assert "ls -la /tmp" in text

    def test_tool_call_string_args(self):
        block = ToolCallBlock("exec", "some command")
        text = _block_text(block)
        assert "exec" in text
        assert "some command" in text

    def test_tool_call_none_args(self):
        block = ToolCallBlock("noop", None)
        text = _block_text(block)
        assert "noop" in text

    def test_tool_result_content_text(self):
        msg = Message(
            id="tr1", parent_id=None, timestamp="t", role="toolResult",
            content=[ContentBlock(type="text", text="file output")],
            tool_call_id="tc1", tool_name="Bash",
        )
        block = ToolResultBlock(msg)
        text = _block_text(block)
        assert "Bash" in text
        assert "file output" in text

    def test_tool_result_prefers_aggregated(self):
        msg = Message(
            id="tr1", parent_id=None, timestamp="t", role="toolResult",
            content=[ContentBlock(type="text", text="raw content")],
            tool_call_id="tc1", tool_name="Bash",
            details={"aggregated": "summarized output"},
        )
        block = ToolResultBlock(msg)
        text = _block_text(block)
        assert "summarized output" in text
        assert "raw content" not in text

    def test_final_block(self):
        block = FinalBlock("listing complete")
        text = _block_text(block)
        assert text == "listing complete"

    def test_unknown_type_returns_empty(self):
        from textual.widget import Widget
        w = Widget()
        assert _block_text(w) == ""

    def test_user_turn_text(self):
        msg = Message(
            id="u1", parent_id=None, timestamp="t", role="user",
            content=[ContentBlock(type="text", text="please list files")],
        )
        block = UserTurn(msg)
        text = _block_text(block)
        assert "please list files" in text

    def test_assistant_turn_plain_text(self):
        msg = Message(
            id="a1", parent_id=None, timestamp="t", role="assistant",
            content=[ContentBlock(type="text", text="plain response here")],
        )
        block = AssistantTurn(msg)
        text = _block_text(block)
        assert "plain response here" in text

    def test_assistant_turn_excludes_final_blocks(self):
        msg = Message(
            id="a1", parent_id=None, timestamp="t", role="assistant",
            content=[ContentBlock(type="text", text="<final>final answer</final>")],
        )
        block = AssistantTurn(msg)
        text = _block_text(block)
        # <final> text should not appear in AssistantTurn's corpus (it has its own FinalBlock)
        assert text.strip() == ""


# ---------------------------------------------------------------------------
# Integration tests: search bar visibility and basic behaviour
# ---------------------------------------------------------------------------

class TestSearchBarVisibility:
    @pytest.mark.asyncio
    async def test_search_bar_hidden_by_default(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            bar = conv.query_one("#search-bar-row")
            assert bar.display is False

    @pytest.mark.asyncio
    async def test_slash_opens_search_bar(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            conv.focus()
            await pilot.press("slash")
            await pilot.pause()
            bar = conv.query_one("#search-bar-row")
            assert bar.display is True

    @pytest.mark.asyncio
    async def test_escape_closes_search_bar(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            conv.action_open_search()
            await pilot.pause()
            bar = conv.query_one("#search-bar-row")
            assert bar.display is True
            conv.action_close_search()
            await pilot.pause()
            assert bar.display is False

    @pytest.mark.asyncio
    async def test_escape_clears_search_state(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            # Manually set some state then close
            conv._search_matches = [object()]
            conv._search_index = 0
            conv._search_active = True
            conv.action_close_search()
            await pilot.pause()
            assert conv._search_matches == []
            assert conv._search_index == 0
            assert conv._search_active is False


# ---------------------------------------------------------------------------
# Integration tests: search results
# ---------------------------------------------------------------------------

class TestSearchResults:
    @pytest.mark.asyncio
    async def test_search_finds_tool_call_block(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            conv._run_search("ls -la")
            assert len(conv._search_matches) == 1
            assert isinstance(conv._search_matches[0], ToolCallBlock)

    @pytest.mark.asyncio
    async def test_search_finds_tool_result_block(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            conv._run_search("total 8")
            assert len(conv._search_matches) == 1
            assert isinstance(conv._search_matches[0], ToolResultBlock)

    @pytest.mark.asyncio
    async def test_search_finds_final_block(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            conv._run_search("listing complete")
            assert len(conv._search_matches) == 1
            assert isinstance(conv._search_matches[0], FinalBlock)

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            conv._run_search("LS -LA")
            assert len(conv._search_matches) == 1
            assert isinstance(conv._search_matches[0], ToolCallBlock)

    @pytest.mark.asyncio
    async def test_search_no_match(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            conv._run_search("xyzzy_no_such_thing")
            assert conv._search_matches == []

    @pytest.mark.asyncio
    async def test_match_expands_block(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            conv._run_search("ls -la")
            assert len(conv._search_matches) == 1
            assert conv._search_matches[0].expanded is True

    @pytest.mark.asyncio
    async def test_counter_shows_one_of_one(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            conv._search_active = True
            conv._run_search("ls -la")
            assert conv._search_index == 0
            assert len(conv._search_matches) == 1

    @pytest.mark.asyncio
    async def test_counter_shows_zero_on_no_match(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            conv._search_active = True
            conv._run_search("xyzzy_no_such_thing")
            assert conv._search_matches == []


# ---------------------------------------------------------------------------
# Integration tests: n/N navigation
# ---------------------------------------------------------------------------

class TestSearchNavigation:
    @pytest.mark.asyncio
    async def test_next_match_advances_index(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            # "Bash" matches ToolCallBlock and ToolResultBlock (2 matches)
            conv._run_search("bash")
            assert len(conv._search_matches) == 2
            assert conv._search_index == 0
            conv.action_next_match()
            assert conv._search_index == 1

    @pytest.mark.asyncio
    async def test_next_match_wraps(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            conv._run_search("bash")
            assert len(conv._search_matches) == 2
            conv.action_next_match()  # → 1
            conv.action_next_match()  # → 0 (wraps)
            assert conv._search_index == 0

    @pytest.mark.asyncio
    async def test_prev_match_wraps_to_last(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            conv._run_search("bash")
            assert len(conv._search_matches) == 2
            assert conv._search_index == 0
            conv.action_prev_match()  # (0 - 1) % 2 = 1
            assert conv._search_index == 1

    @pytest.mark.asyncio
    async def test_next_match_noop_when_no_results(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            conv._run_search("xyzzy_nothing")
            conv.action_next_match()
            assert conv._search_index == 0

    @pytest.mark.asyncio
    async def test_prev_match_noop_when_no_results(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            conv._run_search("xyzzy_nothing")
            conv.action_prev_match()
            assert conv._search_index == 0


# ---------------------------------------------------------------------------
# Integration tests: reload
# ---------------------------------------------------------------------------

class TestSearchCorpusExtension:
    @pytest.mark.asyncio
    async def test_search_finds_user_text(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_plain_text_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            conv._run_search("uniqueuserquery")
            assert len(conv._search_matches) == 1
            assert isinstance(conv._search_matches[0], UserTurn)

    @pytest.mark.asyncio
    async def test_search_finds_plain_assistant_text(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_plain_text_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            conv._run_search("uniqueassistantreply")
            assert len(conv._search_matches) == 1
            assert isinstance(conv._search_matches[0], AssistantTurn)

    @pytest.mark.asyncio
    async def test_search_in_collapsed_turn_expands_it(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            # Turns start collapsed — verify
            assert all(not sep.expanded for sep in conv._turn_separators)
            conv._run_search("ls -la")
            await pilot.pause()
            # The turn containing the match should now be expanded
            assert any(sep.expanded for sep in conv._turn_separators)


class TestSearchReload:
    @pytest.mark.asyncio
    async def test_reload_clears_search_matches(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_search_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            conv = app.query_one("#conversation", ConversationView)
            conv._run_search("bash")
            assert len(conv._search_matches) == 2
            conv.reload(p)
            await pilot.pause()
            assert conv._search_matches == []
            assert conv._search_index == 0
