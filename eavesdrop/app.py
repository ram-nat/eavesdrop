"""Textual App: eavesdrop TUI."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Header

from eavesdrop.parser import scan_sessions, session_uuid
from eavesdrop.widgets.conversation import ConversationView
from eavesdrop.widgets.file_browser import FileBrowser

DEFAULT_SESSIONS_DIR = Path("/home/openclaw/.openclaw/agents/main-cloud/sessions")


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
        Binding("enter", "load_selected", "Load", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(
        self,
        sessions_dir: Path = DEFAULT_SESSIONS_DIR,
        initial_session: Path | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._sessions_dir = sessions_dir
        self._initial_session = initial_session
        self._current_path: Path | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield FileBrowser(self._sessions_dir, id="browser")
            yield ConversationView(id="conversation")
        yield Footer()

    def on_mount(self) -> None:
        if self._initial_session:
            self._load(self._initial_session)
        else:
            paths = scan_sessions(self._sessions_dir)
            if paths:
                self._load(paths[0])

    def _load(self, path: Path) -> None:
        self._current_path = path
        conv = self.query_one("#conversation", ConversationView)
        conv.load_session(path)
        short = session_uuid(path)[:8]
        self.sub_title = short

    def action_load_selected(self) -> None:
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
        browser = self.query_one("#browser", FileBrowser)
        current_path = self._current_path
        browser.load_sessions()
        if current_path:
            # Restore selection to the previously loaded session
            browser.select_path(current_path)
            conv = self.query_one("#conversation", ConversationView)
            conv.reload(current_path)

    def action_cursor_down(self) -> None:
        browser = self.query_one("#browser", FileBrowser)
        browser.action_cursor_down()

    def action_cursor_up(self) -> None:
        browser = self.query_one("#browser", FileBrowser)
        browser.action_cursor_up()

    def on_list_view_selected(self, event) -> None:
        from eavesdrop.widgets.file_browser import SessionItem
        if isinstance(event.item, SessionItem):
            self._load(event.item.session_path)
