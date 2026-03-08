"""Tests for eavesdrop.parser."""

import json
import time
from pathlib import Path

import pytest

from eavesdrop.parser import (
    ContentBlock,
    Message,
    ModelChange,
    ParsedSession,
    SessionMeta,
    Usage,
    parse_file,
    scan_sessions,
    session_summary,
    session_uuid,
    tool_result_has_error,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, lines: list[dict]) -> None:
    with open(path, "w") as f:
        for obj in lines:
            f.write(json.dumps(obj) + "\n")


def _session_event(session_id: str = "abc123", cwd: str = "/tmp") -> dict:
    return {
        "type": "session",
        "id": session_id,
        "timestamp": "2026-03-01T12:00:00.000Z",
        "cwd": cwd,
    }


def _model_change_event(model_id: str = "gemini-3-flash", provider: str = "google") -> dict:
    return {
        "type": "model_change",
        "id": "mc1",
        "parentId": None,
        "timestamp": "2026-03-01T12:00:01.000Z",
        "provider": provider,
        "modelId": model_id,
    }


def _user_message(msg_id: str = "u1", text: str = "Hello") -> dict:
    return {
        "type": "message",
        "id": msg_id,
        "parentId": None,
        "timestamp": "2026-03-01T12:00:02.000Z",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": text}],
            "timestamp": 1000,
        },
    }


def _assistant_message(
    msg_id: str = "a1",
    text: str = "Hi there",
    thinking: str = "",
    tool_calls: list[dict] | None = None,
    usage: dict | None = None,
    stop_reason: str = "end_turn",
) -> dict:
    content = []
    if thinking:
        content.append({"type": "thinking", "thinking": thinking})
    if tool_calls:
        content.extend(tool_calls)
    if text:
        content.append({"type": "text", "text": text})
    return {
        "type": "message",
        "id": msg_id,
        "parentId": None,
        "timestamp": "2026-03-01T12:00:03.000Z",
        "message": {
            "role": "assistant",
            "content": content,
            "model": "gemini-3-flash",
            "provider": "google",
            "usage": usage or {
                "input": 100,
                "output": 50,
                "cacheRead": 10,
                "cacheWrite": 0,
                "totalTokens": 160,
                "cost": {"input": 0.01, "output": 0.005, "cacheRead": 0.0, "cacheWrite": 0.0, "total": 0.015},
            },
            "stopReason": stop_reason,
            "timestamp": 1000,
        },
    }


def _tool_result_message(tool_name: str = "exec", tool_call_id: str = "tc1", text: str = "result", is_error: bool = False, details: dict | None = None) -> dict:
    return {
        "type": "message",
        "id": "tr1",
        "parentId": "a1",
        "timestamp": "2026-03-01T12:00:04.000Z",
        "message": {
            "role": "toolResult",
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
            "details": details or {},
            "timestamp": 1000,
        },
    }


# ---------------------------------------------------------------------------
# parse_file — basic structure
# ---------------------------------------------------------------------------

class TestParseFileBasic:
    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        result = parse_file(p)
        assert result.meta is None
        assert result.events == []

    def test_blank_lines_ignored(self, tmp_path):
        p = tmp_path / "blanks.jsonl"
        p.write_text("\n\n\n")
        result = parse_file(p)
        assert result.meta is None
        assert result.events == []

    def test_malformed_json_skipped(self, tmp_path):
        p = tmp_path / "bad.jsonl"
        p.write_text('{"type": "session", "id": "x", "timestamp": "t", "cwd": "/"}\nnot json\n')
        result = parse_file(p)
        assert result.meta is not None
        assert result.events == []

    def test_session_meta_parsed(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_session_event("myid", "/home/user")])
        result = parse_file(p)
        assert isinstance(result.meta, SessionMeta)
        assert result.meta.id == "myid"
        assert result.meta.cwd == "/home/user"
        assert result.meta.timestamp == "2026-03-01T12:00:00.000Z"

    def test_unknown_event_types_ignored(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [
            _session_event(),
            {"type": "thinking_level_change", "id": "x", "thinkingLevel": "low"},
            {"type": "custom", "customType": "model-snapshot", "data": {}},
        ])
        result = parse_file(p)
        assert result.events == []


# ---------------------------------------------------------------------------
# parse_file — model_change
# ---------------------------------------------------------------------------

