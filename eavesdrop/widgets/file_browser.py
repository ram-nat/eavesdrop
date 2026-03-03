"""Left panel: session file browser."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.widgets import ListView, ListItem, Label
from textual.reactive import reactive

from eavesdrop.parser import scan_sessions, session_summary, session_uuid


def _fmt_ts(ts: str) -> str:
    if not ts:
        return "?"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        local = dt.astimezone()
        return local.strftime("%m-%d %H:%M")
    except Exception:
        return ts[:16]


def _short_id(path: Path) -> str:
    return session_uuid(path)[:8]


class SessionItem(ListItem):
    def __init__(self, summary: dict, **kwargs):
        super().__init__(**kwargs)
        self.summary = summary
        self._path = summary["path"]

    @property
    def session_path(self) -> Path:
        return self._path

    def compose(self) -> ComposeResult:
        s = self.summary
        short_id = _short_id(s["path"])
        ts = _fmt_ts(s["timestamp"])
        model = s["model"] or "unknown"
        # Shorten model name if long
        if len(model) > 22:
            model = model[:20] + ".."
        msgs = s["message_count"]
        tools = s["tool_count"]

        line1 = f"{short_id}  {ts}"
        line2 = f"  {model}"
        line3 = f"  {msgs} msgs  {tools} tools"

        yield Label(line1, classes="session-id-line")
        yield Label(line2, classes="session-model-line")
        yield Label(line3, classes="session-stats-line")


class FileBrowser(ListView):
    """Scrollable list of session files."""

    COMPONENT_CLASSES = {"session-id-line", "session-model-line", "session-stats-line"}

    DEFAULT_CSS = """
    FileBrowser {
        width: 28;
        border-right: solid $panel;
    }
    FileBrowser > SessionItem {
        padding: 0 1;
        height: 3;
    }
    FileBrowser > SessionItem.--highlight {
        background: $accent 20%;
    }
    FileBrowser > SessionItem Label {
        width: 100%;
    }
    FileBrowser > SessionItem .session-id-line {
        color: $text;
        text-style: bold;
    }
    FileBrowser > SessionItem .session-model-line {
        color: $text-muted;
    }
    FileBrowser > SessionItem .session-stats-line {
        color: $text-disabled;
    }
    """

    def __init__(self, sessions_dir: Path, **kwargs):
        super().__init__(**kwargs)
        self._sessions_dir = sessions_dir
        self._summaries: list[dict] = []

    def on_mount(self) -> None:
        self.load_sessions()

    def load_sessions(self) -> None:
        self.clear()
        paths = scan_sessions(self._sessions_dir)
        self._summaries = [session_summary(p) for p in paths]
        for s in self._summaries:
            self.append(SessionItem(s))

    @property
    def selected_path(self) -> Path | None:
        item = self.highlighted_child
        if isinstance(item, SessionItem):
            return item.session_path
        return None
