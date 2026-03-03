"""Right panel: scrollable conversation view."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Label

from eavesdrop.parser import parse_file, Message, ModelChange, ParsedSession
from eavesdrop.widgets.turn import (
    AssistantTurn,
    UserTurn,
    ToolResultBlock,
    ModelChangeTurn,
)


class ConversationView(VerticalScroll):
    DEFAULT_CSS = """
    ConversationView {
        padding: 0 1;
    }
    ConversationView .empty-label {
        color: $text-disabled;
        padding: 2;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._session: ParsedSession | None = None
        self._assistant_turns: list[AssistantTurn] = []
        self._tool_result_blocks: list[ToolResultBlock] = []
        self._show_thinking = False
        self._show_usage = False
        self._tools_expanded = False

    def compose(self) -> ComposeResult:
        yield Label("No session loaded.", classes="empty-label")

    def load_session(self, path: Path) -> None:
        self._session = parse_file(path)
        self._assistant_turns = []
        self._tool_result_blocks = []
        self._rebuild()

    def _rebuild(self) -> None:
        self.remove_children()
        self._assistant_turns = []
        self._tool_result_blocks = []

        if self._session is None:
            self.mount(Label("No session loaded.", classes="empty-label"))
            return

        if self._session.error:
            self.mount(Label(f"Permission denied: {self._session.error}", classes="empty-label"))
            return

        for event in self._session.events:
            if isinstance(event, ModelChange):
                self.mount(ModelChangeTurn(event))
            elif isinstance(event, Message):
                if event.role == "user":
                    self.mount(UserTurn(event))
                elif event.role == "assistant":
                    at = AssistantTurn(event)
                    self._assistant_turns.append(at)
                    self.mount(at)
                    # Apply current state
                    at.set_thinking_visible(self._show_thinking)
                    at.set_tools_expanded(self._tools_expanded)
                    at.set_usage_visible(self._show_usage)
                elif event.role == "toolResult":
                    tr = ToolResultBlock(event)
                    self._tool_result_blocks.append(tr)
                    self.mount(tr)
                    tr.expanded = self._tools_expanded

        self.scroll_home(animate=False)

    def reload(self, path: Path) -> None:
        self.load_session(path)

    def toggle_thinking(self) -> bool:
        self._show_thinking = not self._show_thinking
        for at in self._assistant_turns:
            at.set_thinking_visible(self._show_thinking)
        return self._show_thinking

    def toggle_tools(self) -> bool:
        self._tools_expanded = not self._tools_expanded
        for at in self._assistant_turns:
            at.set_tools_expanded(self._tools_expanded)
        for tr in self._tool_result_blocks:
            tr.expanded = self._tools_expanded
        return self._tools_expanded

    def toggle_usage(self) -> bool:
        self._show_usage = not self._show_usage
        for at in self._assistant_turns:
            at.set_usage_visible(self._show_usage)
        return self._show_usage
