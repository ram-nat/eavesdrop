"""Left panel: two-level cron job browser."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message as TextualMessage
from textual.widget import Widget
from textual.widgets import ListView, ListItem, Label

from eavesdrop.cron_parser import (
    CronJob,
    CronRun,
    load_jobs,
    load_runs,
    find_session,
    fmt_ms,
    fmt_duration,
    relative_time,
)


class CronJobItem(ListItem):
    def __init__(self, job: CronJob, **kwargs):
        super().__init__(**kwargs)
        self.job = job

    def compose(self) -> ComposeResult:
        j = self.job

        badges = []
        if not j.enabled:
            badges.append("[off]")
        elif j.consecutive_errors > 0:
            badges.append(f"[!{j.consecutive_errors}]")
        if j.last_delivery_status == "pending":
            badges.append("[→]")

        name_line = j.name
        if badges:
            name_line += "  " + " ".join(badges)
        yield Label(name_line, classes="cron-job-name")

        tz_short = j.tz.split("/")[-1].replace("_", " ") if j.tz else ""
        sched = j.schedule_expr
        if tz_short:
            sched += f" ({tz_short})"
        yield Label(sched, classes="cron-job-sched")

        status = j.last_run_status or "never"
        ago = relative_time(j.last_run_ms) if j.last_run_ms else ""
        last_str = f"last: {status}"
        if ago:
            last_str += f"  {ago}"
        if j.next_run_ms:
            last_str += f"    next: {fmt_ms(j.next_run_ms)}"
        yield Label(last_str, classes="cron-job-meta")


class CronRunItem(ListItem):
    def __init__(self, run: CronRun, **kwargs):
        super().__init__(**kwargs)
        self.run = run

    def compose(self) -> ComposeResult:
        r = self.run

        status_badge = f"[{r.status}]" if r.status else "[?]"
        duration = fmt_duration(r.duration_ms)

        extra = []
        if r.status == "error":
            extra.append("[err]")
        if r.delivered is False:
            extra.append("[!delivery]")
        if not r.session_id:
            extra.append("[no session]")

        line1 = f"{fmt_ms(r.ts)}  {status_badge}  {duration}"
        if r.delivered:
            line1 += "  delivered"
        if extra:
            line1 += "  " + " ".join(extra)
        yield Label(line1, classes="cron-run-line1")

        if r.session_id:
            yield Label(f"session: {r.session_id[:7]}…", classes="cron-run-session")
        elif r.summary:
            summ = r.summary[:40] + "…" if len(r.summary) > 40 else r.summary
            yield Label(summ, classes="cron-run-session")
        else:
            yield Label("(no session)", classes="cron-run-session")


class CronBrowser(Widget):
    """Two-level browser: jobs list → runs list for a selected job."""

    BINDINGS = [
        Binding("escape", "back", "Back", show=False),
        Binding("backspace", "back", "Back", show=False),
    ]

    DEFAULT_CSS = """
    CronBrowser {
        width: 28;
        height: 100%;
        border-right: solid $panel;
    }
    CronBrowser .cron-browser-header {
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    CronBrowser ListView {
        width: 100%;
        height: 1fr;
    }
    CronBrowser CronJobItem {
        padding: 0 1;
        height: 3;
    }
    CronBrowser CronJobItem.--highlight {
        background: $accent 20%;
    }
    CronBrowser CronRunItem {
        padding: 0 1;
        height: 2;
    }
    CronBrowser CronRunItem.--highlight {
        background: $accent 20%;
    }
    CronBrowser .cron-job-name {
        color: $text;
        text-style: bold;
        width: 100%;
    }
    CronBrowser .cron-job-sched {
        color: $text-muted;
        width: 100%;
    }
    CronBrowser .cron-job-meta {
        color: $text-disabled;
        width: 100%;
    }
    CronBrowser .cron-run-line1 {
        color: $text;
        width: 100%;
    }
    CronBrowser .cron-run-session {
        color: $text-muted;
        width: 100%;
    }
    """

    class SessionRequested(TextualMessage):
        def __init__(self, path: Path, run: CronRun, job: CronJob) -> None:
            super().__init__()
            self.path = path
            self.run = run
            self.job = job

    class NoSession(TextualMessage):
        def __init__(self, job_name: str, reason: str) -> None:
            super().__init__()
            self.job_name = job_name
            self.reason = reason

    def __init__(self, cron_dir: Path, sessions_dir: Path, **kwargs):
        super().__init__(**kwargs)
        self._cron_dir = cron_dir
        self._sessions_dir = sessions_dir
        self._level: str = "jobs"
        self._selected_job: CronJob | None = None
        self._jobs: list[CronJob] = []

    def compose(self) -> ComposeResult:
        yield Label("Cron Jobs", classes="cron-browser-header", id="cron-browser-header")
        yield ListView(id="cron-list")

    def on_mount(self) -> None:
        self.refresh_jobs()

    def refresh_jobs(self) -> None:
        self._jobs = load_jobs(self._cron_dir)
        self._level = "jobs"
        self._selected_job = None
        self._render_jobs()

    def _render_jobs(self) -> None:
        lv = self.query_one("#cron-list", ListView)
        lv.clear()
        self.query_one("#cron-browser-header", Label).update("Cron Jobs")
        for job in self._jobs:
            lv.append(CronJobItem(job))

    def _render_runs(self, job: CronJob) -> None:
        runs = load_runs(self._cron_dir, job.id)
        lv = self.query_one("#cron-list", ListView)
        lv.clear()
        name_short = job.name[:22]
        self.query_one("#cron-browser-header", Label).update(f"{name_short}  ↩Esc")
        for run in runs:
            lv.append(CronRunItem(run))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if self._level == "jobs" and isinstance(event.item, CronJobItem):
            self._selected_job = event.item.job
            self._level = "runs"
            self._render_runs(event.item.job)
        elif self._level == "runs" and isinstance(event.item, CronRunItem):
            run = event.item.run
            job = self._selected_job
            job_name = job.name if job else "?"
            if not run.session_id:
                self.post_message(self.NoSession(
                    job_name=job_name,
                    reason="No isolated session (job may use sessionTarget: main)",
                ))
                return
            path = find_session(self._sessions_dir, run.session_id)
            if path is None:
                sid = run.session_id[:8]
                self.post_message(self.NoSession(
                    job_name=job_name,
                    reason=f"Session file not found for ID {sid}…",
                ))
                return
            self.post_message(self.SessionRequested(path=path, run=run, job=job))

    def action_back(self) -> None:
        if self._level == "runs":
            self._level = "jobs"
            self._selected_job = None
            self._render_jobs()

    def action_cursor_down(self) -> None:
        self.query_one("#cron-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#cron-list", ListView).action_cursor_up()