class TestParseFileModelChange:
    def test_model_change_parsed(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_model_change_event("gpt-4o", "openai")])
        result = parse_file(p)
        assert len(result.events) == 1
        mc = result.events[0]
        assert isinstance(mc, ModelChange)
        assert mc.model_id == "gpt-4o"
        assert mc.provider == "openai"

    def test_multiple_model_changes(self, tmp_path):
        p = tmp_path / "s.jsonl"
        mc1 = _model_change_event("model-a", "google")
        mc2 = {**mc1, "id": "mc2", "modelId": "model-b", "provider": "anthropic"}
        _write_jsonl(p, [mc1, mc2])
        result = parse_file(p)
        assert len(result.events) == 2
        assert result.events[0].model_id == "model-a"
        assert result.events[1].model_id == "model-b"


# ---------------------------------------------------------------------------
# parse_file — user messages
# ---------------------------------------------------------------------------

class TestParseFileUserMessages:
    def test_user_text_content(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_user_message(text="Hello world")])
        result = parse_file(p)
        assert len(result.events) == 1
        msg = result.events[0]
        assert isinstance(msg, Message)
        assert msg.role == "user"
        assert len(msg.content) == 1
        assert msg.content[0].type == "text"
        assert msg.content[0].text == "Hello world"

    def test_user_message_no_usage(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_user_message()])
        result = parse_file(p)
        assert result.events[0].usage is None

    def test_user_empty_content(self, tmp_path):
        p = tmp_path / "s.jsonl"
        event = {
            "type": "message",
            "id": "u1",
            "parentId": None,
            "timestamp": "t",
            "message": {"role": "user", "content": [], "timestamp": 1},
        }
        _write_jsonl(p, [event])
        result = parse_file(p)
        assert result.events[0].content == []

    def test_user_message_ids(self, tmp_path):
        p = tmp_path / "s.jsonl"
        event = {
            "type": "message",
            "id": "msg-xyz",
            "parentId": "parent-abc",
            "timestamp": "2026-01-01T00:00:00.000Z",
            "message": {"role": "user", "content": [], "timestamp": 1},
        }
        _write_jsonl(p, [event])
        result = parse_file(p)
        msg = result.events[0]
        assert msg.id == "msg-xyz"
        assert msg.parent_id == "parent-abc"


# ---------------------------------------------------------------------------
# parse_file — assistant messages
# ---------------------------------------------------------------------------

class TestParseFileAssistantMessages:
    def test_assistant_text(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_assistant_message(text="Response text")])
        result = parse_file(p)
        msg = result.events[0]
        assert msg.role == "assistant"
        text_blocks = [c for c in msg.content if c.type == "text"]
        assert any(b.text == "Response text" for b in text_blocks)

    def test_assistant_thinking_block(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_assistant_message(thinking="my thoughts", text="")])
        result = parse_file(p)
        msg = result.events[0]
        thinking_blocks = [c for c in msg.content if c.type == "thinking"]
        assert len(thinking_blocks) == 1
        assert thinking_blocks[0].thinking == "my thoughts"

    def test_assistant_tool_call_block(self, tmp_path):
        p = tmp_path / "s.jsonl"
        tool_call = {
            "type": "toolCall",
            "id": "tc_001",
            "name": "exec",
            "arguments": {"command": "ls -la"},
        }
        _write_jsonl(p, [_assistant_message(tool_calls=[tool_call], text="")])
        result = parse_file(p)
        msg = result.events[0]
        tc_blocks = [c for c in msg.content if c.type == "toolCall"]
        assert len(tc_blocks) == 1
        assert tc_blocks[0].tool_name == "exec"
        assert tc_blocks[0].tool_call_id == "tc_001"
        assert tc_blocks[0].arguments == {"command": "ls -la"}

    def test_assistant_multiple_content_blocks(self, tmp_path):
        p = tmp_path / "s.jsonl"
        tool_call = {"type": "toolCall", "id": "tc1", "name": "read", "arguments": {"path": "/etc"}}
        _write_jsonl(p, [_assistant_message(thinking="think", tool_calls=[tool_call], text="done")])
        result = parse_file(p)
        msg = result.events[0]
        types = [c.type for c in msg.content]
        assert "thinking" in types
        assert "toolCall" in types
        assert "text" in types

    def test_assistant_usage_parsed(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_assistant_message()])
        result = parse_file(p)
        usage = result.events[0].usage
        assert isinstance(usage, Usage)
        assert usage.input == 100
        assert usage.output == 50
        assert usage.cache_read == 10
        assert usage.total == 160
        assert abs(usage.cost_total - 0.015) < 1e-9

    def test_assistant_usage_missing(self, tmp_path):
        p = tmp_path / "s.jsonl"
        event = _assistant_message()
        event["message"]["usage"] = None
        _write_jsonl(p, [event])
        result = parse_file(p)
        assert result.events[0].usage is None

    def test_assistant_stop_reason_and_model(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_assistant_message(stop_reason="toolUse")])
        result = parse_file(p)
        msg = result.events[0]
        assert msg.stop_reason == "toolUse"
        assert msg.model == "gemini-3-flash"
        assert msg.provider == "google"


