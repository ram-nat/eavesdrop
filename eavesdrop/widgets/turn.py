"""Widgets for individual conversation turns."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from typing import TYPE_CHECKING

from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message as TextualMessage
from textual.widget import Widget
from textual.widgets import Static, Label
from textual.reactive import reactive
from textual.containers import Vertical

from eavesdrop.parser import Message, ModelChange, Usage, tool_result_has_error

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


def _is_final(text: str) -> bool:
    t = text.strip()
    return t.startswith("<final>") and t.endswith("</final>")


def _unwrap_final(text: str) -> str:
    t = text.strip()
    return t[len("<final>"):-len("</final>")].strip()


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

    BINDINGS = [
        Binding("enter", "toggle", "Toggle", show=True),
        Binding("space", "toggle", "Toggle", show=False),
        Binding("y", "copy", "Copy", show=True),
    ]

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
        color: $text;
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
        yield Static(_args_preview(self._arguments), classes="tool-preview", id="preview", markup=False)
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

    def action_copy(self) -> None:
        args = self._arguments
        if not isinstance(args, dict) or "command" not in args:
            return
        command = args["command"]
        if not isinstance(command, str):
            return
        if os.environ.get("WAYLAND_DISPLAY"):
            try:
                subprocess.run(["wl-copy"], input=command.encode(), check=True, timeout=2)
            except Exception:
                pass
        self.app.copy_to_clipboard(command)
        self.app.notify("Copied", timeout=1.5)


class ToolResultBlock(Widget):
    """A collapsible tool result block."""

    can_focus = True
    expanded: reactive[bool] = reactive(False)

    BINDINGS = [
        Binding("enter", "toggle", "Toggle", show=True),
        Binding("space", "toggle", "Toggle", show=False),
    ]

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
        color: $text;
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
        is_err = tool_result_has_error(msg)
        error_suffix = " [ERROR]" if is_err else ""
        label_class = "result-error" if is_err else "result-label"
        yield Label(f"[TOOL RESULT: {msg.tool_name}]{error_suffix}", classes=label_class)
        full_text = self._get_text()
        yield Static(_truncate(full_text), classes="result-preview", id="preview", markup=False)
        body = Static(full_text, classes="result-body", id="body", markup=False)
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
        yield Static(self._text, classes="thinking-body", markup=False)

    def watch_visible(self, value: bool) -> None:
        self.display = value


class FinalBlock(Widget):
    """A collapsible assistant final-response block (text wrapped in <final> tags)."""

    can_focus = True
    expanded: reactive[bool] = reactive(False)

    BINDINGS = [
        Binding("enter", "toggle", "Toggle", show=True),
        Binding("space", "toggle", "Toggle", show=False),
    ]

    DEFAULT_CSS = """
    FinalBlock {
        height: auto;
        padding: 0 0 0 2;
    }
    FinalBlock:focus {
        background: $boost;
    }
    FinalBlock .final-label {
        color: $text;
        text-style: bold;
    }
    FinalBlock .final-preview {
        color: $text;
    }
    FinalBlock .final-body {
        color: $text;
        padding: 0 0 0 2;
    }
    """

    def __init__(self, text: str, **kwargs):
        super().__init__(**kwargs)
        self._text = text

    def compose(self) -> ComposeResult:
        yield Label("[RESPONSE]", classes="final-label")
        yield Static(_truncate(self._text), classes="final-preview", id="preview", markup=False)
        body = Static(self._text, classes="final-body", id="body", markup=False)
        body.display = False
        yield body

    def watch_expanded(self, value: bool) -> None:
        try:
            self.query_one("#preview").display = not value
            self.query_one("#body").display = value
        except Exception:
            pass

    def action_toggle(self) -> None:
        self.expanded = not self.expanded

    def toggle(self) -> None:
        self.expanded = not self.expanded


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
        self._final_blocks: list[FinalBlock] = []
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
                if _is_final(block.text):
                    fb = FinalBlock(_unwrap_final(block.text))
                    self._final_blocks.append(fb)
                    yield fb
                else:
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


class TurnSeparator(Widget):
    """A focusable, collapsible turn separator shown before each user turn."""

    can_focus = True
    expanded: reactive[bool] = reactive(False)

    class Toggle(TextualMessage):
        def __init__(self, separator: "TurnSeparator") -> None:
            super().__init__()
            self.separator = separator

    BINDINGS = [
        Binding("enter", "toggle", "Toggle turn", show=True),
        Binding("space", "toggle", "Toggle turn", show=False),
    ]

    DEFAULT_CSS = """
    TurnSeparator {
        height: 1;
        padding: 0 1;
        color: $text-disabled;
    }
    TurnSeparator:focus { background: $boost; }
    TurnSeparator.turn-error { color: $warning; }
    TurnSeparator.turn-corrected { color: $success; }
    """

    def __init__(self, turn_num: int, timestamp: str, tool_count: int,
                 total_cost: float, has_error: bool, corrected: bool, **kwargs):
        if corrected:
            css = "turn-corrected"
        elif has_error:
            css = "turn-error"
        else:
            css = ""
        existing = kwargs.pop("classes", "")
        combined = f"{existing} {css}".strip() if existing else css
        super().__init__(classes=combined, **kwargs)
        self._turn_num = turn_num
        self._timestamp = timestamp
        self._tool_count = tool_count
        self._total_cost = total_cost
        self._has_error = has_error
        self._corrected = corrected

    def _time_str(self) -> str:
        ts = self._timestamp
        if not ts:
            return ""
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.astimezone().strftime("%H:%M")
        except Exception:
            try:
                return ts.split("T")[1][:5]
            except (IndexError, AttributeError):
                return ts

    def render(self) -> Text:
        num = self._turn_num
        time = self._time_str()
        calls = self._tool_count
        cost = self._total_cost

        cost_str = f"${cost:.4f}"
        meta = f"Turn {num}  ·  {time}  ·  {calls} calls  ·  {cost_str}"

        if self._corrected:
            indicator = "  [!→✓]"
        elif self._has_error:
            indicator = "  [!]"
        else:
            indicator = ""

        if self.expanded:
            label = f"── {meta}{indicator} "
            # Fill remaining space with dashes via Rich
            t = Text(label)
            t.append("─" * max(0, self.size.width - len(label)))
        else:
            t = Text(f"▸ {meta}{indicator}")

        return t

    def action_toggle(self) -> None:
        self.expanded = not self.expanded
        self.post_message(TurnSeparator.Toggle(self))
