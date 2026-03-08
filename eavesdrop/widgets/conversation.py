"""Right panel: scrollable conversation view."""

from __future__ import annotations

import json
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Input, Label

from eavesdrop.parser import parse_file, Message, ModelChange, ParsedSession, tool_result_has_error
from eavesdrop.cron_parser import CronRunContext, load_debug_log
from eavesdrop.widgets.turn import (
    AssistantTurn,
    CronRunHeader,
    DebugLogSection,
    FinalBlock,
    ModelChangeTurn,
    ToolCallBlock,
    ToolResultBlock,
    TurnSeparator,
    UserTurn,
    _is_final,
)


def _group_turns(events):
    """Returns (prologue: list, turns: list[list]).

    A turn starts at each user message and includes all following events
    up to (but not including) the next user message.
    """
    prologue, turns, current = [], [], None
    for event in events:
        if isinstance(event, Message) and event.role == "user":
            if current is not None:
                turns.append(current)
            current = [event]
        else:
            (current if current is not None else prologue).append(event)
    if current:
        turns.append(current)
    return prologue, turns


def _turn_meta(turn_events):
    """Returns (has_error, corrected, tool_count, total_cost)."""
    has_error = False
    tool_count = 0
    total_cost = 0.0
    last_assistant = None
    for event in turn_events:
        if not isinstance(event, Message):
            continue
        if event.role == "toolResult" and tool_result_has_error(event):
            has_error = True
        if event.role == "assistant":
            last_assistant = event
            tool_count += sum(1 for c in event.content if c.type == "toolCall")
            if event.usage:
                total_cost += event.usage.cost_total or 0.0
    corrected = (
        has_error
        and last_assistant is not None
        and last_assistant.stop_reason not in ("toolUse", None)
    )
    return has_error, corrected, tool_count, total_cost


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
    elif isinstance(block, UserTurn):
        parts = [c.text for c in block._message.content if c.type == "text" and c.text]
        return "\n".join(parts)
    elif isinstance(block, AssistantTurn):
        # Plain (non-final) text blocks in assistant turns
        parts = []
        for cb in block._message.content:
            if cb.type == "text" and cb.text.strip() and not _is_final(cb.text):
                parts.append(cb.text)
        return "\n".join(parts)
    return ""