# ---------------------------------------------------------------------------
# parse_file — toolResult messages
# ---------------------------------------------------------------------------

class TestParseFileToolResults:
    def test_tool_result_basic(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_tool_result_message(tool_name="exec", text="output text")])
        result = parse_file(p)
        msg = result.events[0]
        assert isinstance(msg, Message)
        assert msg.role == "toolResult"
        assert msg.tool_name == "exec"
        text_blocks = [c for c in msg.content if c.type == "text"]
        assert text_blocks[0].text == "output text"

    def test_tool_result_is_error_flag(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_tool_result_message(is_error=True)])
        result = parse_file(p)
        assert result.events[0].is_error is True

    def test_tool_result_not_error_by_default(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_tool_result_message(is_error=False)])
        result = parse_file(p)
        assert result.events[0].is_error is False

    def test_tool_result_details_aggregated(self, tmp_path):
        p = tmp_path / "s.jsonl"
        details = {"aggregated": "summarized output", "ok": True}
        _write_jsonl(p, [_tool_result_message(details=details)])
        result = parse_file(p)
        assert result.events[0].details["aggregated"] == "summarized output"

    def test_tool_result_tool_call_id(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_tool_result_message(tool_call_id="tc_xyz")])
        result = parse_file(p)
        assert result.events[0].tool_call_id == "tc_xyz"


# ---------------------------------------------------------------------------
# parse_file — content block edge cases
# ---------------------------------------------------------------------------

class TestContentBlockEdgeCases:
    def test_unknown_content_type_with_text_preserved(self, tmp_path):
        p = tmp_path / "s.jsonl"
        event = {
            "type": "message",
            "id": "u1",
            "parentId": None,
            "timestamp": "t",
            "message": {
                "role": "user",
                "content": [{"type": "image_url", "text": "fallback text"}],
                "timestamp": 1,
            },
        }
        _write_jsonl(p, [event])
        result = parse_file(p)
        # unknown type with a text field → preserved as text block
        blocks = result.events[0].content
        assert any(b.text == "fallback text" for b in blocks)

    def test_unknown_content_type_without_text_dropped(self, tmp_path):
        p = tmp_path / "s.jsonl"
        event = {
            "type": "message",
            "id": "u1",
            "parentId": None,
            "timestamp": "t",
            "message": {
                "role": "user",
                "content": [{"type": "image_url", "url": "http://example.com/img.png"}],
                "timestamp": 1,
            },
        }
        _write_jsonl(p, [event])
        result = parse_file(p)
        assert result.events[0].content == []

    def test_tool_call_with_none_arguments(self, tmp_path):
        p = tmp_path / "s.jsonl"
        tool_call = {"type": "toolCall", "id": "tc1", "name": "noop", "arguments": None}
        _write_jsonl(p, [_assistant_message(tool_calls=[tool_call], text="")])
        result = parse_file(p)
        tc = next(c for c in result.events[0].content if c.type == "toolCall")
        assert tc.arguments is None

    def test_tool_call_with_string_arguments(self, tmp_path):
        p = tmp_path / "s.jsonl"
        tool_call = {"type": "toolCall", "id": "tc1", "name": "run", "arguments": '{"cmd": "ls"}'}
        _write_jsonl(p, [_assistant_message(tool_calls=[tool_call], text="")])
        result = parse_file(p)
        tc = next(c for c in result.events[0].content if c.type == "toolCall")
        assert tc.arguments == '{"cmd": "ls"}'


