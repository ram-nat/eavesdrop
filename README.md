# eavesdrop

Terminal UI for browsing openclaw session files. Two-panel layout: session list on the left, conversation thread on the right.

This allows debugging and understanding of what the agent does in response to anything you ask. The session is organized in the form of turns where each turn is a user's request, 0 or more tool calls and other intermediate steps by the LLM and the final response.

## Why? 
- I have setup Openclaw where the cloud LLM (which is much more capable), provides prompts + directions to the local model hosted on my puny 12 GB VRAM 3060. 
- Even though the cloud LLM is capable, sometimes it struggles a bit to find the right tools or the right way to use the tool.
- When I write skills, I may not be clear enough or there can be mistakes that cause the LLM to struggle.
- Finally, the tools themselves may have bugs, the environment setup may have issues.

Having this turn based viewer helps me understand and debug such potential issues.

Built with [Textual](https://github.com/Textualize/textual).

<!-- screenshot -->

## Requirements

- Python 3.12+
- Sessions produced by openclaw (JSONL files)
- `wl-clipboard` (optional, for clipboard on Wayland): `sudo apt install wl-clipboard`

## Install

```bash
git clone https://github.com/ram-nat/eavesdrop
cd eavesdrop
uv venv
uv pip install -e .
```

## Usage

```bash
# Browse the default sessions directory
eavesdrop

# Browse a custom directory
eavesdrop --dir /path/to/sessions

# Open a specific session file directly
eavesdrop --session /path/to/session.jsonl
```

The default sessions directory is `~/.openclaw/agents/main-cloud/sessions`.

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
| `r` | Reload current file |
| `q` | Quit |
| `/` | Open search bar |
| `n` / `N` | Next / previous search match |
| `Escape` | Close search bar |
| `]` / `[` | Scroll to next / previous turn |
| `y` | Copy tool call command to clipboard |

## Session format

Eavesdrop reads JSONL files where each line is a typed event (`session`, `model_change`, `message`). This format is specific to openclaw. Active sessions use a `.jsonl` extension; closed sessions are `.jsonl.reset.<timestamp>`; deleted sessions (`.jsonl.deleted.<timestamp>`) are excluded from the browser.

## License

MIT License

Copyright (c) 2026 ramnat

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
