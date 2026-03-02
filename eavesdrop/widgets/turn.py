"""Widgets for individual conversation turns."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static, Label
from textual.reactive import reactive
from textual.containers import Vertical

from eavesdrop.parser import Message, ModelChange, Usage

if TYPE_CHECKING:
    pass


def _cost_str(usage: Usage) -> str:
    parts = [f"{usage.total:,} tok"]
    if usage.cost_total:
        parts.append(f"${usage.cost_total:.4f}")
    return "  ".join(parts)


def _truncate(text: str, max_chars: int = 120) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) > max_chars:
        return text[:max_chars] + "…"
    return text


def _args_preview(arguments) -> str:
    if arguments is None:
        return ""
    if isinstance(arguments, str):
        return _truncate(arguments)
    if isinstance(arguments, dict):
        # Show first meaningful value
        for v in arguments.values():
            if isinstance(v, str) and v.strip():
                return _truncate(v)
        return _truncate(json.dumps(arguments))
    return _truncate(str(arguments))


def _args_full(arguments) -> str:
    if arguments is None:
        return "(no arguments)"
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
            return json.dumps(parsed, indent=2)
        except Exception:
            return arguments
    return json.dumps(arguments, indent=2)


class ModelChangeTurn(Widget):
    DEFAULT_CSS = """
    ModelChangeTurn {
        height: auto;
        padding: 0 1;
        color: $text-disabled;
    }
    """

    def __init__(self, event: ModelChange, **kwargs):
        super().__init__(**kwargs)
        self._event = event

    def render(self) -> Text:
        e = self._event
        label = f"── {e.model_id} ({e.provider}) ──"
        t = Text(label, style="dim")
        return t


class ToolCallBlock(Widget):
    """A collapsible tool call block."""

    can_focus = True
    expanded: reactive[bool] = reactive(False)

    BINDINGS = [Binding("enter", "toggle", "Toggle", show=False)]

    DEFAULT_CSS = """
    ToolCallBlock {
        height: auto;
        padding: 0 0 0 2;
    }
    ToolCallBlock:focus {
        background: $boost;
    }
    ToolCallBlock .tool-label {
        color: $warning;
        text-style: bold;
    }
    ToolCallBlock .tool-preview {
        color: $text-muted;
    }
    ToolCallBlock .tool-body {
        color: $text;
        padding: 0 0 0 2;
    }
    """

    def __init__(self, tool_name: str, arguments, **kwargs):
        super().__init__(**kwargs)
        self._tool_name = tool_name
        self._arguments = arguments

    def compose(self) -> ComposeResult:
        yield Label(f"[TOOL CALL: {self._tool_name}]", classes="tool-label")
        yield Static(_args_preview(self._arguments), classes="tool-preview", id="preview")
        body = Static(
            Syntax(_args_full(self._arguments), "json", theme="monokai", word_wrap=True),
            classes="tool-body",
            id="body",
        )
        body.display = False
        yield body

    def watch_expanded(self, value: bool) -> None:
        try:
            preview = self.query_one("#preview")
            body = self.query_one("#body")
            preview.display = not value
            body.display = value
        except Exception:
            pass

    def action_toggle(self) -> None:
        self.expanded = not self.expanded

    def toggle(self) -> None:
        self.expanded = not self.expanded


class ToolResultBlock(Widget):
    """A collapsible tool result block."""

    can_focus = True
    expanded: reactive[bool] = reactive(False)

    BINDINGS = [Binding("enter", "toggle", "Toggle", show=False)]

    DEFAULT_CSS = """
    ToolResultBlock {
        height: auto;
        padding: 0 0 0 2;
    }
    ToolResultBlock:focus {
        background: $boost;
    }
    ToolResultBlock .result-label {
        color: $success;
        text-style: bold;
    }
    ToolResultBlock .result-preview {
        color: $text-muted;
    }
    ToolResultBlock .result-body {
        color: $text;
        padding: 0 0 0 2;
    }
    ToolResultBlock .result-error {
        color: $error;
        text-style: bold;
    }
    """

    def __init__(self, message: Message, **kwargs):
        super().__init__(**kwargs)
        self._message = message

    def _get_text(self) -> str:
        msg = self._message
        # Prefer details.aggregated if present
        agg = msg.details.get("aggregated")
        if agg is not None:
            return str(agg)
        # Fall back to content text
        parts = [c.text for c in msg.content if c.type == "text" and c.text]
        return "\n".join(parts)

    def compose(self) -> ComposeResult:
        msg = self._message
        error_suffix = " [ERROR]" if msg.is_error else ""
        label_class = "result-error" if msg.is_error else "result-label"
        yield Label(f"[TOOL RESULT: {msg.tool_name}]{error_suffix}", classes=label_class)
        full_text = self._get_text()
        yield Static(_truncate(full_text), classes="result-preview", id="preview")
        body = Static(full_text, classes="result-body", id="body")
        body.display = False
        yield body

    def watch_expanded(self, value: bool) -> None:
        try:
            preview = self.query_one("#preview")
            body = self.query_one("#body")
            preview.display = not value
            body.display = value
        except Exception:
            pass

    def action_toggle(self) -> None:
        self.expanded = not self.expanded

    def toggle(self) -> None:
        self.expanded = not self.expanded


class ThinkingBlock(Widget):
    """A thinking block, hidden by default."""

    visible: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    ThinkingBlock {
        height: auto;
        padding: 0 0 0 2;
    }
    ThinkingBlock .thinking-label {
        color: $accent;
        text-style: bold;
    }
    ThinkingBlock .thinking-body {
        color: $text-muted;
        padding: 0 0 0 2;
    }
    """

    def __init__(self, text: str, **kwargs):
        super().__init__(**kwargs)
        self._text = text
        self.display = False

    def compose(self) -> ComposeResult:
        yield Label("[THINKING]", classes="thinking-label")
        yield Static(self._text, classes="thinking-body")

    def watch_visible(self, value: bool) -> None:
        self.display = value