# ---------------------------------------------------------------------------
# parse_file — mixed full session
# ---------------------------------------------------------------------------

class TestParseFileFullSession:
    def test_full_session_event_ordering(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [
            _session_event(),
            _model_change_event(),
            _user_message(),
            _assistant_message(),
            _tool_result_message(),
        ])
        result = parse_file(p)
        assert isinstance(result.meta, SessionMeta)
        assert len(result.events) == 4  # model_change + user + assistant + toolResult
        assert isinstance(result.events[0], ModelChange)
        assert result.events[1].role == "user"
        assert result.events[2].role == "assistant"
        assert result.events[3].role == "toolResult"

    def test_parent_id_preserved(self, tmp_path):
        p = tmp_path / "s.jsonl"
        event = _user_message()
        event["parentId"] = "parent-001"
        _write_jsonl(p, [event])
        result = parse_file(p)
        assert result.events[0].parent_id == "parent-001"

    def test_null_parent_id(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_user_message()])
        result = parse_file(p)
        assert result.events[0].parent_id is None


# ---------------------------------------------------------------------------
# scan_sessions
# ---------------------------------------------------------------------------

class TestScanSessions:
    def test_includes_plain_and_reset_files(self, tmp_path):
        (tmp_path / "active.jsonl").write_text("{}")
        (tmp_path / "closed.jsonl.reset.2026-01-01T00-00-00.000Z").write_text("{}")
        (tmp_path / "gone.jsonl.deleted.2026-01-01T00-00-00.000Z").write_text("{}")
        (tmp_path / "sessions.json").write_text("{}")
        (tmp_path / "notes.txt").write_text("ignored")

        paths = scan_sessions(tmp_path)
        names = {p.name for p in paths}
        assert names == {
            "active.jsonl",
            "closed.jsonl.reset.2026-01-01T00-00-00.000Z",
        }

    def test_excludes_deleted_files(self, tmp_path):
        (tmp_path / "a.jsonl.deleted.2026-01-01T00-00-00.000Z").write_text("{}")
        assert scan_sessions(tmp_path) == []

    def test_excludes_non_jsonl_files(self, tmp_path):
        (tmp_path / "sessions.json").write_text("{}")
        (tmp_path / "notes.txt").write_text("{}")
        assert scan_sessions(tmp_path) == []

    def test_sorted_by_mtime_descending(self, tmp_path):
        p1 = tmp_path / "older.jsonl"
        p2 = tmp_path / "newer.jsonl.reset.2026-01-02T00-00-00.000Z"
        p1.write_text("{}")
        time.sleep(0.01)
        p2.write_text("{}")

        paths = scan_sessions(tmp_path)
        assert paths[0].name == "newer.jsonl.reset.2026-01-02T00-00-00.000Z"
        assert paths[1].name == "older.jsonl"

    def test_empty_directory(self, tmp_path):
        assert scan_sessions(tmp_path) == []

    def test_deleted_substring_only_excluded_with_dots(self, tmp_path):
        (tmp_path / "deleted-uuid-here.jsonl").write_text("{}")
        paths = scan_sessions(tmp_path)
        assert len(paths) == 1

    def test_returns_path_objects(self, tmp_path):
        (tmp_path / "s.jsonl").write_text("{}")
        paths = scan_sessions(tmp_path)
        assert all(isinstance(p, Path) for p in paths)

    def test_exclude_ids_filters_matching_session(self, tmp_path):
        uuid = "f6ba1f43-a58c-4fa9-8f70-7e7cd9c03e83"
        (tmp_path / f"{uuid}.jsonl").write_text("{}")
        (tmp_path / "other-uuid.jsonl").write_text("{}")
        paths = scan_sessions(tmp_path, exclude_ids={uuid})
        names = {p.name for p in paths}
        assert f"{uuid}.jsonl" not in names
        assert "other-uuid.jsonl" in names

    def test_exclude_ids_none_is_backwards_compatible(self, tmp_path):
        (tmp_path / "s.jsonl").write_text("{}")
        paths_default = scan_sessions(tmp_path)
        paths_none = scan_sessions(tmp_path, exclude_ids=None)
        assert [p.name for p in paths_default] == [p.name for p in paths_none]

    def test_exclude_ids_empty_set_shows_all(self, tmp_path):
        (tmp_path / "s.jsonl").write_text("{}")
        paths = scan_sessions(tmp_path, exclude_ids=set())
        assert len(paths) == 1

    def test_exclude_ids_reset_variant_excluded(self, tmp_path):
        uuid = "f6ba1f43-a58c-4fa9-8f70-7e7cd9c03e83"
        fname = f"{uuid}.jsonl.reset.2026-01-01T00-00-00.000Z"
        (tmp_path / fname).write_text("{}")
        paths = scan_sessions(tmp_path, exclude_ids={uuid})
        assert paths == []

    def test_exclude_ids_non_matching_uuid_kept(self, tmp_path):
        uuid_a = "aaaaaaaa-0000-0000-0000-000000000000"
        uuid_b = "bbbbbbbb-0000-0000-0000-000000000000"
        (tmp_path / f"{uuid_a}.jsonl").write_text("{}")
        (tmp_path / f"{uuid_b}.jsonl").write_text("{}")
        paths = scan_sessions(tmp_path, exclude_ids={uuid_a})
        assert len(paths) == 1
        assert session_uuid(paths[0]) == uuid_b


