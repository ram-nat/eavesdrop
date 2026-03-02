"""Tests for eavesdrop.app — wiring, keybindings, CLI arg parsing."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from eavesdrop.app import EavesdropApp
from eavesdrop.parser import scan_sessions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, lines: list[dict]) -> None:
    with open(path, "w") as f:
        for obj in lines:
            f.write(json.dumps(obj) + "\n")


def _minimal_session(path: Path, model: str = "test-model") -> None:
    _write_jsonl(path, [
        {"type": "session", "id": "test-id", "timestamp": "2026-03-01T12:00:00.000Z", "cwd": "/tmp"},
        {"type": "model_change", "id": "mc1", "parentId": None, "timestamp": "2026-03-01T12:00:01.000Z", "provider": "test", "modelId": model},
        {
            "type": "message", "id": "u1", "parentId": None, "timestamp": "2026-03-01T12:00:02.000Z",
            "message": {"role": "user", "content": [{"type": "text", "text": "hello"}], "timestamp": 1},
        },
        {
            "type": "message", "id": "a1", "parentId": "u1", "timestamp": "2026-03-01T12:00:03.000Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "hi"}],
                "model": model, "provider": "test",
                "usage": {"input": 10, "output": 5, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 15,
                          "cost": {"input": 0.001, "output": 0.0005, "cacheRead": 0, "cacheWrite": 0, "total": 0.0015}},
                "stopReason": "end_turn", "timestamp": 1,
            },
        },
    ])


# ---------------------------------------------------------------------------
# App construction
# ---------------------------------------------------------------------------

class TestAppConstruction:
    def test_app_instantiates_with_sessions_dir(self, tmp_path):
        app = EavesdropApp(sessions_dir=tmp_path)
        assert app._sessions_dir == tmp_path

    def test_app_instantiates_with_initial_session(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _minimal_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        assert app._initial_session == p

    def test_app_no_initial_session_by_default(self, tmp_path):
        app = EavesdropApp(sessions_dir=tmp_path)
        assert app._initial_session is None


# ---------------------------------------------------------------------------
# App startup — session auto-selection
# ---------------------------------------------------------------------------

class TestAppStartup:
    @pytest.mark.asyncio
    async def test_mounts_without_crashing_empty_dir(self, tmp_path):
        app = EavesdropApp(sessions_dir=tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            # app launched without error, sub_title not set (no sessions)
            assert app.sub_title == ""

    @pytest.mark.asyncio
    async def test_auto_selects_most_recent_session(self, tmp_path):
        import time
        p1 = tmp_path / "older.jsonl"
        _minimal_session(p1)
        time.sleep(0.02)
        p2 = tmp_path / "newer.jsonl"
        _minimal_session(p2)

        app = EavesdropApp(sessions_dir=tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            assert app.sub_title == "newer"

    @pytest.mark.asyncio
    async def test_initial_session_overrides_auto_select(self, tmp_path):
        import time
        p1 = tmp_path / "older.jsonl"
        _minimal_session(p1)
        time.sleep(0.02)
        p2 = tmp_path / "newer.jsonl"
        _minimal_session(p2)

        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p1)
        async with app.run_test(size=(80, 24)) as pilot:
            assert app.sub_title == "older"


# ---------------------------------------------------------------------------
# Keybinding actions
# ---------------------------------------------------------------------------

class TestKeybindingActions:
    @pytest.mark.asyncio
    async def test_quit_action(self, tmp_path):
        app = EavesdropApp(sessions_dir=tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("q")
        # if we get here without hanging, quit worked

    @pytest.mark.asyncio
    async def test_toggle_thinking_action(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _minimal_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            from eavesdrop.widgets.conversation import ConversationView
            conv = app.query_one("#conversation", ConversationView)
            assert conv._show_thinking is False
            await pilot.press("t")
            assert conv._show_thinking is True
            await pilot.press("t")
            assert conv._show_thinking is False

    @pytest.mark.asyncio
    async def test_toggle_tools_action(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _minimal_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            from eavesdrop.widgets.conversation import ConversationView
            conv = app.query_one("#conversation", ConversationView)
            assert conv._tools_expanded is False
            await pilot.press("e")
            assert conv._tools_expanded is True
            await pilot.press("e")
            assert conv._tools_expanded is False

    @pytest.mark.asyncio
    async def test_toggle_usage_action(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _minimal_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            from eavesdrop.widgets.conversation import ConversationView
            conv = app.query_one("#conversation", ConversationView)
            assert conv._show_usage is False
            await pilot.press("dollar_sign")
            assert conv._show_usage is True
            await pilot.press("dollar_sign")
            assert conv._show_usage is False

    @pytest.mark.asyncio
    async def test_reload_action_with_no_session(self, tmp_path):
        app = EavesdropApp(sessions_dir=tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            # reload with no session loaded should not crash
            await pilot.press("r")

    @pytest.mark.asyncio
    async def test_reload_action_reloads_current_session(self, tmp_path):
        p = tmp_path / "s.jsonl"
        _minimal_session(p)
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            from eavesdrop.widgets.conversation import ConversationView
            conv = app.query_one("#conversation", ConversationView)
            original_path = app._current_path
            await pilot.press("r")
            assert app._current_path == original_path


# ---------------------------------------------------------------------------
# __main__ argparse
# ---------------------------------------------------------------------------

class TestArgparse:
    def test_default_args(self, tmp_path, monkeypatch):
        import argparse
        from eavesdrop.__main__ import main
        from eavesdrop.app import DEFAULT_SESSIONS_DIR

        created_app = {}

        class FakeApp:
            def __init__(self, sessions_dir, initial_session, **kw):
                created_app["sessions_dir"] = sessions_dir
                created_app["initial_session"] = initial_session

            def run(self):
                pass

        monkeypatch.setattr("eavesdrop.__main__.EavesdropApp", FakeApp)
        monkeypatch.setattr("sys.argv", ["eavesdrop"])
        main()

        assert created_app["sessions_dir"] == DEFAULT_SESSIONS_DIR
        assert created_app["initial_session"] is None

    def test_session_arg(self, tmp_path, monkeypatch):
        from eavesdrop.__main__ import main

        session_path = tmp_path / "my.jsonl"
        session_path.write_text("")

        created_app = {}

        class FakeApp:
            def __init__(self, sessions_dir, initial_session, **kw):
                created_app["initial_session"] = initial_session

            def run(self):
                pass

        monkeypatch.setattr("eavesdrop.__main__.EavesdropApp", FakeApp)
        monkeypatch.setattr("sys.argv", ["eavesdrop", "--session", str(session_path)])
        main()

        assert created_app["initial_session"] == session_path

    def test_dir_arg(self, tmp_path, monkeypatch):
        from eavesdrop.__main__ import main

        created_app = {}

        class FakeApp:
            def __init__(self, sessions_dir, initial_session, **kw):
                created_app["sessions_dir"] = sessions_dir

            def run(self):
                pass

        monkeypatch.setattr("eavesdrop.__main__.EavesdropApp", FakeApp)
        monkeypatch.setattr("sys.argv", ["eavesdrop", "--dir", str(tmp_path)])
        main()

        assert created_app["sessions_dir"] == tmp_path
