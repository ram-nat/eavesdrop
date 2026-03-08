"""Cron job and run data model and parsers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class CronJob:
    id: str
    name: str
    enabled: bool
    schedule_kind: str      # "cron" | "at"
    schedule_expr: str      # cron expr or ISO timestamp
    tz: str
    next_run_ms: int | None
    last_run_ms: int | None
    last_run_status: str | None   # "ok" | "error" | None
    last_duration_ms: int | None
    last_delivery_status: str | None
    consecutive_errors: int


@dataclass
class CronRun:
    ts: int                 # ms epoch when run was recorded
    action: str             # "finished" | "started" | etc.
    status: str             # "ok" | "error"
    summary: str
    session_id: str | None
    duration_ms: int | None
    delivered: bool | None
    delivery_status: str
    usage: dict = field(default_factory=dict)


@dataclass
class CronRunContext:
    job: CronJob
    run: CronRun
    debug_log_path: Path | None = None


def load_jobs(cron_dir: Path) -> list[CronJob]:
    """Load job definitions from cron/jobs.json."""
    jobs_file = cron_dir / "jobs.json"
    try:
        with open(jobs_file, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, PermissionError, OSError, json.JSONDecodeError):
        return []

    jobs = []
    for job in data.get("jobs", []):
        schedule = job.get("schedule", {}) or {}
        state = job.get("state", {}) or {}
        # "at" schedules use an "at" key; "cron" schedules use "expr"
        expr = schedule.get("expr") or schedule.get("at") or ""
        jobs.append(CronJob(
            id=job.get("id", ""),
            name=job.get("name", ""),
            enabled=job.get("enabled", True),
            schedule_kind=schedule.get("kind", "cron"),
            schedule_expr=expr,
            tz=schedule.get("tz", ""),
            next_run_ms=state.get("nextRunAtMs"),
            last_run_ms=state.get("lastRunAtMs"),
            last_run_status=state.get("lastRunStatus"),
            last_duration_ms=state.get("lastDurationMs"),
            last_delivery_status=state.get("lastDeliveryStatus"),
            consecutive_errors=state.get("consecutiveErrors", 0),
        ))
    return jobs


def load_runs(cron_dir: Path, job_id: str) -> list[CronRun]:
    """Load run history for a job, newest first. Only 'finished' actions."""
    runs_file = cron_dir / "runs" / f"{job_id}.jsonl"
    runs = []
    try:
        with open(runs_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("action") != "finished":
                    continue
                runs.append(CronRun(
                    ts=obj.get("ts", 0),
                    action=obj.get("action", ""),
                    status=obj.get("status", ""),
                    summary=obj.get("summary", ""),
                    session_id=obj.get("sessionId"),
                    duration_ms=obj.get("durationMs"),
                    delivered=obj.get("delivered"),
                    delivery_status=obj.get("deliveryStatus", ""),
                    usage=obj.get("usage") or {},
                ))
    except (FileNotFoundError, PermissionError, OSError):
        return []
    return list(reversed(runs))


def find_session(sessions_dir: Path, session_id: str) -> Path | None:
    """Find the session file (any non-deleted variant) matching session_id."""
    try:
        for p in sessions_dir.iterdir():
            if (
                p.name.startswith(session_id)
                and ".jsonl" in p.name
                and ".deleted." not in p.name
            ):
                return p
    except (FileNotFoundError, PermissionError, OSError):
        pass
    return None


def load_debug_log(
    log_path: Path,
    job_id: str,
    run_at_ms: int,
    window_ms: int = 60_000,
) -> list[dict]:
    """Load debug log entries near a run timestamp.

    Filters to entries within ±window_ms of run_at_ms that belong to the
    cron module or reference the job_id.
    """
    entries = []
    lo = run_at_ms - window_ms
    hi = run_at_ms + window_ms

    try:
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                meta = obj.get("_meta", {}) or {}
                raw_ts = meta.get("ts", obj.get("ts", 0))
                ts_ms: int = 0
                if isinstance(raw_ts, (int, float)):
                    ts_ms = int(raw_ts)
                elif isinstance(raw_ts, str) and raw_ts:
                    try:
                        dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                        ts_ms = int(dt.timestamp() * 1000)
                    except Exception:
                        pass

                if ts_ms < lo or ts_ms > hi:
                    continue

                module = meta.get("module", "")
                msg = str(obj.get("msg", ""))
                if module != "cron" and job_id not in msg and job_id not in str(obj):
                    continue

                entries.append(obj)
    except (FileNotFoundError, PermissionError, OSError):
        pass

    return entries


def fmt_ms(ts_ms: int | None) -> str:
    """Format a millisecond epoch timestamp as a local datetime string."""
    if ts_ms is None:
        return "?"
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "?"


def fmt_duration(ms: int | None) -> str:
    """Format a millisecond duration as a human-readable string."""
    if ms is None:
        return "?"
    s = ms // 1000
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m{s % 60:02d}s"


def relative_time(ts_ms: int | None) -> str:
    """Return a human-readable relative time (e.g. '2h ago')."""
    if ts_ms is None:
        return ""
    try:
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        diff = now_ms - ts_ms
        if diff < 0:
            return "in future"
        s = diff // 1000
        if s < 60:
            return f"{s}s ago"
        m = s // 60
        if m < 60:
            return f"{m}m ago"
        h = m // 60
        if h < 24:
            return f"{h}h ago"
        return f"{h // 24}d ago"
    except Exception:
        return ""