# ---------------------------------------------------------------------------
# session_uuid
# ---------------------------------------------------------------------------

class TestSessionUuid:
    def test_plain_jsonl(self, tmp_path):
        p = tmp_path / "f6ba1f43-a58c-4fa9-8f70-7e7cd9c03e83.jsonl"
        assert session_uuid(p) == "f6ba1f43-a58c-4fa9-8f70-7e7cd9c03e83"

    def test_reset_file(self, tmp_path):
        p = tmp_path / "f6ba1f43-a58c-4fa9-8f70-7e7cd9c03e83.jsonl.reset.2026-03-01T20-37-45.416Z"
        assert session_uuid(p) == "f6ba1f43-a58c-4fa9-8f70-7e7cd9c03e83"

    def test_deleted_file(self, tmp_path):
        p = tmp_path / "f6ba1f43-a58c-4fa9-8f70-7e7cd9c03e83.jsonl.deleted.2026-03-01T20-37-45.416Z"
        assert session_uuid(p) == "f6ba1f43-a58c-4fa9-8f70-7e7cd9c03e83"

    def test_short_id_is_first_8_chars(self, tmp_path):
        p = tmp_path / "f6ba1f43-a58c-4fa9-8f70-7e7cd9c03e83.jsonl.reset.2026-03-01T20-37-45.416Z"
        assert session_uuid(p)[:8] == "f6ba1f43"


# ---------------------------------------------------------------------------
# session_summary
# ---------------------------------------------------------------------------