class UsageFooter(Widget):
    """Token/cost footer for assistant turns."""

    visible: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    UsageFooter {
        height: auto;
        padding: 0 0 0 2;
        color: $text-disabled;
    }
    """

    def __init__(self, usage: Usage, **kwargs):
        super().__init__(**kwargs)
        self._usage = usage
        self.display = False

    def render(self) -> Text:
        return Text(_cost_str(self._usage), style="dim")

    def watch_visible(self, value: bool) -> None:
        self.display = value


class UserTurn(Widget):
    DEFAULT_CSS = """
    UserTurn {
        height: auto;
        padding: 1 1 0 1;
        border-left: thick $primary;
    }
    UserTurn .user-label {
        color: $primary;
        text-style: bold;
    }
    UserTurn .user-body {
        color: $text;
        padding: 0 0 0 2;
    }
    """

    def __init__(self, message: Message, **kwargs):
        super().__init__(**kwargs)
        self._message = message

    def compose(self) -> ComposeResult:
        yield Label("[USER]", classes="user-label")
        text_parts = [c.text for c in self._message.content if c.type == "text" and c.text]
        body = "\n".join(text_parts)
        yield Static(body, classes="user-body")


class AssistantTurn(Widget):
    DEFAULT_CSS = """
    AssistantTurn {
        height: auto;
        padding: 1 1 0 1;
        border-left: thick $panel-lighten-2;
    }
    AssistantTurn .assistant-label {
        color: $text;
        text-style: bold;
    }
    AssistantTurn .assistant-body {
        color: $text;
        padding: 0 0 0 2;
    }
    """

    def __init__(self, message: Message, **kwargs):
        super().__init__(**kwargs)
        self._message = message
        self._tool_calls: list[ToolCallBlock] = []
        self._thinking_blocks: list[ThinkingBlock] = []
        self._usage_footer: UsageFooter | None = None

    def compose(self) -> ComposeResult:
        yield Label("[ASSISTANT]", classes="assistant-label")

        for block in self._message.content:
            if block.type == "thinking" and block.thinking:
                tb = ThinkingBlock(block.thinking)
                self._thinking_blocks.append(tb)
                yield tb
            elif block.type == "toolCall":
                tc = ToolCallBlock(block.tool_name, block.arguments)
                self._tool_calls.append(tc)
                yield tc
            elif block.type == "text" and block.text.strip():
                yield Static(block.text, classes="assistant-body", markup=False)

        if self._message.usage:
            footer = UsageFooter(self._message.usage)
            self._usage_footer = footer
            yield footer

    def set_thinking_visible(self, visible: bool) -> None:
        for tb in self._thinking_blocks:
            tb.visible = visible

    def set_tools_expanded(self, expanded: bool) -> None:
        for tc in self._tool_calls:
            tc.expanded = expanded

    def set_usage_visible(self, visible: bool) -> None:
        if self._usage_footer:
            self._usage_footer.visible = visible

    @property
    def tool_calls(self) -> list[ToolCallBlock]:
        return self._tool_calls
