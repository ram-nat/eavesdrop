"""Tests for graceful handling of unreadable session files."""

import json
import stat
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest

from eavesdrop.parser import parse_file, session_summary, scan_sessions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, lines: list[dict]) -> None:
    with open(path, "w") as f:
        for obj in lines:
            f.write(json.dumps(obj) + "\n")


# ---------------------------------------------------------------------------
# parse_file permission errors
# ---------------------------------------------------------------------------

class TestParseFilePermissions:
    def test_permission_error_returns_empty_session_with_error(self, tmp_path):
        p = tmp_path / "s.jsonl"
        p.write_text("{}")
        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            result = parse_file(p)
        assert result.meta is None
        assert result.events == []
        assert "Permission denied" in result.error

    def test_os_error_returns_empty_session_with_error(self, tmp_path):
        p = tmp_path / "s.jsonl"
        p.write_text("{}")
        with patch("builtins.open", side_effect=OSError("I/O error")):
            result = parse_file(p)
        assert result.error != ""

    def test_readable_file_has_no_error(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [
            {"type": "session", "id": "x", "timestamp": "t", "cwd": "/"},
        ])
        result = parse_file(p)
        assert result.error == ""


# ---------------------------------------------------------------------------
# session_summary permission errors
# ---------------------------------------------------------------------------

class TestSessionSummaryPermissions:
    def test_permission_error_returns_error_dict(self, tmp_path):
        p = tmp_path / "s.jsonl"
        p.write_text("{}")
        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            s = session_summary(p)
        assert s["error"] != ""
        assert "Permission denied" in s["error"]
        assert s["path"] == p
        assert s["message_count"] == 0

    def test_os_error_returns_error_dict(self, tmp_path):
        p = tmp_path / "s.jsonl"
        p.write_text("{}")
        with patch("builtins.open", side_effect=OSError("I/O error")):
            s = session_summary(p)
        assert s["error"] != ""

    def test_readable_file_has_empty_error(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _write_jsonl(p, [{"type": "session", "id": "x", "timestamp": "t", "cwd": "/"}])
        s = session_summary(p)
        assert s["error"] == ""


# ---------------------------------------------------------------------------
# File browser: inaccessible sessions don't crash load_sessions
# ---------------------------------------------------------------------------

class TestFileBrowserPermissions:
    @pytest.mark.asyncio
    async def test_inaccessible_session_shown_in_browser(self, tmp_path):
        from eavesdrop.app import EavesdropApp
        from eavesdrop.widgets.file_browser import FileBrowser, SessionItem

        good = tmp_path / "good.jsonl"
        bad = tmp_path / "bad.jsonl"
        _write_jsonl(good, [{"type": "session", "id": "g", "timestamp": "t", "cwd": "/"}])
        bad.write_text("{}")

        def fake_summary(path):
            if path == bad:
                return {"path": path, "timestamp": "", "model": "", "provider": "",
                        "message_count": 0, "tool_count": 0, "error": "Permission denied"}
            return {"path": path, "timestamp": "2026-03-01T12:00:00.000Z", "model": "m",
                    "provider": "p", "message_count": 1, "tool_count": 0, "error": ""}

        with patch("eavesdrop.widgets.file_browser.session_summary", side_effect=fake_summary):
            app = EavesdropApp(sessions_dir=tmp_path)
            async with app.run_test(size=(80, 24)) as pilot:
                browser = app.query_one(FileBrowser)
                items = browser.query(SessionItem)
                assert len(items) == 2  # both shown, not dropped

    @pytest.mark.asyncio
    async def test_opening_inaccessible_session_shows_error_in_conversation(self, tmp_path):
        from eavesdrop.app import EavesdropApp
        from eavesdrop.widgets.conversation import ConversationView
        from eavesdrop.parser import ParsedSession

        p = tmp_path / "s.jsonl"
        p.write_text("{}")

        error_session = ParsedSession(meta=None, events=[], error="Permission denied: /path/to/file")

        with patch("eavesdrop.widgets.conversation.parse_file", return_value=error_session):
            app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
            async with app.run_test(size=(80, 24)) as pilot:
                conv = app.query_one(ConversationView)
                assert conv._session is not None
                assert conv._session.error != ""