class TestSessionSummary:
    def test_basic_summary(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [
            _session_event(),
            _model_change_event("my-model", "my-provider"),
            _user_message(),
            _assistant_message(),
            _tool_result_message(),
        ])
        s = session_summary(p)
        assert s["timestamp"] == "2026-03-01T12:00:00.000Z"
        assert s["model"] == "my-model"
        assert s["provider"] == "my-provider"
        assert s["message_count"] == 2  # 1 user + 1 assistant
        assert s["tool_count"] == 0  # default assistant message has no tool calls
        assert s["path"] == p
        # last_event_ts is the toolResult timestamp (last in file)
        assert s["last_event_ts"] == "2026-03-01T12:00:04.000Z"

    def test_last_event_ts_tracks_final_event(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [
            _session_event(),
            _user_message(),
            _assistant_message(),
        ])
        s = session_summary(p)
        # assistant message is last, timestamp 2026-03-01T12:00:03.000Z
        assert s["last_event_ts"] == "2026-03-01T12:00:03.000Z"

    def test_last_event_ts_empty_for_empty_file(self, tmp_path):
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        s = session_summary(p)
        assert s["last_event_ts"] == ""

    def test_tool_call_counting(self, tmp_path):
        p = tmp_path / "s.jsonl"
        tool_calls = [
            {"type": "toolCall", "id": f"tc{i}", "name": "exec", "arguments": {}}
            for i in range(3)
        ]
        _write_jsonl(p, [_assistant_message(tool_calls=tool_calls, text="")])
        s = session_summary(p)
        assert s["tool_count"] == 3

    def test_model_from_first_model_change_only(self, tmp_path):
        p = tmp_path / "s.jsonl"
        mc1 = _model_change_event("first-model", "google")
        mc2 = {**mc1, "id": "mc2", "modelId": "second-model"}
        _write_jsonl(p, [mc1, mc2])
        s = session_summary(p)
        assert s["model"] == "first-model"

    def test_empty_file_summary(self, tmp_path):
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        s = session_summary(p)
        assert s["timestamp"] == ""
        assert s["last_event_ts"] == ""
        assert s["model"] == ""
        assert s["message_count"] == 0
        assert s["tool_count"] == 0

    def test_toolresult_not_counted_in_messages(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [
            _user_message(),
            _assistant_message(),
            _tool_result_message(),
            _tool_result_message(),
        ])
        s = session_summary(p)
        assert s["message_count"] == 2  # only user + assistant

    def test_malformed_lines_dont_crash_summary(self, tmp_path):
        p = tmp_path / "s.jsonl"
        p.write_text('{"type": "session", "id": "x", "timestamp": "t", "cwd": "/"}\nnot json\n')
        s = session_summary(p)
        assert s["timestamp"] == "t"

    def test_has_error_false_for_clean_session(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_user_message(), _assistant_message(), _tool_result_message(is_error=False)])
        s = session_summary(p)
        assert s["has_error"] is False
        assert s["has_corrected"] is False

    def test_has_error_true_for_is_error_flag(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_user_message(), _assistant_message(), _tool_result_message(is_error=True)])
        s = session_summary(p)
        assert s["has_error"] is True

    def test_has_error_true_for_nonzero_exit_code(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_user_message(), _assistant_message(),
                         _tool_result_message(details={"exitCode": 1, "status": "completed"})])
        s = session_summary(p)
        assert s["has_error"] is True

    def test_has_error_false_for_zero_exit_code(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_user_message(), _assistant_message(),
                         _tool_result_message(details={"exitCode": 0})])
        s = session_summary(p)
        assert s["has_error"] is False

    def test_total_cost_accumulates(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_user_message(), _assistant_message()])
        s = session_summary(p)
        assert abs(s["total_cost"] - 0.015) < 1e-9

    def test_total_cost_zero_for_no_assistant(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [_user_message()])
        s = session_summary(p)
        assert s["total_cost"] == 0.0

    def test_has_error_fields_in_error_return(self, tmp_path):
        # PermissionError path should still return has_error/has_corrected/total_cost
        s = session_summary(tmp_path / "nonexistent_xyz.jsonl")
        assert "has_error" in s
        assert "has_corrected" in s
        assert "total_cost" in s


# ---------------------------------------------------------------------------
# tool_result_has_error
# ---------------------------------------------------------------------------

def _make_tr(is_error=False, details=None) -> Message:
    return Message(
        id="tr1", parent_id=None, timestamp="t", role="toolResult",
        content=[ContentBlock(type="text", text="output")],
        tool_call_id="tc1", tool_name="exec",
        is_error=is_error,
        details=details or {},
    )


class TestToolResultHasError:
    def test_is_error_flag_detected(self):
        assert tool_result_has_error(_make_tr(is_error=True)) is True

    def test_clean_success_not_error(self):
        assert tool_result_has_error(_make_tr(details={"exitCode": 0, "status": "completed"})) is False

    def test_exit_code_1(self):
        assert tool_result_has_error(_make_tr(details={"exitCode": 1, "status": "completed"})) is True

    def test_exit_code_2(self):
        assert tool_result_has_error(_make_tr(details={"exitCode": 2, "status": "completed"})) is True

    def test_exit_code_126_permission_denied(self):
        assert tool_result_has_error(_make_tr(details={"exitCode": 126, "status": "completed"})) is True

    def test_exit_code_zero_not_error(self):
        assert tool_result_has_error(_make_tr(details={"exitCode": 0})) is False

    def test_no_exit_code_running_not_error(self):
        assert tool_result_has_error(_make_tr(details={"status": "running", "pid": 123})) is False

    def test_status_failed(self):
        assert tool_result_has_error(_make_tr(details={"status": "failed", "exitCode": 1})) is True

    def test_status_error(self):
        assert tool_result_has_error(_make_tr(details={"status": "error", "tool": "read", "error": "ENOENT"})) is True

    def test_error_key_present(self):
        assert tool_result_has_error(_make_tr(details={"error": "ENOENT: no such file"})) is True

    def test_empty_details_not_error(self):
        assert tool_result_has_error(_make_tr(details={})) is False
