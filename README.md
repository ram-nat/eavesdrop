# eavesdrop

A terminal UI for inspecting openclaw session JSONL files.

You get a fast two-pane workflow:
- Left: session browser (model, message/tool counts, status badges, cost)
- Right: turn-by-turn timeline (user, assistant, tool calls/results, final response)

`eavesdrop` is built for debugging agent behavior: what the model tried, where tools failed, and how it recovered.

Built with [Textual](https://github.com/Textualize/textual).

## Why?
- I've set up Openclaw where the cloud LLM (which is much more capable), provides prompts + directions to the local model hosted on my puny 12 GB VRAM 3060. 
- Even though the cloud LLM is capable, sometimes it struggles a bit to find the right tools or the right way to use the tool.
- When I write skills, I may not be clear enough or there can be mistakes that cause the LLM to struggle.
- Finally, the tools themselves may have bugs, the environment setup may have issues.

Having this turn based viewer helps me understand and debug such potential issues.

## Highlights

- Turn separators with error/corrected indicators
- Collapsible tool calls, tool results, and final responses
- In-session search with next/previous navigation
- Follow mode for live sessions (`f`)
- Local-time display in the session browser
- Copy tool command (`y`) from a focused tool call

## Requirements

- Python 3.12+
- Openclaw session files (JSONL)
- Optional on Wayland for reliable clipboard: `sudo apt install wl-clipboard`

## Install

### Install as a package (recommended for normal use)

```bash
# After publishing to PyPI:
pip install eavesdrop
```

or isolated tool install:

```bash
pipx install eavesdrop
```

### Install from a built wheel (no editable mode)

```bash
git clone https://github.com/ram-nat/eavesdrop
cd eavesdrop
uv build
pip install dist/eavesdrop-*.whl
```

### Dev install (editable)

```bash
git clone https://github.com/ram-nat/eavesdrop
cd eavesdrop
uv venv
uv pip install -e .
```

## Quick Start

```bash
# Browse the default sessions directory
eavesdrop

# Browse a custom directory
eavesdrop --dir /path/to/sessions

# Open one session directly
eavesdrop --session /path/to/session.jsonl

# Try with bundled demo data
eavesdrop --dir demo/sessions
```

Default sessions directory:

`~/.openclaw/agents/main-cloud/sessions`

## Configuration

- `EAVESDROP_SESSIONS_DIR`: default sessions path if `--dir` is not passed
- `.env` at repo root is loaded by the CLI entrypoint (simple `KEY=VALUE` lines only)

Example:

```bash
EAVESDROP_SESSIONS_DIR=/home/you/.openclaw/agents/main-cloud/sessions
```

## Keybindings

| Key | Action |
|---|---|
| `j` / `k`, arrows | Navigate session list |
| `Enter` | Load session / toggle focused block |
| `Space` | Toggle focused collapsible block |
| `Tab` | Move focus between collapsible blocks |
| `t` | Toggle thinking blocks |
| `T` | Collapse / expand all turns |
| `e` | Toggle all tool blocks expanded/collapsed |
| `$` | Toggle token/cost footers |
| `r` | Reload session + refresh browser |
| `f` | Toggle follow mode for active sessions |
| `/` | Open search bar |
| `n` / `N` | Next / previous search match |
| `Escape` | Close search bar |
| `]` / `[` | Scroll to next / previous turn |
| `y` | Copy tool call command to clipboard |
| `q` | Quit |

## Session File Support

Supported patterns:
- Active: `*.jsonl`
- Closed: `*.jsonl.reset.<timestamp>`
- Ignored: `*.jsonl.deleted.<timestamp>`

Each JSONL line is a typed event (`session`, `model_change`, `message`).

## Publishing / Deployment

For maintainers publishing package artifacts:

```bash
# Build sdist + wheel
uv build

# Optional sanity check
python3 -m zipfile -l dist/*.whl
```

If publishing to PyPI:

```bash
# one-time
python3 -m pip install --upgrade twine

# verify metadata and long description
python3 -m twine check dist/*

# publish
python3 -m twine upload dist/*
```

If publishing only to GitHub Releases, upload files from `dist/`.

## License

MIT. See [LICENSE](LICENSE).
