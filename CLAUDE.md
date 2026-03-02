# eavesdrop — Maintainer Guide

TUI for browsing openclaw session JSONL files. Built with Textual (Python).

---

## Purpose

Openclaw stores every agent session as a JSONL file under `/home/openclaw/.openclaw/agents/main-cloud/sessions/`. Each line is a typed event. This tool provides a two-panel browser: session list on the left, conversation thread on the right.

---

## JSONL Format

Each line is a JSON object. Key types:

| `type` | Notes |
|---|---|
| `session` | First line. Has `id`, `timestamp`, `cwd`. |
| `model_change` | Has `modelId`, `provider`. |
| `message` | Main content. `message.role` is `user`, `assistant`, or `toolResult`. |
| `thinking_level_change`, `custom` | Ignored by the parser. |

**`message.role` values:**
- `user` — human turn; content is `[{type: "text"}]`
- `assistant` — model turn; content can include `{type: "thinking"}`, `{type: "toolCall"}`, `{type: "text"}`; has `model`, `provider`, `usage`, `stopReason`
- `toolResult` — tool output; top-level role (not nested in a user message); has `toolCallId`, `toolName`, `isError`, `details`

**`details.aggregated`** on toolResult: openclaw-specific field containing a compact summary of large tool output (e.g. exec results). Prefer this over `content[].text` when present.

**File naming:** active sessions are plain `<uuid>.jsonl`. Inactive files contain `.deleted.` or `.reset.` in the name and are excluded by `scan_sessions()`.

---

## Architecture

```
eavesdrop/
  parser.py          — JSONL reader; returns ParsedSession(meta, events[])
  app.py             — Textual App; two-panel layout, keybindings, CLI wiring
  __main__.py        — argparse entry point (--session, --dir)
  widgets/
    file_browser.py  — ListView of sessions with per-item metadata
    conversation.py  — VerticalScroll; mounts turn widgets from parsed events
    turn.py          — Per-turn widgets: UserTurn, AssistantTurn, ToolCallBlock,
                       ToolResultBlock, ThinkingBlock, UsageFooter, ModelChangeTurn
```

**Data flow:** `scan_sessions()` → `session_summary()` (lightweight, for browser) or `parse_file()` (full parse, for conversation view) → widget tree.

**State managed in `ConversationView`:** `_show_thinking`, `_show_usage`, `_tools_expanded` — toggled by keybinding actions in `app.py`, propagated to child widgets on rebuild or toggle call.

---

## Keybindings

| Key | Action |
|---|---|
| `j`/`k`, arrows | Navigate file browser |
| `Enter` | Load selected session (when browser focused); toggle focused tool block (when `ToolCallBlock` or `ToolResultBlock` focused) |
| `Tab` | Move focus between focusable tool blocks in the conversation |
| `t` | Toggle thinking blocks |
| `e` | Toggle all tool calls/results expanded/collapsed |
| `$` | Toggle token/cost footers |
| `r` | Reload current file |
| `q` | Quit |

---

## Dependencies

- `textual` — TUI framework (includes `rich`)
- `pytest`, `pytest-asyncio` — test suite
- No other third-party dependencies

---

## Testing

```bash
venv/bin/pytest tests/ -v
```

- `tests/test_parser.py` — 42 tests; uses `tmp_path` to write fixture JSONL files; no live sessions directory touched
- `tests/test_app.py` — 15 tests; uses `app.run_test()` (Textual's async test pilot) and `monkeypatch` for argparse

---

## Known Constraints / Future Work

- Tool call expand/collapse: `e` toggles all globally; `Enter` on a focused `ToolCallBlock`, `ToolResultBlock`, or `FinalBlock` toggles that item individually. All three block types are focusable (`can_focus = True`) — tab to navigate between them.
- Assistant text wrapped in `<final>...</final>` (openclaw's response tag) is detected by `_is_final()`, stripped by `_unwrap_final()`, and rendered as a collapsible `FinalBlock` (collapsed by default, label `[RESPONSE]`). Plain text blocks without the tag render as normal `Static` widgets.
- Conversation does not render assistant text as markdown (uses plain `Static`); upgrading to `Markdown` widget is straightforward but adds render overhead for large sessions
- `session_summary()` does a second full file scan separately from `parse_file()`; for very large session dirs this could be unified
- Default sessions dir is hardcoded to `/home/openclaw/.openclaw/agents/main-cloud/sessions/`; override with `--dir`
