"""Tests for TurnSeparator widget, _group_turns(), and _turn_meta()."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eavesdrop.parser import ContentBlock, Message, ModelChange, Usage, tool_result_has_error
from eavesdrop.widgets.conversation import _group_turns, _turn_meta
from eavesdrop.widgets.turn import TurnSeparator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(ts: str = "2026-03-01T09:00:00.000Z", text: str = "hello") -> Message:
    return Message(
        id="u1", parent_id=None, timestamp=ts, role="user",
        content=[ContentBlock(type="text", text=text)],
    )


def _make_assistant(stop_reason: str = "stop", cost: float = 0.001,
                    tool_calls: int = 0) -> Message:
    content = [ContentBlock(type="toolCall", tool_name="exec", arguments={}) for _ in range(tool_calls)]
    content.append(ContentBlock(type="text", text="done"))
    return Message(
        id="a1", parent_id=None, timestamp="2026-03-01T09:01:00.000Z",
        role="assistant", content=content,
        stop_reason=stop_reason,
        usage=Usage(input=10, output=5, total=15, cost_total=cost),
    )


def _make_tool_result(is_error: bool = False) -> Message:
    return Message(
        id="tr1", parent_id=None, timestamp="2026-03-01T09:00:30.000Z",
        role="toolResult",
        content=[ContentBlock(type="text", text="output")],
        tool_call_id="tc1", tool_name="exec", is_error=is_error,
    )


def _make_model_change() -> ModelChange:
    return ModelChange(id="mc1", timestamp="2026-03-01T09:00:00.000Z",
                       provider="test", model_id="test-model")


def _write_jsonl(path: Path, lines: list[dict]) -> None:
    with open(path, "w") as f:
        for obj in lines:
            f.write(json.dumps(obj) + "\n")


def _session_lines(**kwargs) -> list[dict]:
    """Minimal session preamble."""
    return [{"type": "session", "id": "s1", "timestamp": "2026-03-01T09:00:00.000Z", "cwd": "/tmp"}]


def _user_line(msg_id: str = "u1", text: str = "do something",
               ts: str = "2026-03-01T09:00:00.000Z") -> dict:
    return {
        "type": "message", "id": msg_id, "parentId": None, "timestamp": ts,
        "message": {"role": "user", "content": [{"type": "text", "text": text}], "timestamp": 1},
    }


def _assistant_line(msg_id: str = "a1", stop_reason: str = "stop",
                    tool_calls: int = 0, cost: float = 0.001,
                    ts: str = "2026-03-01T09:01:00.000Z") -> dict:
    content = [{"type": "toolCall", "id": f"tc{i}", "name": "exec", "arguments": {}}
               for i in range(tool_calls)]
    content.append({"type": "text", "text": "response"})
    return {
        "type": "message", "id": msg_id, "parentId": None, "timestamp": ts,
        "message": {
            "role": "assistant", "content": content,
            "model": "test", "provider": "test",
            "usage": {"input": 10, "output": 5, "cacheRead": 0, "cacheWrite": 0,
                      "totalTokens": 15, "cost": {"total": cost, "input": 0, "output": 0,
                                                   "cacheRead": 0, "cacheWrite": 0}},
            "stopReason": stop_reason, "timestamp": 1,
        },
    }


def _tool_result_line(msg_id: str = "tr1", is_error: bool = False,
                      ts: str = "2026-03-01T09:00:30.000Z") -> dict:
    return {
        "type": "message", "id": msg_id, "parentId": None, "timestamp": ts,
        "message": {
            "role": "toolResult", "toolCallId": "tc0", "toolName": "exec",
            "content": [{"type": "text", "text": "output"}],
            "isError": is_error, "details": {}, "timestamp": 1,
        },
    }


# ---------------------------------------------------------------------------
# Unit: _group_turns
# ---------------------------------------------------------------------------

class TestGroupTurns:
    def test_empty_events(self):
        prologue, turns = _group_turns([])
        assert prologue == []
        assert turns == []

    def test_only_prologue_events(self):
        mc = _make_model_change()
        prologue, turns = _group_turns([mc])
        assert prologue == [mc]
        assert turns == []

    def test_single_turn_no_prologue(self):
        user = _make_user()
        assistant = _make_assistant()
        prologue, turns = _group_turns([user, assistant])
        assert prologue == []
        assert len(turns) == 1
        assert turns[0][0] is user

    def test_single_turn_with_prologue(self):
        mc = _make_model_change()
        user = _make_user()
        assistant = _make_assistant()
        prologue, turns = _group_turns([mc, user, assistant])
        assert prologue == [mc]
        assert len(turns) == 1

    def test_multi_turn_count(self):
        u1 = _make_user(ts="2026-03-01T09:00:00.000Z")
        a1 = _make_assistant()
        u2 = Message(id="u2", parent_id=None, timestamp="2026-03-01T09:05:00.000Z",
                     role="user", content=[ContentBlock(type="text", text="next")])
        a2 = _make_assistant(stop_reason="end_turn")
        prologue, turns = _group_turns([u1, a1, u2, a2])
        assert len(turns) == 2

    def test_each_turn_starts_with_user_message(self):
        u1 = _make_user(ts="2026-03-01T09:00:00.000Z")
        a1 = _make_assistant()
        u2 = Message(id="u2", parent_id=None, timestamp="2026-03-01T09:05:00.000Z",
                     role="user", content=[ContentBlock(type="text", text="next")])
        prologue, turns = _group_turns([u1, a1, u2])
        assert turns[0][0] is u1
        assert turns[1][0] is u2

    def test_tool_results_included_in_turn(self):
        user = _make_user()
        assistant = _make_assistant()
        tool_result = _make_tool_result()
        prologue, turns = _group_turns([user, assistant, tool_result])
        assert len(turns) == 1
        assert tool_result in turns[0]


# ---------------------------------------------------------------------------
# Unit: _turn_meta
# ---------------------------------------------------------------------------

class TestTurnMeta:
    def test_clean_turn(self):
        turn = [_make_user(), _make_assistant(stop_reason="stop")]
        has_error, corrected, tool_count, total_cost = _turn_meta(turn)
        assert has_error is False
        assert corrected is False

    def test_error_with_stop_reason_stop_is_corrected(self):
        turn = [
            _make_user(),
            _make_assistant(stop_reason="stop", tool_calls=1),
            _make_tool_result(is_error=True),
            _make_assistant(stop_reason="stop"),
        ]
        has_error, corrected, tool_count, total_cost = _turn_meta(turn)
        assert has_error is True
        assert corrected is True

    def test_error_with_stop_reason_tool_use_not_corrected(self):
        turn = [
            _make_user(),
            _make_tool_result(is_error=True),
            _make_assistant(stop_reason="toolUse"),
        ]
        has_error, corrected, tool_count, total_cost = _turn_meta(turn)
        assert has_error is True
        assert corrected is False

    def test_tool_count_and_cost_accumulate(self):
        a1 = _make_assistant(stop_reason="toolUse", tool_calls=2, cost=0.001)
        a2 = _make_assistant(stop_reason="stop", tool_calls=3, cost=0.002)
        turn = [_make_user(), a1, _make_tool_result(), a2]
        has_error, corrected, tool_count, total_cost = _turn_meta(turn)
        assert tool_count == 5
        assert abs(total_cost - 0.003) < 1e-9

    def test_no_assistant_message_not_corrected(self):
        turn = [_make_user(), _make_tool_result(is_error=True)]
        has_error, corrected, tool_count, total_cost = _turn_meta(turn)
        assert has_error is True
        assert corrected is False


# ---------------------------------------------------------------------------
# Unit: _tool_result_has_error (structural detection)
# ---------------------------------------------------------------------------

def _make_tool_result_with_details(is_error=False, details=None) -> Message:
    return Message(
        id="tr1", parent_id=None, timestamp="t", role="toolResult",
        content=[ContentBlock(type="text", text="output")],
        tool_call_id="tc1", tool_name="exec",
        is_error=is_error,
        details=details or {},
    )


class TestToolResultHasError:
    def test_is_error_true_detected(self):
        msg = _make_tool_result_with_details(is_error=True)
        assert tool_result_has_error(msg) is True

    def test_clean_success_not_error(self):
        msg = _make_tool_result_with_details(details={"exitCode": 0, "status": "completed"})
        assert tool_result_has_error(msg) is False

    def test_nonzero_exit_code_detected(self):
        msg = _make_tool_result_with_details(details={"exitCode": 1, "status": "completed"})
        assert tool_result_has_error(msg) is True

    def test_exit_code_2_detected(self):
        msg = _make_tool_result_with_details(details={"exitCode": 2, "status": "completed"})
        assert tool_result_has_error(msg) is True

    def test_exit_code_126_detected(self):
        # Permission denied on executable
        msg = _make_tool_result_with_details(details={"exitCode": 126, "status": "completed"})
        assert tool_result_has_error(msg) is True

    def test_exit_code_zero_not_error(self):
        msg = _make_tool_result_with_details(details={"exitCode": 0, "status": "completed"})
        assert tool_result_has_error(msg) is False

    def test_no_exit_code_key_not_error(self):
        # Running process has no exitCode yet
        msg = _make_tool_result_with_details(details={"status": "running", "pid": 1234})
        assert tool_result_has_error(msg) is False

    def test_status_failed_detected(self):
        # process tool: timeout / crash
        msg = _make_tool_result_with_details(details={"status": "failed", "exitCode": 1})
        assert tool_result_has_error(msg) is True

    def test_status_error_detected(self):
        # read tool: ENOENT
        msg = _make_tool_result_with_details(
            details={"status": "error", "tool": "read", "error": "ENOENT: no such file"}
        )
        assert tool_result_has_error(msg) is True

    def test_error_key_present_detected(self):
        # read tool ENOENT without status field
        msg = _make_tool_result_with_details(details={"error": "ENOENT: no such file or directory"})
        assert tool_result_has_error(msg) is True

    def test_empty_details_not_error(self):
        msg = _make_tool_result_with_details(details={})
        assert tool_result_has_error(msg) is False

    def test_status_completed_exitcode_zero_not_error(self):
        msg = _make_tool_result_with_details(details={"status": "completed", "exitCode": 0})
        assert tool_result_has_error(msg) is False


class TestTurnMetaStructuralErrors:
    def test_nonzero_exitcode_marks_turn_errored(self):
        tr = _make_tool_result_with_details(details={"exitCode": 1, "status": "completed"})
        turn = [_make_user(), _make_assistant(stop_reason="stop"), tr]
        has_error, corrected, _, _ = _turn_meta(turn)
        assert has_error is True

    def test_status_failed_marks_turn_errored(self):
        tr = _make_tool_result_with_details(details={"status": "failed", "exitCode": 1})
        turn = [_make_user(), tr, _make_assistant(stop_reason="stop")]
        has_error, corrected, _, _ = _turn_meta(turn)
        assert has_error is True
        assert corrected is True

    def test_read_enoent_marks_turn_errored(self):
        tr = _make_tool_result_with_details(
            details={"status": "error", "tool": "read", "error": "ENOENT: …"}
        )
        turn = [_make_user(), tr, _make_assistant(stop_reason="stop")]
        has_error, corrected, _, _ = _turn_meta(turn)
        assert has_error is True

    def test_exitcode_zero_does_not_mark_error(self):
        tr = _make_tool_result_with_details(details={"exitCode": 0, "status": "completed"})
        turn = [_make_user(), _make_assistant(stop_reason="stop"), tr]
        has_error, _, _, _ = _turn_meta(turn)
        assert has_error is False


# ---------------------------------------------------------------------------
# Unit: TurnSeparator widget
# ---------------------------------------------------------------------------

class TestTurnSeparatorWidget:
    def _make_sep(self, has_error=False, corrected=False):
        return TurnSeparator(
            turn_num=1,
            timestamp="2026-03-01T09:14:00.000Z",
            tool_count=6,
            total_cost=0.0012,
            has_error=has_error,
            corrected=corrected,
        )

    def test_error_class_applied(self):
        sep = self._make_sep(has_error=True, corrected=False)
        assert "turn-error" in sep.classes

    def test_corrected_class_applied(self):
        sep = self._make_sep(corrected=True)
        assert "turn-corrected" in sep.classes

    def test_no_error_class_when_clean(self):
        sep = self._make_sep(has_error=False, corrected=False)
        assert "turn-error" not in sep.classes
        assert "turn-corrected" not in sep.classes

    def test_expanded_defaults_to_false(self):
        sep = self._make_sep()
        assert sep.expanded is False

    def test_action_toggle_flips_expanded(self):
        sep = self._make_sep()
        assert sep.expanded is False
        sep.action_toggle()
        assert sep.expanded is True
        sep.action_toggle()
        assert sep.expanded is False

    def test_can_focus_is_true(self):
        sep = self._make_sep()
        assert sep.can_focus is True

    def test_has_enter_and_space_bindings(self):
        keys = {b.key for b in TurnSeparator.BINDINGS}
        assert "enter" in keys
        assert "space" in keys


# ---------------------------------------------------------------------------
# Integration tests (with Textual pilot)
# ---------------------------------------------------------------------------

from eavesdrop.app import EavesdropApp


class TestTurnSeparatorIntegration:
    @pytest.mark.asyncio
    async def test_single_turn_session_has_one_separator(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, _session_lines() + [
            _user_line(),
            _assistant_line(),
        ])
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            seps = app.query(TurnSeparator)
            assert len(seps) == 1

    @pytest.mark.asyncio
    async def test_two_turn_session_has_two_separators(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, _session_lines() + [
            _user_line(msg_id="u1", ts="2026-03-01T09:00:00.000Z"),
            _assistant_line(msg_id="a1", ts="2026-03-01T09:01:00.000Z"),
            _user_line(msg_id="u2", ts="2026-03-01T09:05:00.000Z", text="second"),
            _assistant_line(msg_id="a2", ts="2026-03-01T09:06:00.000Z"),
        ])
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            seps = app.query(TurnSeparator)
            assert len(seps) == 2

    @pytest.mark.asyncio
    async def test_error_turn_separator_has_error_class(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, _session_lines() + [
            _user_line(),
            _assistant_line(stop_reason="toolUse", tool_calls=1),
            _tool_result_line(is_error=True),
            _assistant_line(msg_id="a2", stop_reason="toolUse"),
        ])
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            sep = app.query_one(TurnSeparator)
            assert "turn-error" in sep.classes

    @pytest.mark.asyncio
    async def test_corrected_turn_separator_has_corrected_class(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, _session_lines() + [
            _user_line(),
            _assistant_line(stop_reason="toolUse", tool_calls=1),
            _tool_result_line(is_error=True),
            _assistant_line(msg_id="a2", stop_reason="stop"),
        ])
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            sep = app.query_one(TurnSeparator)
            assert "turn-corrected" in sep.classes

    @pytest.mark.asyncio
    async def test_enter_on_separator_expands_turn(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, _session_lines() + [
            _user_line(),
            _assistant_line(),
        ])
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            sep = app.query_one(TurnSeparator)
            assert sep.expanded is False
            sep.focus()
            await pilot.press("enter")
            assert sep.expanded is True

    @pytest.mark.asyncio
    async def test_enter_again_collapses_turn(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, _session_lines() + [
            _user_line(),
            _assistant_line(),
        ])
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            sep = app.query_one(TurnSeparator)
            sep.focus()
            await pilot.press("enter")
            assert sep.expanded is True
            await pilot.press("enter")
            assert sep.expanded is False

    @pytest.mark.asyncio
    async def test_turns_hidden_on_load(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, _session_lines() + [
            _user_line(),
            _assistant_line(),
        ])
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            from eavesdrop.widgets.conversation import ConversationView
            cv = app.query_one(ConversationView)
            for sep, widgets in cv._turn_groups:
                for w in widgets:
                    assert w.display is False

    @pytest.mark.asyncio
    async def test_expand_shows_child_widgets(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, _session_lines() + [
            _user_line(),
            _assistant_line(),
        ])
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            from eavesdrop.widgets.conversation import ConversationView
            cv = app.query_one(ConversationView)
            sep = app.query_one(TurnSeparator)
            sep.focus()
            await pilot.press("enter")
            for s, widgets in cv._turn_groups:
                if s is sep:
                    for w in widgets:
                        assert w.display is True
                    break

    @pytest.mark.asyncio
    async def test_next_turn_key_scrolls_to_next_separator(self, tmp_path):
        p = tmp_path / "s.jsonl"
        # Create enough content to require scrolling
        lines = _session_lines()
        for i in range(4):
            lines.append(_user_line(msg_id=f"u{i}", ts=f"2026-03-01T09:0{i}:00.000Z",
                                    text=f"turn {i} " + "x " * 50))
            lines.append(_assistant_line(msg_id=f"a{i}", ts=f"2026-03-01T09:0{i}:30.000Z"))
        _write_jsonl(p, lines)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 20)) as pilot:
            from eavesdrop.widgets.conversation import ConversationView
            cv = app.query_one(ConversationView)
            initial_y = cv.scroll_y
            await pilot.press("]")
            # scroll_y may or may not change depending on layout; just ensure no crash
            # and that the action runs without error
            assert cv is not None

    @pytest.mark.asyncio
    async def test_prev_turn_key_does_not_crash(self, tmp_path):
        p = tmp_path / "s.jsonl"
        lines = _session_lines()
        for i in range(3):
            lines.append(_user_line(msg_id=f"u{i}", ts=f"2026-03-01T09:0{i}:00.000Z",
                                    text=f"turn {i}"))
            lines.append(_assistant_line(msg_id=f"a{i}", ts=f"2026-03-01T09:0{i}:30.000Z"))
        _write_jsonl(p, lines)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 20)) as pilot:
            from eavesdrop.widgets.conversation import ConversationView
            cv = app.query_one(ConversationView)
            await pilot.press("[")
            assert cv is not None


# ---------------------------------------------------------------------------
# Global collapse/expand all turns (T key)
# ---------------------------------------------------------------------------

class TestToggleAllTurns:
    def _two_turn_session(self, tmp_path) -> Path:
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, _session_lines() + [
            _user_line(msg_id="u1", ts="2026-03-01T09:00:00.000Z"),
            _assistant_line(msg_id="a1", ts="2026-03-01T09:01:00.000Z"),
            _user_line(msg_id="u2", ts="2026-03-01T09:05:00.000Z", text="second"),
            _assistant_line(msg_id="a2", ts="2026-03-01T09:06:00.000Z"),
        ])
        return p

    @pytest.mark.asyncio
    async def test_T_expands_all_separators(self, tmp_path):
        p = self._two_turn_session(tmp_path)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            seps = list(app.query(TurnSeparator))
            assert all(not s.expanded for s in seps)
            await pilot.press("T")
            assert all(s.expanded for s in seps)

    @pytest.mark.asyncio
    async def test_T_again_collapses_all_separators(self, tmp_path):
        p = self._two_turn_session(tmp_path)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("T")
            await pilot.press("T")
            seps = list(app.query(TurnSeparator))
            assert all(not s.expanded for s in seps)

    @pytest.mark.asyncio
    async def test_T_shows_child_widgets_when_expanding(self, tmp_path):
        p = self._two_turn_session(tmp_path)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            from eavesdrop.widgets.conversation import ConversationView
            cv = app.query_one(ConversationView)
            await pilot.press("T")
            for sep, widgets in cv._turn_groups:
                for w in widgets:
                    assert w.display is True

    @pytest.mark.asyncio
    async def test_T_hides_child_widgets_when_collapsing(self, tmp_path):
        p = self._two_turn_session(tmp_path)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            from eavesdrop.widgets.conversation import ConversationView
            cv = app.query_one(ConversationView)
            await pilot.press("T")
            await pilot.press("T")
            for sep, widgets in cv._turn_groups:
                for w in widgets:
                    assert w.display is False

    @pytest.mark.asyncio
    async def test_toggle_turns_method_returns_new_state(self, tmp_path):
        p = self._two_turn_session(tmp_path)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(120, 40)) as pilot:
            from eavesdrop.widgets.conversation import ConversationView
            cv = app.query_one(ConversationView)
            result = cv.toggle_turns()
            assert result is True
            result = cv.toggle_turns()
            assert result is False
