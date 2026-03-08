"""Tests for CronBrowser widget and app cron mode integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eavesdrop.app import EavesdropApp
from eavesdrop.cron_parser import CronJob, CronRun
from eavesdrop.widgets.cron_browser import CronBrowser, CronJobItem, CronRunItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jobs(cron_dir: Path, jobs: list[dict]) -> None:
    cron_dir.mkdir(parents=True, exist_ok=True)
    with open(cron_dir / "jobs.json", "w") as f:
        json.dump({"jobs": jobs}, f)


def _write_runs(runs_dir: Path, job_id: str, lines: list[dict]) -> None:
    runs_dir.mkdir(parents=True, exist_ok=True)
    with open(runs_dir / f"{job_id}.jsonl", "w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")


def _job_dict(
    job_id: str = "job-uuid-1",
    name: str = "Morning Briefing",
    enabled: bool = True,
) -> dict:
    return {
        "id": job_id,
        "name": name,
        "enabled": enabled,
        "schedule": {"kind": "cron", "expr": "30 6 * * *", "tz": "America/Los_Angeles"},
        "state": {
            "lastRunStatus": "ok",
            "lastDurationMs": 83323,
            "nextRunAtMs": 1773063000000,
            "consecutiveErrors": 0,
            "lastDeliveryStatus": "delivered",
        },
    }


def _run_line(
    ts: int = 1772976683336,
    status: str = "ok",
    session_id: str = "session-uuid-abc",
) -> dict:
    return {
        "ts": ts,
        "action": "finished",
        "status": status,
        "summary": "All good",
        "sessionId": session_id,
        "durationMs": 83323,
        "delivered": True,
        "deliveryStatus": "delivered",
        "usage": {"totalTokens": 18066},
    }


def _minimal_session(path: Path) -> None:
    with open(path, "w") as f:
        f.write(json.dumps({
            "type": "session",
            "id": "test-id",
            "timestamp": "2026-03-01T12:00:00.000Z",
            "cwd": "/tmp",
        }) + "\n")
        f.write(json.dumps({
            "type": "message",
            "id": "u1",
            "parentId": None,
            "timestamp": "2026-03-01T12:00:02.000Z",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "hello"}],
            },
        }) + "\n")


# ---------------------------------------------------------------------------
# CronBrowser unit tests (no App)
# ---------------------------------------------------------------------------

class TestCronBrowserWidget:
    @pytest.mark.asyncio
    async def test_mounts_without_error(self, tmp_path):
        cron_dir = tmp_path / "cron"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        _write_jobs(cron_dir, [])

        app = EavesdropApp(sessions_dir=sessions_dir, openclaw_dir=tmp_path)
        async with app.run_test(size=(80, 24)):
            cron = app.query_one("#cron-browser", CronBrowser)
            assert cron is not None

    @pytest.mark.asyncio
    async def test_shows_jobs_from_jobs_json(self, tmp_path):
        cron_dir = tmp_path / "cron"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        _write_jobs(cron_dir, [
            _job_dict(job_id="j1", name="Job One"),
            _job_dict(job_id="j2", name="Job Two"),
        ])

        app = EavesdropApp(
            sessions_dir=sessions_dir,
            openclaw_dir=tmp_path,
            start_cron=True,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            cron = app.query_one("#cron-browser", CronBrowser)
            items = list(cron.query(CronJobItem))
            assert len(items) == 2
            names = [item.job.name for item in items]
            assert "Job One" in names
            assert "Job Two" in names

    @pytest.mark.asyncio
    async def test_empty_jobs_shows_no_items(self, tmp_path):
        cron_dir = tmp_path / "cron"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        _write_jobs(cron_dir, [])

        app = EavesdropApp(
            sessions_dir=sessions_dir,
            openclaw_dir=tmp_path,
            start_cron=True,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            cron = app.query_one("#cron-browser", CronBrowser)
            items = list(cron.query(CronJobItem))
            assert items == []

    @pytest.mark.asyncio
    async def test_missing_cron_dir_shows_no_items(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        app = EavesdropApp(
            sessions_dir=sessions_dir,
            openclaw_dir=tmp_path,
            start_cron=True,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            cron = app.query_one("#cron-browser", CronBrowser)
            items = list(cron.query(CronJobItem))
            assert items == []


# ---------------------------------------------------------------------------
# App cron mode toggle
# ---------------------------------------------------------------------------

class TestAppCronModeToggle:
    @pytest.mark.asyncio
    async def test_C_key_shows_cron_browser(self, tmp_path):
        cron_dir = tmp_path / "cron"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        _write_jobs(cron_dir, [])

        app = EavesdropApp(sessions_dir=sessions_dir, openclaw_dir=tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            from eavesdrop.widgets.file_browser import FileBrowser
            browser = app.query_one("#browser", FileBrowser)
            cron = app.query_one("#cron-browser", CronBrowser)

            assert browser.display is True
            assert cron.display is False

            await pilot.press("C")

            assert browser.display is False
            assert cron.display is True

    @pytest.mark.asyncio
    async def test_C_key_toggles_back(self, tmp_path):
        cron_dir = tmp_path / "cron"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        _write_jobs(cron_dir, [])

        app = EavesdropApp(sessions_dir=sessions_dir, openclaw_dir=tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            from eavesdrop.widgets.file_browser import FileBrowser
            browser = app.query_one("#browser", FileBrowser)
            cron = app.query_one("#cron-browser", CronBrowser)

            await pilot.press("C")
            await pilot.press("C")

            assert browser.display is True
            assert cron.display is False

    @pytest.mark.asyncio
    async def test_start_cron_shows_cron_browser(self, tmp_path):
        cron_dir = tmp_path / "cron"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        _write_jobs(cron_dir, [])

        app = EavesdropApp(
            sessions_dir=sessions_dir,
            openclaw_dir=tmp_path,
            start_cron=True,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            from eavesdrop.widgets.file_browser import FileBrowser
            browser = app.query_one("#browser", FileBrowser)
            cron = app.query_one("#cron-browser", CronBrowser)

            assert browser.display is False
            assert cron.display is True


# ---------------------------------------------------------------------------
# CronBrowser level navigation
# ---------------------------------------------------------------------------

class TestCronBrowserNavigation:
    @pytest.mark.asyncio
    async def test_enter_on_job_shows_runs(self, tmp_path):
        job_id = "job-uuid-1"
        cron_dir = tmp_path / "cron"
        runs_dir = cron_dir / "runs"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        _write_jobs(cron_dir, [_job_dict(job_id=job_id)])
        _write_runs(runs_dir, job_id, [
            _run_line(ts=1000, session_id="sess-1"),
            _run_line(ts=2000, session_id="sess-2"),
        ])

        app = EavesdropApp(
            sessions_dir=sessions_dir,
            openclaw_dir=tmp_path,
            start_cron=True,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            cron = app.query_one("#cron-browser", CronBrowser)

            # Initially at jobs level
            assert cron._level == "jobs"
            assert len(list(cron.query(CronJobItem))) == 1

            # Simulate selecting the job item
            cron._selected_job = cron._jobs[0]
            cron._level = "runs"
            cron._render_runs(cron._jobs[0])
            await pilot.pause()

            assert cron._level == "runs"
            items = list(cron.query(CronRunItem))
            assert len(items) == 2

    @pytest.mark.asyncio
    async def test_back_from_runs_returns_to_jobs(self, tmp_path):
        job_id = "job-uuid-1"
        cron_dir = tmp_path / "cron"
        runs_dir = cron_dir / "runs"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        _write_jobs(cron_dir, [_job_dict(job_id=job_id)])
        _write_runs(runs_dir, job_id, [_run_line()])

        app = EavesdropApp(
            sessions_dir=sessions_dir,
            openclaw_dir=tmp_path,
            start_cron=True,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            cron = app.query_one("#cron-browser", CronBrowser)

            # Go to runs level
            cron._selected_job = cron._jobs[0]
            cron._level = "runs"
            cron._render_runs(cron._jobs[0])
            await pilot.pause()
            assert cron._level == "runs"

            # Go back
            cron.action_back()
            await pilot.pause()
            assert cron._level == "jobs"
            assert cron._selected_job is None
            assert len(list(cron.query(CronJobItem))) == 1

    @pytest.mark.asyncio
    async def test_back_at_jobs_level_is_noop(self, tmp_path):
        cron_dir = tmp_path / "cron"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        _write_jobs(cron_dir, [])

        app = EavesdropApp(
            sessions_dir=sessions_dir,
            openclaw_dir=tmp_path,
            start_cron=True,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            cron = app.query_one("#cron-browser", CronBrowser)
            assert cron._level == "jobs"
            cron.action_back()  # should not crash
            assert cron._level == "jobs"


# ---------------------------------------------------------------------------
# Session load from cron run
# ---------------------------------------------------------------------------

class TestCronBrowserSessionLoad:
    @pytest.mark.asyncio
    async def test_session_requested_fires_and_loads(self, tmp_path):
        job_id = "job-uuid-1"
        session_id = "session-uuid-abc"
        cron_dir = tmp_path / "cron"
        runs_dir = cron_dir / "runs"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        # Create a real session file
        sess_file = sessions_dir / f"{session_id}.jsonl.reset.1234567890"
        _minimal_session(sess_file)

        _write_jobs(cron_dir, [_job_dict(job_id=job_id)])
        _write_runs(runs_dir, job_id, [_run_line(session_id=session_id)])

        app = EavesdropApp(
            sessions_dir=sessions_dir,
            openclaw_dir=tmp_path,
            start_cron=True,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            cron = app.query_one("#cron-browser", CronBrowser)

            # Navigate to runs
            job = cron._jobs[0]
            cron._selected_job = job
            cron._level = "runs"
            cron._render_runs(job)
            await pilot.pause()

            # Fire SessionRequested directly
            from eavesdrop.cron_parser import load_runs, find_session
            runs = load_runs(cron_dir, job_id)
            assert len(runs) == 1
            run = runs[0]
            path = find_session(sessions_dir, session_id)
            assert path is not None

            cron.post_message(CronBrowser.SessionRequested(path=path, run=run, job=job))
            await pilot.pause()

            assert app._current_path == path

    @pytest.mark.asyncio
    async def test_no_session_id_shows_cron_header(self, tmp_path):
        job_id = "job-uuid-1"
        cron_dir = tmp_path / "cron"
        runs_dir = cron_dir / "runs"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        _write_jobs(cron_dir, [_job_dict(job_id=job_id)])
        # Run with no sessionId
        line = _run_line()
        del line["sessionId"]
        _write_runs(runs_dir, job_id, [line])

        app = EavesdropApp(
            sessions_dir=sessions_dir,
            openclaw_dir=tmp_path,
            start_cron=True,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            cron = app.query_one("#cron-browser", CronBrowser)
            job = cron._jobs[0]
            from eavesdrop.cron_parser import load_runs, CronRunContext
            runs = load_runs(cron_dir, job_id)
            assert len(runs) == 1
            # SessionRequested with path=None — should show cron header, not crash
            cron.post_message(CronBrowser.SessionRequested(path=None, run=runs[0], job=job))
            await pilot.pause()
            # Should not crash; header should be visible
            from eavesdrop.widgets.conversation import ConversationView
            from eavesdrop.widgets.turn import CronRunHeader
            conv = app.query_one("#conversation", ConversationView)
            assert len(list(conv.query(CronRunHeader))) == 1

    @pytest.mark.asyncio
    async def test_missing_session_file_shows_cron_header(self, tmp_path):
        job_id = "job-uuid-1"
        cron_dir = tmp_path / "cron"
        runs_dir = cron_dir / "runs"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        _write_jobs(cron_dir, [_job_dict(job_id=job_id)])
        # Run points to a session that doesn't exist in sessions_dir
        _write_runs(runs_dir, job_id, [_run_line(session_id="nonexistent-session-id")])

        app = EavesdropApp(
            sessions_dir=sessions_dir,
            openclaw_dir=tmp_path,
            start_cron=True,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            cron = app.query_one("#cron-browser", CronBrowser)
            job = cron._jobs[0]
            from eavesdrop.cron_parser import load_runs
            runs = load_runs(cron_dir, job_id)
            # State is "missing" so path=None — cron header should still render
            cron.post_message(CronBrowser.SessionRequested(path=None, run=runs[0], job=job))
            await pilot.pause()
            from eavesdrop.widgets.conversation import ConversationView
            from eavesdrop.widgets.turn import CronRunHeader
            conv = app.query_one("#conversation", ConversationView)
            assert len(list(conv.query(CronRunHeader))) == 1


# ---------------------------------------------------------------------------
# __main__ --cron flag
# ---------------------------------------------------------------------------

class TestCronCLIFlag:
    def test_cron_flag_enables_start_cron(self, tmp_path, monkeypatch):
        from eavesdrop.__main__ import main

        created_app = {}

        class FakeApp:
            def __init__(self, sessions_dir, initial_session, openclaw_dir, start_cron, **kw):
                created_app["openclaw_dir"] = openclaw_dir
                created_app["start_cron"] = start_cron

            def run(self):
                pass

        monkeypatch.setattr("eavesdrop.__main__.EavesdropApp", FakeApp)
        monkeypatch.setattr("sys.argv", ["eavesdrop", "--cron", str(tmp_path)])
        main()

        assert created_app["start_cron"] is True
        assert created_app["openclaw_dir"] == tmp_path

    def test_cron_flag_no_path_uses_default(self, tmp_path, monkeypatch):
        from eavesdrop.__main__ import main
        from eavesdrop.app import DEFAULT_OPENCLAW_DIR

        created_app = {}

        class FakeApp:
            def __init__(self, sessions_dir, initial_session, openclaw_dir, start_cron, **kw):
                created_app["openclaw_dir"] = openclaw_dir
                created_app["start_cron"] = start_cron

            def run(self):
                pass

        monkeypatch.setattr("eavesdrop.__main__.EavesdropApp", FakeApp)
        monkeypatch.setattr("sys.argv", ["eavesdrop", "--cron"])
        main()

        assert created_app["start_cron"] is True
        assert created_app["openclaw_dir"] == DEFAULT_OPENCLAW_DIR

    def test_no_cron_flag_start_cron_false(self, tmp_path, monkeypatch):
        from eavesdrop.__main__ import main

        created_app = {}

        class FakeApp:
            def __init__(self, sessions_dir, initial_session, openclaw_dir, start_cron, **kw):
                created_app["start_cron"] = start_cron

            def run(self):
                pass

        monkeypatch.setattr("eavesdrop.__main__.EavesdropApp", FakeApp)
        monkeypatch.setattr("sys.argv", ["eavesdrop"])
        main()

        assert created_app["start_cron"] is False


# ---------------------------------------------------------------------------
# DEFAULT_OPENCLAW_DIR derivation  (bug: was hardcoded to ~/. openclaw)
# ---------------------------------------------------------------------------

class TestDefaultPaths:
    def test_openclaw_dir_derived_from_sessions_dir(self):
        """openclaw_dir must be 3 levels up from sessions_dir, not hardcoded to ~/. openclaw.

        With EAVESDROP_SESSIONS_DIR=/home/openclaw/.openclaw/agents/main-cloud/sessions,
        DEFAULT_OPENCLAW_DIR must equal /home/openclaw/.openclaw, not /home/<user>/.openclaw.
        """
        import os
        from eavesdrop.app import DEFAULT_OPENCLAW_DIR, DEFAULT_SESSIONS_DIR
        if "EAVESDROP_OPENCLAW_DIR" in os.environ:
            pytest.skip("EAVESDROP_OPENCLAW_DIR is explicitly set — derivation not active")
        assert DEFAULT_OPENCLAW_DIR == DEFAULT_SESSIONS_DIR.parent.parent.parent

    def test_openclaw_dir_env_override(self, tmp_path, monkeypatch):
        """EAVESDROP_OPENCLAW_DIR overrides the derived default."""
        import importlib
        import eavesdrop.app as app_module
        monkeypatch.setenv("EAVESDROP_OPENCLAW_DIR", str(tmp_path))
        importlib.reload(app_module)
        try:
            assert app_module.DEFAULT_OPENCLAW_DIR == tmp_path
        finally:
            importlib.reload(app_module)


# ---------------------------------------------------------------------------
# No-session label messages  (bug: unhelpful "session file not found")
# ---------------------------------------------------------------------------

def _label_texts(conv) -> list[str]:
    """Collect plain text of all Labels inside a ConversationView."""
    from textual.widgets import Label
    texts = []
    for lbl in conv.query(Label):
        try:
            texts.append(str(lbl.render()))
        except Exception:
            pass
    return texts


class TestNoSessionMessages:
    @pytest.mark.asyncio
    async def test_deleted_message_contains_uuid_and_retention(self, tmp_path):
        """Bug: was showing generic 'session file not found'; must say 'deleted by openclaw retention'."""
        job_id = "job-uuid-1"
        session_id = "sess-uuid-deleted"
        cron_dir = tmp_path / "cron"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        _write_jobs(cron_dir, [_job_dict(job_id=job_id)])
        # Create only the deleted variant
        (sessions_dir / f"{session_id}.jsonl.deleted.1234567890").write_text("")
        _write_runs(cron_dir / "runs", job_id, [_run_line(session_id=session_id)])

        app = EavesdropApp(
            sessions_dir=sessions_dir,
            openclaw_dir=tmp_path,
            start_cron=True,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            cron = app.query_one("#cron-browser", CronBrowser)
            job = cron._jobs[0]
            from eavesdrop.cron_parser import load_runs, CronRunContext
            runs = load_runs(cron_dir, job_id)
            cron.post_message(CronBrowser.SessionRequested(
                path=None, run=runs[0], job=job, session_state="deleted"
            ))
            await pilot.pause()
            from eavesdrop.widgets.conversation import ConversationView
            conv = app.query_one("#conversation", ConversationView)
            texts = _label_texts(conv)
            combined = " ".join(texts)
            assert session_id in combined
            assert "retention" in combined

    @pytest.mark.asyncio
    async def test_no_isolated_session_message(self, tmp_path):
        """sessionTarget: main runs should say 'no isolated session'."""
        job_id = "job-uuid-1"
        cron_dir = tmp_path / "cron"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        _write_jobs(cron_dir, [_job_dict(job_id=job_id)])
        line = _run_line()
        del line["sessionId"]
        _write_runs(cron_dir / "runs", job_id, [line])

        app = EavesdropApp(
            sessions_dir=sessions_dir,
            openclaw_dir=tmp_path,
            start_cron=True,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            cron = app.query_one("#cron-browser", CronBrowser)
            job = cron._jobs[0]
            from eavesdrop.cron_parser import load_runs
            runs = load_runs(cron_dir, job_id)
            cron.post_message(CronBrowser.SessionRequested(
                path=None, run=runs[0], job=job, session_state="no_session"
            ))
            await pilot.pause()
            from eavesdrop.widgets.conversation import ConversationView
            conv = app.query_one("#conversation", ConversationView)
            texts = _label_texts(conv)
            assert any("isolated session" in t for t in texts)

    @pytest.mark.asyncio
    async def test_no_session_and_no_debug_log_appends_note(self, tmp_path):
        """Bug: no-session + no-debug-log should say both are empty."""
        job_id = "job-uuid-1"
        cron_dir = tmp_path / "cron"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        _write_jobs(cron_dir, [_job_dict(job_id=job_id)])
        _write_runs(cron_dir / "runs", job_id, [_run_line(session_id="gone-session")])

        # No debug log file at all
        app = EavesdropApp(
            sessions_dir=sessions_dir,
            openclaw_dir=tmp_path,  # no logs/openclaw-debug.log here
            start_cron=True,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            cron = app.query_one("#cron-browser", CronBrowser)
            job = cron._jobs[0]
            from eavesdrop.cron_parser import load_runs
            runs = load_runs(cron_dir, job_id)
            cron.post_message(CronBrowser.SessionRequested(
                path=None, run=runs[0], job=job, session_state="missing"
            ))
            await pilot.pause()
            from eavesdrop.widgets.conversation import ConversationView
            conv = app.query_one("#conversation", ConversationView)
            texts = _label_texts(conv)
            assert any("no debug log entries" in t for t in texts)

    @pytest.mark.asyncio
    async def test_cron_header_shown_even_without_session(self, tmp_path):
        """Bug: deleted/missing sessions used to show a dead-end label; must show CronRunHeader."""
        job_id = "job-uuid-1"
        cron_dir = tmp_path / "cron"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        _write_jobs(cron_dir, [_job_dict(job_id=job_id)])
        _write_runs(cron_dir / "runs", job_id, [_run_line(session_id="gone-session")])

        app = EavesdropApp(
            sessions_dir=sessions_dir,
            openclaw_dir=tmp_path,
            start_cron=True,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            cron = app.query_one("#cron-browser", CronBrowser)
            job = cron._jobs[0]
            from eavesdrop.cron_parser import load_runs
            runs = load_runs(cron_dir, job_id)
            cron.post_message(CronBrowser.SessionRequested(
                path=None, run=runs[0], job=job, session_state="missing"
            ))
            await pilot.pause()
            from eavesdrop.widgets.conversation import ConversationView
            from eavesdrop.widgets.turn import CronRunHeader, DebugLogSection
            conv = app.query_one("#conversation", ConversationView)
            assert len(list(conv.query(CronRunHeader))) == 1
            assert len(list(conv.query(DebugLogSection))) == 1


# ---------------------------------------------------------------------------
# session_state carried through SessionRequested → CronRunContext → _rebuild
# ---------------------------------------------------------------------------

class TestSessionStateFlow:
    @pytest.mark.asyncio
    async def test_session_state_stored_on_cron_run_item(self, tmp_path):
        job_id = "job-uuid-1"
        session_id = "sess-deleted"
        cron_dir = tmp_path / "cron"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        _write_jobs(cron_dir, [_job_dict(job_id=job_id)])
        # Only deleted variant exists
        (sessions_dir / f"{session_id}.jsonl.deleted.111").write_text("")
        _write_runs(cron_dir / "runs", job_id, [_run_line(session_id=session_id)])

        app = EavesdropApp(
            sessions_dir=sessions_dir,
            openclaw_dir=tmp_path,
            start_cron=True,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            cron = app.query_one("#cron-browser", CronBrowser)
            job = cron._jobs[0]
            cron._selected_job = job
            cron._level = "runs"
            cron._render_runs(job)
            await pilot.pause()
            items = list(cron.query(CronRunItem))
            assert len(items) == 1
            assert items[0].session_state == "deleted"

    @pytest.mark.asyncio
    async def test_session_state_in_cron_run_context(self, tmp_path):
        """session_state must flow into CronRunContext so _rebuild picks the right label."""
        job_id = "job-uuid-1"
        session_id = "sess-deleted"
        cron_dir = tmp_path / "cron"
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        _write_jobs(cron_dir, [_job_dict(job_id=job_id)])
        (sessions_dir / f"{session_id}.jsonl.deleted.111").write_text("")
        _write_runs(cron_dir / "runs", job_id, [_run_line(session_id=session_id)])

        app = EavesdropApp(
            sessions_dir=sessions_dir,
            openclaw_dir=tmp_path,
            start_cron=True,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            cron = app.query_one("#cron-browser", CronBrowser)
            job = cron._jobs[0]
            from eavesdrop.cron_parser import load_runs
            runs = load_runs(cron_dir, job_id)
            cron.post_message(CronBrowser.SessionRequested(
                path=None, run=runs[0], job=job, session_state="deleted"
            ))
            await pilot.pause()
            from eavesdrop.widgets.conversation import ConversationView
            conv = app.query_one("#conversation", ConversationView)
            assert conv._cron_context is not None
            assert conv._cron_context.session_state == "deleted"
