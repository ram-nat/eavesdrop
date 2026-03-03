# eavesdrop — Maintainer Guide

TUI for browsing openclaw session JSONL files. Built with Textual (Python).

---

## Purpose

Openclaw stores every agent session as a JSONL file under `/home/openclaw/.openclaw/agents/main-cloud/sessions/`. Each line is a typed event. This tool provides a two-panel browser: session list on the left, conversation thread on the right.

---

## JSONL Format

Each line is a JSON object. Relevant types:

| `type` | Notes |
|---|---|
| `session` | First line. Has `id`, `timestamp`, `cwd`. |
| `model_change` | Has `modelId`, `provider`. |
| `message` | Main content. `message.role` is `user`, `assistant`, or `toolResult`. |

**`message.role` values:**
- `user` — human turn; `content[].type` is `text`
- `assistant` — model turn; content can include `thinking`, `toolCall`, `text`; has `model`, `provider`, `usage`, `stopReason`
- `toolResult` — tool output; a top-level role, not nested inside a user message; has `toolCallId`, `toolName`, `isError`, `details`

**Notable fields:**
- `details.aggregated` on toolResult: openclaw-specific compact summary of large output — prefer over `content[].text` when present
- Assistant text wrapped in `<final>...</final>` is openclaw's response tag; rendered as a collapsible block

**File naming:** `<uuid>.jsonl` (active) and `<uuid>.jsonl.reset.<timestamp>` (closed) are both shown. `<uuid>.jsonl.deleted.<timestamp>` is excluded. `session_uuid(path)` extracts the UUID from any variant.

---

## Architecture

```
eavesdrop/
  parser.py          — JSONL reader; returns ParsedSession(meta, events[], error)
  app.py             — Textual App; two-panel layout, keybindings, CLI wiring
  __main__.py        — argparse entry point (--session, --dir)
  widgets/
    file_browser.py  — ListView of sessions with per-item metadata
    conversation.py  — VerticalScroll; mounts turn widgets from parsed events
    turn.py          — Per-turn widgets for all content block types
```

**Data flow:** `scan_sessions()` → `session_summary()` (lightweight, for browser) or `parse_file()` (full parse, for conversation) → widget tree.

**Global toggle state** lives in `ConversationView` (`_show_thinking`, `_show_usage`, `_tools_expanded`) and is propagated to child widgets. Per-item toggle is handled by the widgets themselves via `Enter` when focused.

**Error handling:** `parse_file()` and `session_summary()` catch `PermissionError`/`OSError` and return an `error` field rather than raising. The browser shows inaccessible files as `[no access]`; the conversation panel shows the error message.

---

## Keybindings

| Key | Action |
|---|---|
| `j`/`k`, arrows | Navigate file browser |
| `Enter` | Load session (browser focused) or toggle item (tool/result/response block focused) |
| `Tab` | Move focus between collapsible blocks in the conversation |
| `t` | Toggle thinking blocks |
| `e` | Toggle all collapsible blocks expanded/collapsed |
| `$` | Toggle token/cost footers |
| `r` | Reload current file |
| `q` | Quit |

---

## Dependencies

- `textual` — TUI framework (includes `rich`)
- `pytest`, `pytest-asyncio` — test suite only
- No other third-party dependencies

---

## Testing

```bash
venv/bin/pytest tests/ -v
```

Tests use `tmp_path` fixture JSONL files and Textual's `app.run_test()` async pilot. No live sessions directory is touched.

---

## Known Constraints / Future Work

- Assistant text is rendered as plain `Static`, not markdown — easy to upgrade but adds overhead for large sessions
- `session_summary()` scans the file independently from `parse_file()`; could be unified for very large session dirs
- Default sessions dir is hardcoded; override with `--dir`
