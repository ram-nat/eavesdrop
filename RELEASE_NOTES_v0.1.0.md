# eavesdrop v0.1.0

Initial public release of `eavesdrop`, a Textual TUI for browsing and debugging openclaw session JSONL files.

## Highlights

- Two-pane workflow:
  - Session browser with model/message/tool metadata
  - Turn-by-turn conversation timeline
- Turn separators with error/corrected indicators
- Collapsible tool calls, tool results, and final responses
- Search across conversation content with match navigation (`/`, `n`, `N`)
- Follow mode for live session files (`f`)
- Local-time session timestamps
- Reload now refreshes both session browser and conversation (`r`)
- Clipboard command copy from tool call blocks (`y`)

## Publish Readiness Improvements

- Hardened startup when sessions directory is missing (no crash)
- Improved follow append behavior to preserve turn structure
- Expanded packaging metadata in `pyproject.toml`
- Updated README with package-first install instructions (`pip`, `pipx`, wheel install)
- Added publishing/deployment instructions and improved onboarding docs

## Testing

- Full test suite passing: `239 passed`

## Artifacts

Built artifacts for this release:

- `dist/eavesdrop-0.1.0-py3-none-any.whl`
- `dist/eavesdrop-0.1.0.tar.gz`
