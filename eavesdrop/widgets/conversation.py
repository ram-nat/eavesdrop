"""Right panel: scrollable conversation view."""

from __future__ import annotations

import json
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Input, Label

from eavesdrop.parser import parse_file, Message, ModelChange, ParsedSession
from eavesdrop.widgets.turn import (
    AssistantTurn,
    FinalBlock,
    ModelChangeTurn,
    ToolCallBlock,
    ToolResultBlock,
    UserTurn,
)


def _block_text(block) -> str:
    if isinstance(block, ToolCallBlock):
        parts = [block._tool_name]
        args = block._arguments
        if isinstance(args, str):
            parts.append(args)
        elif isinstance(args, dict):
            parts.append(json.dumps(args))
        elif args is not None:
            parts.append(str(args))
        return " ".join(parts)
    elif isinstance(block, ToolResultBlock):
        return block._message.tool_name + " " + block._get_text()
    elif isinstance(block, FinalBlock):
        return block._text
    return ""


class ConversationView(VerticalScroll):
    BINDINGS = [
        Binding("slash", "open_search", "Search", show=True),
        Binding("n", "next_match", "Next match", show=False),
        Binding("N", "prev_match", "Prev match", show=False),
        Binding("escape", "close_search", "Close search", show=False),
    ]

    DEFAULT_CSS = """
    ConversationView {
        padding: 0 1;
    }
    ConversationView .empty-label {
        color: $text-disabled;
        padding: 2;
    }
    #search-bar-row {
        dock: bottom;
        height: 3;
        background: $panel;
        display: none;
    }
    #search-input {
        width: 1fr;
    }
    #search-counter {
        width: auto;
        min-width: 8;
        content-align: center middle;
        color: $text-muted;
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
        self._search_matches: list = []
        self._search_index: int = 0
        self._search_active: bool = False

    def compose(self) -> ComposeResult:
        yield Label("No session loaded.", classes="empty-label")
        with Horizontal(id="search-bar-row"):
            yield Input(placeholder="Search…", id="search-input")
            yield Label("", id="search-counter")

    def load_session(self, path: Path) -> None:
        self._session = parse_file(path)
        self._assistant_turns = []
        self._tool_result_blocks = []
        self._rebuild()

    def _rebuild(self) -> None:
        for child in list(self.children):
            if child.id != "search-bar-row":
                child.remove()
        self._assistant_turns = []
        self._tool_result_blocks = []
        self._search_matches = []
        self._search_index = 0
        try:
            self._update_counter_label()
        except Exception:
            pass

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

    def _collect_searchable_blocks(self) -> list:
        return [
            w for w in self.query("*")
            if isinstance(w, (ToolCallBlock, ToolResultBlock, FinalBlock))
        ]

    def _update_counter_label(self) -> None:
        label = self.query_one("#search-counter", Label)
        if self._search_matches:
            label.update(f" {self._search_index + 1}/{len(self._search_matches)} ")
        else:
            label.update(" 0/0 " if self._search_active else "")

    def _jump_to(self, index: int) -> None:
        block = self._search_matches[index]
        block.expanded = True
        block.focus()
        block.scroll_visible(animate=False)

    def _run_search(self, query: str) -> None:
        q = query.lower()
        self._search_matches = [
            b for b in self._collect_searchable_blocks()
            if q in _block_text(b).lower()
        ]
        self._search_index = 0
        self._update_counter_label()
        if self._search_matches:
            self._jump_to(0)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "search-input":
            return
        query = event.value.strip()
        if query:
            self._run_search(query)

    def action_open_search(self) -> None:
        self._search_active = True
        self.query_one("#search-bar-row").display = True
        self.query_one("#search-input", Input).focus()

    def action_close_search(self) -> None:
        self._search_active = False
        self._search_matches = []
        self._search_index = 0
        self.query_one("#search-bar-row").display = False
        self.query_one("#search-input", Input).clear()
        self._update_counter_label()
        self.focus()

    def action_next_match(self) -> None:
        if not self._search_matches:
            return
        self._search_index = (self._search_index + 1) % len(self._search_matches)
        self._jump_to(self._search_index)
        self._update_counter_label()

    def action_prev_match(self) -> None:
        if not self._search_matches:
            return
        self._search_index = (self._search_index - 1) % len(self._search_matches)
        self._jump_to(self._search_index)
        self._update_counter_label()
