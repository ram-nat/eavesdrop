"""Textual App: eavesdrop TUI."""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Label

from eavesdrop.cron_parser import CronRunContext, load_debug_log
from eavesdrop.parser import scan_sessions, session_uuid
from eavesdrop.widgets.conversation import ConversationView
from eavesdrop.widgets.cron_browser import CronBrowser
from eavesdrop.widgets.file_browser import FileBrowser

DEFAULT_SESSIONS_DIR = Path(
    os.environ.get(
        "EAVESDROP_SESSIONS_DIR",
        Path.home() / ".openclaw" / "agents" / "main-cloud" / "sessions",
    )
)

DEFAULT_OPENCLAW_DIR = Path(
    os.environ.get(
        "EAVESDROP_OPENCLAW_DIR",
        DEFAULT_SESSIONS_DIR.parent.parent.parent,  # agents/main-cloud/sessions → root
    )
)


class EavesdropApp(App):
    TITLE = "eavesdrop"

    CSS = """
    Screen {
        layout: horizontal;
    }
    FileBrowser {
        width: 28;
        height: 100%;
    }
    CronBrowser {
        width: 28;
        height: 100%;
    }
    ConversationView {
        width: 1fr;
        height: 100%;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("t", "toggle_thinking", "Thinking"),
        Binding("T", "toggle_turns", "Collapse turns"),
        Binding("e", "toggle_tools", "Expand tools"),
        Binding("dollar_sign", "toggle_usage", "Costs", key_display="$"),
        Binding("r", "reload", "Reload"),
        Binding("f", "toggle_follow", "Follow"),
        Binding("C", "toggle_cron", "Cron", key_display="C"),
        Binding("enter", "load_selected", "Load", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(
        self,
        sessions_dir: Path = DEFAULT_SESSIONS_DIR,
        initial_session: Path | None = None,
        openclaw_dir: Path = DEFAULT_OPENCLAW_DIR,
        start_cron: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._sessions_dir = sessions_dir
        self._initial_session = initial_session
        self._openclaw_dir = openclaw_dir
        self._start_cron = start_cron
        self._current_path: Path | None = None
        self._follow_mode: bool = False
        self._follow_mtime: float = 0.0
        self._follow_inode: int = 0
        self._follow_timer = None
        self._cron_mode: bool = start_cron

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield FileBrowser(self._sessions_dir, id="browser")
            cron_dir = self._openclaw_dir / "cron"
            yield CronBrowser(cron_dir, self._sessions_dir, id="cron-browser")
            yield ConversationView(id="conversation")
        yield Footer()

    def on_mount(self) -> None:
        # Apply initial panel visibility
        browser = self.query_one("#browser", FileBrowser)
        cron = self.query_one("#cron-browser", CronBrowser)
        if self._cron_mode:
            browser.display = False
        else:
            cron.display = False

        if self._initial_session:
            self._load(self._initial_session)
        elif not self._cron_mode:
            paths = scan_sessions(self._sessions_dir)
            if paths:
                self._load(paths[0])

    def _load(self, path: Path | None, cron_context: CronRunContext | None = None) -> None:
        self._current_path = path
        conv = self.query_one("#conversation", ConversationView)
        conv.load_session(path, cron_context=cron_context)
        if path is not None:
            self.sub_title = session_uuid(path)[:8]
        elif cron_context is not None:
            self.sub_title = cron_context.job.name[:20]

    def action_load_selected(self) -> None:
        if self._cron_mode:
            return
        browser = self.query_one("#browser", FileBrowser)
        path = browser.selected_path
        if path:
            self._load(path)

    def action_toggle_thinking(self) -> None:
        conv = self.query_one("#conversation", ConversationView)
        conv.toggle_thinking()

    def action_toggle_tools(self) -> None:
        conv = self.query_one("#conversation", ConversationView)
        conv.toggle_tools()

    def action_toggle_turns(self) -> None:
        conv = self.query_one("#conversation", ConversationView)
        conv.toggle_turns()

    def action_toggle_usage(self) -> None:
        conv = self.query_one("#conversation", ConversationView)
        conv.toggle_usage()

    def action_reload(self) -> None:
        if self._cron_mode:
            self.query_one("#cron-browser", CronBrowser).refresh_jobs()
            return
        browser = self.query_one("#browser", FileBrowser)
        current_path = self._current_path
        browser.load_sessions()
        if current_path:
            browser.select_path(current_path)
            conv = self.query_one("#conversation", ConversationView)
            conv.reload(current_path)

    def action_cursor_down(self) -> None:
        if self._cron_mode:
            self.query_one("#cron-browser", CronBrowser).action_cursor_down()
        else:
            self.query_one("#browser", FileBrowser).action_cursor_down()

    def action_cursor_up(self) -> None:
        if self._cron_mode:
            self.query_one("#cron-browser", CronBrowser).action_cursor_up()
        else:
            self.query_one("#browser", FileBrowser).action_cursor_up()

    def action_toggle_cron(self) -> None:
        self._cron_mode = not self._cron_mode
        browser = self.query_one("#browser", FileBrowser)
        cron = self.query_one("#cron-browser", CronBrowser)
        if self._cron_mode:
            browser.display = False
            cron.display = True
        else:
            cron.display = False
            browser.display = True

    def on_list_view_selected(self, event) -> None:
        from eavesdrop.widgets.file_browser import SessionItem
        if isinstance(event.item, SessionItem):
            self._load(event.item.session_path)

    def on_cron_browser_session_requested(self, event: CronBrowser.SessionRequested) -> None:
        debug_log_path = self._openclaw_dir / "logs" / "openclaw-debug.log"
        if not debug_log_path.exists():
            debug_log_path = None
        ctx = CronRunContext(
            job=event.job,
            run=event.run,
            debug_log_path=debug_log_path,
        )
        self._load(event.path, cron_context=ctx)


    def action_toggle_follow(self) -> None:
        self._follow_mode = not self._follow_mode
        if self._follow_mode:
            self._update_follow_title()
            self._snapshot_file_state()
            self._follow_timer = self.set_interval(1.0, self._poll_follow)
        else:
            if self._follow_timer is not None:
                self._follow_timer.stop()
                self._follow_timer = None
            self._update_follow_title()

    def _update_follow_title(self) -> None:
        if self._follow_mode:
            self.sub_title = (self.sub_title.rstrip(" [FOLLOW]") + " [FOLLOW]")
        else:
            self.sub_title = self.sub_title.rstrip(" [FOLLOW]").rstrip()

    def _snapshot_file_state(self) -> None:
        if self._current_path is None:
            return
        try:
            st = self._current_path.stat()
            self._follow_mtime = st.st_mtime
            self._follow_inode = st.st_ino
        except OSError:
            pass

    def _poll_follow(self) -> None:
        if not self._follow_mode or self._current_path is None:
            return
        try:
            st = self._current_path.stat()
        except OSError:
            return
        # File replaced (rotation) or shrunk → full reload
        if st.st_ino != self._follow_inode or st.st_mtime < self._follow_mtime:
            self._follow_mtime = st.st_mtime
            self._follow_inode = st.st_ino
            conv = self.query_one("#conversation", ConversationView)
            conv.reload(self._current_path)
            return
        if st.st_mtime == self._follow_mtime:
            return
        # File grew — partial append
        self._follow_mtime = st.st_mtime
        conv = self.query_one("#conversation", ConversationView)
        conv.append_new_lines(self._current_path)