class ConversationView(VerticalScroll):
    BINDINGS = [
        Binding("slash", "open_search", "Search", show=True),
        Binding("n", "next_match", "Next match", show=False),
        Binding("N", "prev_match", "Prev match", show=False),
        Binding("escape", "close_search", "Close search", show=False),
        Binding("[", "prev_turn", "Prev turn", show=False),
        Binding("]", "next_turn", "Next turn", show=False),
        Binding("d", "toggle_debug_log", "Debug log", show=False),
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
        self._current_path: Path | None = None
        self._file_byte_offset: int = 0
        self._assistant_turns: list[AssistantTurn] = []
        self._tool_result_blocks: list[ToolResultBlock] = []
        self._show_thinking = False
        self._show_usage = False
        self._tools_expanded = False
        self._search_matches: list = []
        self._search_index: int = 0
        self._search_active: bool = False
        self._turn_separators: list[TurnSeparator] = []
        self._turn_groups: list[tuple[TurnSeparator, list[Widget]]] = []
        self._turns_expanded = False
        self._cron_context: CronRunContext | None = None
        self._debug_section: DebugLogSection | None = None

    def compose(self) -> ComposeResult:
        yield Label("No session loaded.", classes="empty-label")
        with Horizontal(id="search-bar-row"):
            yield Input(placeholder="Search…", id="search-input")
            yield Label("", id="search-counter")

    def load_session(
        self,
        path: Path | None,
        cron_context: CronRunContext | None = None,
    ) -> None:
        self._current_path = path
        self._session = parse_file(path) if path is not None else None
        self._cron_context = cron_context
        self._assistant_turns = []
        self._tool_result_blocks = []
        self._debug_section = None
        self._rebuild()
        try:
            self._file_byte_offset = path.stat().st_size if path is not None else 0
        except OSError:
            self._file_byte_offset = 0

    def _mount_event(self, event) -> list:
        """Mount a single event widget and return the list of mounted widgets."""
        widgets = []
        if isinstance(event, ModelChange):
            w = ModelChangeTurn(event)
            self.mount(w)
            widgets.append(w)
        elif isinstance(event, Message):
            if event.role == "user":
                w = UserTurn(event)
                self.mount(w)
                widgets.append(w)
            elif event.role == "assistant":
                at = AssistantTurn(event)
                self._assistant_turns.append(at)
                self.mount(at)
                at.set_thinking_visible(self._show_thinking)
                at.set_tools_expanded(self._tools_expanded)
                at.set_usage_visible(self._show_usage)
                widgets.append(at)
            elif event.role == "toolResult":
                tr = ToolResultBlock(event)
                self._tool_result_blocks.append(tr)
                self.mount(tr)
                tr.expanded = self._tools_expanded
                widgets.append(tr)
        return widgets

    def _rebuild(self) -> None:
        for child in list(self.children):
            if child.id != "search-bar-row":
                child.remove()
        self._assistant_turns = []
        self._tool_result_blocks = []
        self._search_matches = []
        self._search_index = 0
        self._turn_separators = []
        self._turn_groups = []
        self._debug_section = None
        try:
            self._update_counter_label()
        except Exception:
            pass

        if self._cron_context is not None:
            ctx = self._cron_context
            self.mount(CronRunHeader(ctx.job, ctx.run))
            entries: list[dict] = []
            if ctx.debug_log_path is not None:
                entries = load_debug_log(ctx.debug_log_path, ctx.job.id, ctx.run.ts)
            dbg = DebugLogSection(entries)
            self._debug_section = dbg
            self.mount(dbg)
            if self._session is None:
                self.mount(Label("(no session file)", classes="empty-label"))
                self.scroll_home(animate=False)
                return
            self.mount(Label("── Session content ──────────────────────────", classes="empty-label"))

        if self._session is None:
            self.mount(Label("No session loaded.", classes="empty-label"))
            return

        if self._session.error:
            self.mount(Label(f"Permission denied: {self._session.error}", classes="empty-label"))
            return

        prologue, turns = _group_turns(self._session.events)

        for event in prologue:
            self._mount_event(event)

        for i, turn_events in enumerate(turns):
            has_error, corrected, tool_count, total_cost = _turn_meta(turn_events)
            sep = TurnSeparator(
                i + 1,
                turn_events[0].timestamp,
                tool_count,
                total_cost,
                has_error,
                corrected,
            )
            self._turn_separators.append(sep)
            self.mount(sep)

            turn_widgets: list = []
            for event in turn_events:
                turn_widgets.extend(self._mount_event(event))
            self._turn_groups.append((sep, turn_widgets))

        # Collapse all turns on load/reload
        self._turns_expanded = False
        for sep, widgets in self._turn_groups:
            for w in widgets:
                w.display = False

        self.scroll_home(animate=False)

    def reload(self, path: Path | None) -> None:
        self.load_session(path, cron_context=self._cron_context)

    def action_toggle_debug_log(self) -> None:
        if self._debug_section is not None:
            self._debug_section.toggle()

    def append_new_lines(self, path: Path) -> None:
        """Parse only lines added since last load and mount new widgets."""
        try:
            size = path.stat().st_size
        except OSError:
            return
        if size <= self._file_byte_offset:
            return

        new_events = []
        try:
            with open(path, encoding="utf-8") as f:
                f.seek(self._file_byte_offset)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    from eavesdrop.parser import _parse_content, _parse_usage
                    t = obj.get("type")
                    if t == "message":
                        msg = obj.get("message", {})
                        role = msg.get("role", "")
                        if role in ("user", "assistant"):
                            content = _parse_content(msg.get("content", []))
                            usage = _parse_usage(msg.get("usage")) if role == "assistant" else None
                            new_events.append(Message(
                                id=obj.get("id", ""),
                                parent_id=obj.get("parentId"),
                                timestamp=obj.get("timestamp", ""),
                                role=role,
                                content=content,
                                model=msg.get("model", ""),
                                provider=msg.get("provider", ""),
                                usage=usage,
                                stop_reason=msg.get("stopReason", ""),
                            ))
                        elif role == "toolResult":
                            content = _parse_content(msg.get("content", []))
                            new_events.append(Message(
                                id=obj.get("id", ""),
                                parent_id=obj.get("parentId"),
                                timestamp=obj.get("timestamp", ""),
                                role="toolResult",
                                content=content,
                                tool_call_id=msg.get("toolCallId", ""),
                                tool_name=msg.get("toolName", ""),
                                is_error=msg.get("isError", False),
                                details=msg.get("details", {}),
                            ))
            self._file_byte_offset = size
        except OSError:
            return

        if not new_events:
            return

        near_bottom = self._is_near_bottom()
        for event in new_events:
            if isinstance(event, Message) and event.role == "user":
                # Start a new turn so turn-level collapse/expand keeps working.
                sep = TurnSeparator(
                    len(self._turn_separators) + 1,
                    event.timestamp,
                    0,
                    0.0,
                    False,
                    False,
                )
                sep.expanded = self._turns_expanded
                self._turn_separators.append(sep)
                self.mount(sep)

                turn_widgets = self._mount_event(event)
                for w in turn_widgets:
                    w.display = sep.expanded
                self._turn_groups.append((sep, turn_widgets))
            elif self._turn_groups:
                # Append to the current turn, preserving its collapsed state.
                sep, widgets = self._turn_groups[-1]
                mounted = self._mount_event(event)
                for w in mounted:
                    w.display = sep.expanded
                widgets.extend(mounted)
            else:
                # Prologue events (before first user turn) remain always visible.
                self._mount_event(event)
        if near_bottom:
            self.scroll_end(animate=False)

    def _is_near_bottom(self) -> bool:
        """Return True if scroll position is within ~3 lines of bottom."""
        if self.max_scroll_y <= 0:
            return True
        return (self.max_scroll_y - self.scroll_y) <= 3

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

    def toggle_turns(self) -> bool:
        self._turns_expanded = not self._turns_expanded
        for sep, widgets in self._turn_groups:
            sep.expanded = self._turns_expanded
            for w in widgets:
                w.display = self._turns_expanded
        return self._turns_expanded

    def _collect_searchable_blocks(self) -> list:
        return [
            w for w in self.query("*")
            if isinstance(w, (ToolCallBlock, ToolResultBlock, FinalBlock, UserTurn, AssistantTurn))
            and _block_text(w).strip()
        ]

    def _turn_separator_for(self, block) -> TurnSeparator | None:
        """Return the TurnSeparator whose turn group contains block, or None."""
        # Walk block's ancestor chain to find a direct turn-group member
        node = block
        while node is not None and node is not self:
            for sep, widgets in self._turn_groups:
                if any(w is node for w in widgets):
                    return sep
            node = node.parent
        return None

    def _update_counter_label(self) -> None:
        label = self.query_one("#search-counter", Label)
        if self._search_matches:
            label.update(f" {self._search_index + 1}/{len(self._search_matches)} ")
        else:
            label.update(" 0/0 " if self._search_active else "")

    def _jump_to(self, index: int) -> None:
        block = self._search_matches[index]
        # Expand the containing turn if collapsed
        sep = self._turn_separator_for(block)
        if sep is not None and not sep.expanded:
            sep.expanded = True
            self.on_turn_separator_toggle(TurnSeparator.Toggle(sep))
        # Expand the block if it's a collapsible widget
        if hasattr(block, "expanded"):
            block.expanded = True
        if block.can_focus:
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

    def on_turn_separator_toggle(self, message: TurnSeparator.Toggle) -> None:
        sep = message.separator
        for s, widgets in self._turn_groups:
            if s is sep:
                for w in widgets:
                    w.display = sep.expanded
                break

    def action_next_turn(self) -> None:
        y = self.scroll_y
        for sep in self._turn_separators:
            if sep.region.y > y + 2:
                self.scroll_to_widget(sep, animate=False)
                return

    def action_prev_turn(self) -> None:
        y = self.scroll_y
        for sep in reversed(self._turn_separators):
            if sep.region.y < y - 2:
                self.scroll_to_widget(sep, animate=False)
                return
