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
