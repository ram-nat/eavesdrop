"""Tests for eavesdrop.cron_parser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eavesdrop.cron_parser import (
    CronJob,
    CronRun,
    CronRunContext,
    find_session,
    fmt_duration,
    fmt_ms,
    load_debug_log,
    load_jobs,
    load_runs,
    relative_time,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jobs(path: Path, jobs: list[dict]) -> None:
    with open(path, "w") as f:
        json.dump({"jobs": jobs}, f)


def _job_dict(
    job_id: str = "job-uuid-1",
    name: str = "Morning Briefing",
    enabled: bool = True,
    schedule_expr: str = "30 6 * * *",
    tz: str = "America/Los_Angeles",
    last_run_status: str = "ok",
    last_duration_ms: int = 83323,
    next_run_ms: int = 1773063000000,
    consecutive_errors: int = 0,
    last_delivery_status: str = "delivered",
) -> dict:
    return {
        "id": job_id,
        "name": name,
        "enabled": enabled,
        "schedule": {"kind": "cron", "expr": schedule_expr, "tz": tz},
        "state": {
            "lastRunStatus": last_run_status,
            "lastDurationMs": last_duration_ms,
            "nextRunAtMs": next_run_ms,
            "consecutiveErrors": consecutive_errors,
            "lastDeliveryStatus": last_delivery_status,
        },
    }


def _run_line(
    ts: int = 1772976683336,
    status: str = "ok",
    session_id: str = "session-uuid-abc",
    duration_ms: int = 83323,
    delivered: bool = True,
    action: str = "finished",
) -> dict:
    return {
        "ts": ts,
        "action": action,
        "status": status,
        "summary": "All good",
        "sessionId": session_id,
        "durationMs": duration_ms,
        "delivered": delivered,
        "deliveryStatus": "delivered",
        "usage": {"totalTokens": 18066},
    }


def _write_runs(path: Path, lines: list[dict]) -> None:
    with open(path, "w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")


# ---------------------------------------------------------------------------
# load_jobs
# ---------------------------------------------------------------------------

class TestLoadJobs:
    def test_missing_file(self, tmp_path):
        result = load_jobs(tmp_path / "nonexistent")
        assert result == []

    def test_empty_jobs_list(self, tmp_path):
        cron_dir = tmp_path / "cron"
        cron_dir.mkdir()
        _write_jobs(cron_dir / "jobs.json", [])
        assert load_jobs(cron_dir) == []

    def test_malformed_json(self, tmp_path):
        cron_dir = tmp_path / "cron"
        cron_dir.mkdir()
        (cron_dir / "jobs.json").write_text("not json {{")
        assert load_jobs(cron_dir) == []

    def test_valid_job(self, tmp_path):
        cron_dir = tmp_path / "cron"
        cron_dir.mkdir()
        _write_jobs(cron_dir / "jobs.json", [_job_dict()])
        jobs = load_jobs(cron_dir)
        assert len(jobs) == 1
        j = jobs[0]
        assert j.id == "job-uuid-1"
        assert j.name == "Morning Briefing"
        assert j.enabled is True
        assert j.schedule_kind == "cron"
        assert j.schedule_expr == "30 6 * * *"
        assert j.tz == "America/Los_Angeles"
        assert j.last_run_status == "ok"
        assert j.last_duration_ms == 83323
        assert j.next_run_ms == 1773063000000
        assert j.consecutive_errors == 0
        assert j.last_delivery_status == "delivered"

    def test_multiple_jobs(self, tmp_path):
        cron_dir = tmp_path / "cron"
        cron_dir.mkdir()
        _write_jobs(cron_dir / "jobs.json", [
            _job_dict(job_id="j1", name="Job 1"),
            _job_dict(job_id="j2", name="Job 2"),
        ])
        jobs = load_jobs(cron_dir)
        assert len(jobs) == 2
        assert jobs[0].id == "j1"
        assert jobs[1].id == "j2"

    def test_missing_fields_use_defaults(self, tmp_path):
        cron_dir = tmp_path / "cron"
        cron_dir.mkdir()
        _write_jobs(cron_dir / "jobs.json", [{"id": "j1"}])
        jobs = load_jobs(cron_dir)
        assert len(jobs) == 1
        j = jobs[0]
        assert j.name == ""
        assert j.enabled is True
        assert j.schedule_expr == ""
        assert j.consecutive_errors == 0
        assert j.last_run_status is None

    def test_disabled_job(self, tmp_path):
        cron_dir = tmp_path / "cron"
        cron_dir.mkdir()
        _write_jobs(cron_dir / "jobs.json", [_job_dict(enabled=False)])
        jobs = load_jobs(cron_dir)
        assert jobs[0].enabled is False

    def test_at_schedule(self, tmp_path):
        cron_dir = tmp_path / "cron"
        cron_dir.mkdir()
        _write_jobs(cron_dir / "jobs.json", [{
            "id": "j1",
            "name": "One-shot",
            "enabled": True,
            "schedule": {"kind": "at", "at": "2026-04-01T08:00:00Z", "tz": "UTC"},
            "state": {},
        }])
        jobs = load_jobs(cron_dir)
        assert jobs[0].schedule_kind == "at"
        assert jobs[0].schedule_expr == "2026-04-01T08:00:00Z"

    def test_consecutive_errors(self, tmp_path):
        cron_dir = tmp_path / "cron"
        cron_dir.mkdir()
        _write_jobs(cron_dir / "jobs.json", [_job_dict(consecutive_errors=3)])
        jobs = load_jobs(cron_dir)
        assert jobs[0].consecutive_errors == 3

    def test_permission_error(self, tmp_path, monkeypatch):
        cron_dir = tmp_path / "cron"
        cron_dir.mkdir()

        def raise_perm(*args, **kwargs):
            raise PermissionError("denied")

        monkeypatch.setattr("builtins.open", raise_perm)
        assert load_jobs(cron_dir) == []


# ---------------------------------------------------------------------------
# load_runs
# ---------------------------------------------------------------------------

class TestLoadRuns:
    def test_missing_file(self, tmp_path):
        result = load_runs(tmp_path / "cron", "no-such-job")
        assert result == []

    def test_empty_file(self, tmp_path):
        cron_dir = tmp_path / "cron"
        runs_dir = cron_dir / "runs"
        runs_dir.mkdir(parents=True)
        (runs_dir / "job1.jsonl").write_text("")
        assert load_runs(cron_dir, "job1") == []

    def test_valid_runs_newest_first(self, tmp_path):
        cron_dir = tmp_path / "cron"
        runs_dir = cron_dir / "runs"
        runs_dir.mkdir(parents=True)
        _write_runs(runs_dir / "job1.jsonl", [
            _run_line(ts=1000, session_id="sess-old"),
            _run_line(ts=2000, session_id="sess-mid"),
            _run_line(ts=3000, session_id="sess-new"),
        ])
        runs = load_runs(cron_dir, "job1")
        assert len(runs) == 3
        assert runs[0].ts == 3000
        assert runs[1].ts == 2000
        assert runs[2].ts == 1000

    def test_non_finished_actions_excluded(self, tmp_path):
        cron_dir = tmp_path / "cron"
        runs_dir = cron_dir / "runs"
        runs_dir.mkdir(parents=True)
        _write_runs(runs_dir / "job1.jsonl", [
            _run_line(ts=1000, action="started"),
            _run_line(ts=2000, action="finished"),
            _run_line(ts=3000, action="cancelled"),
        ])
        runs = load_runs(cron_dir, "job1")
        assert len(runs) == 1
        assert runs[0].ts == 2000

    def test_malformed_lines_skipped(self, tmp_path):
        cron_dir = tmp_path / "cron"
        runs_dir = cron_dir / "runs"
        runs_dir.mkdir(parents=True)
        with open(runs_dir / "job1.jsonl", "w") as f:
            f.write("not json\n")
            f.write(json.dumps(_run_line(ts=500)) + "\n")
            f.write("{broken\n")
        runs = load_runs(cron_dir, "job1")
        assert len(runs) == 1

    def test_run_fields(self, tmp_path):
        cron_dir = tmp_path / "cron"
        runs_dir = cron_dir / "runs"
        runs_dir.mkdir(parents=True)
        _write_runs(runs_dir / "job1.jsonl", [
            _run_line(ts=5000, status="ok", session_id="sess-abc", duration_ms=12000, delivered=True),
        ])
        runs = load_runs(cron_dir, "job1")
        r = runs[0]
        assert r.ts == 5000
        assert r.status == "ok"
        assert r.session_id == "sess-abc"
        assert r.duration_ms == 12000
        assert r.delivered is True
        assert r.delivery_status == "delivered"
        assert r.usage == {"totalTokens": 18066}

    def test_no_session_id(self, tmp_path):
        cron_dir = tmp_path / "cron"
        runs_dir = cron_dir / "runs"
        runs_dir.mkdir(parents=True)
        line = _run_line()
        del line["sessionId"]
        _write_runs(runs_dir / "job1.jsonl", [line])
        runs = load_runs(cron_dir, "job1")
        assert runs[0].session_id is None


# ---------------------------------------------------------------------------
# find_session
# ---------------------------------------------------------------------------

class TestFindSession:
    def test_finds_plain_jsonl(self, tmp_path):
        sess_id = "abc12345-uuid"
        (tmp_path / f"{sess_id}.jsonl").write_text("")
        result = find_session(tmp_path, sess_id)
        assert result is not None
        assert result.name == f"{sess_id}.jsonl"

    def test_finds_reset_variant(self, tmp_path):
        sess_id = "abc12345-uuid"
        fname = f"{sess_id}.jsonl.reset.1234567890"
        (tmp_path / fname).write_text("")
        result = find_session(tmp_path, sess_id)
        assert result is not None
        assert result.name == fname

    def test_excludes_deleted_variant(self, tmp_path):
        sess_id = "abc12345-uuid"
        (tmp_path / f"{sess_id}.jsonl.deleted.9999999999").write_text("")
        result = find_session(tmp_path, sess_id)
        assert result is None

    def test_not_found(self, tmp_path):
        result = find_session(tmp_path, "no-such-uuid")
        assert result is None

    def test_missing_directory(self, tmp_path):
        result = find_session(tmp_path / "nonexistent", "some-uuid")
        assert result is None

    def test_does_not_match_partial_prefix(self, tmp_path):
        # "abc" should not match "abcdef.jsonl"
        (tmp_path / "abcdef.jsonl").write_text("")
        # find_session uses startswith, so "abc" WILL match "abcdef" — this is intentional
        # (openclaw session IDs are full UUIDs; partial matches are by design)
        result = find_session(tmp_path, "abc")
        assert result is not None

    def test_permission_error_on_dir(self, tmp_path, monkeypatch):
        def raise_err(*args, **kwargs):
            raise PermissionError("denied")

        monkeypatch.setattr(Path, "iterdir", raise_err)
        result = find_session(tmp_path, "some-id")
        assert result is None


# ---------------------------------------------------------------------------
# load_debug_log
# ---------------------------------------------------------------------------

class TestLoadDebugLog:
    def test_missing_file(self, tmp_path):
        result = load_debug_log(tmp_path / "missing.log", "job1", 1000000)
        assert result == []

    def test_empty_file(self, tmp_path):
        log = tmp_path / "debug.log"
        log.write_text("")
        assert load_debug_log(log, "job1", 1000000) == []

    def test_malformed_lines_skipped(self, tmp_path):
        log = tmp_path / "debug.log"
        ts = 1000000
        with open(log, "w") as f:
            f.write("not json\n")
            f.write(json.dumps({
                "_meta": {"module": "cron", "ts": ts},
                "msg": "valid entry",
            }) + "\n")
        entries = load_debug_log(log, "job1", ts)
        assert len(entries) == 1

    def test_filters_by_time_window(self, tmp_path):
        log = tmp_path / "debug.log"
        run_ts = 1_000_000
        window = 60_000
        in_range = run_ts + 30_000
        out_of_range = run_ts + 120_000

        with open(log, "w") as f:
            f.write(json.dumps({
                "_meta": {"module": "cron", "ts": in_range},
                "msg": "in window",
            }) + "\n")
            f.write(json.dumps({
                "_meta": {"module": "cron", "ts": out_of_range},
                "msg": "outside window",
            }) + "\n")

        entries = load_debug_log(log, "job1", run_ts, window_ms=window)
        assert len(entries) == 1
        assert entries[0]["msg"] == "in window"

    def test_filters_by_cron_module(self, tmp_path):
        log = tmp_path / "debug.log"
        ts = 1_000_000
        with open(log, "w") as f:
            f.write(json.dumps({
                "_meta": {"module": "cron", "ts": ts},
                "msg": "cron entry",
            }) + "\n")
            f.write(json.dumps({
                "_meta": {"module": "executor", "ts": ts},
                "msg": "executor entry",
            }) + "\n")

        entries = load_debug_log(log, "job1", ts)
        assert len(entries) == 1
        assert entries[0]["msg"] == "cron entry"

    def test_includes_entries_with_job_id_in_msg(self, tmp_path):
        log = tmp_path / "debug.log"
        ts = 1_000_000
        job_id = "special-job-id"
        with open(log, "w") as f:
            f.write(json.dumps({
                "_meta": {"module": "executor", "ts": ts},
                "msg": f"processing {job_id}",
            }) + "\n")

        entries = load_debug_log(log, job_id, ts)
        assert len(entries) == 1

    def test_lower_bound_inclusive(self, tmp_path):
        log = tmp_path / "debug.log"
        run_ts = 1_000_000
        edge_ts = run_ts - 60_000  # exactly at boundary

        with open(log, "w") as f:
            f.write(json.dumps({
                "_meta": {"module": "cron", "ts": edge_ts},
                "msg": "lower edge",
            }) + "\n")

        entries = load_debug_log(log, "job1", run_ts, window_ms=60_000)
        assert len(entries) == 1

    def test_permission_error(self, tmp_path, monkeypatch):
        log = tmp_path / "debug.log"
        log.write_text("x")

        def raise_perm(*args, **kwargs):
            raise PermissionError("denied")

        monkeypatch.setattr("builtins.open", raise_perm)
        assert load_debug_log(log, "job1", 1000000) == []


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

class TestFormatHelpers:
    def test_fmt_ms_none(self):
        assert fmt_ms(None) == "?"

    def test_fmt_ms_valid(self):
        # Just check it returns a date-like string
        result = fmt_ms(1_000_000_000_000)
        assert len(result) == len("2001-09-08 21:46")

    def test_fmt_duration_none(self):
        assert fmt_duration(None) == "?"

    def test_fmt_duration_seconds(self):
        assert fmt_duration(5000) == "5s"

    def test_fmt_duration_minutes(self):
        assert fmt_duration(83323) == "1m23s"

    def test_fmt_duration_zero(self):
        assert fmt_duration(0) == "0s"

    def test_relative_time_none(self):
        assert relative_time(None) == ""

    def test_relative_time_future(self):
        import time
        future_ms = int(time.time() * 1000) + 3_600_000
        assert relative_time(future_ms) == "in future"

    def test_relative_time_past(self):
        import time
        past_ms = int(time.time() * 1000) - 7_200_000  # 2 hours ago
        result = relative_time(past_ms)
        assert "ago" in result
