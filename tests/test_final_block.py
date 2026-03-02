"""Tests for FinalBlock and <final> tag detection/stripping."""

import json
from pathlib import Path

import pytest

from eavesdrop.widgets.turn import FinalBlock, _is_final, _unwrap_final


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, lines: list[dict]) -> None:
    with open(path, "w") as f:
        for obj in lines:
            f.write(json.dumps(obj) + "\n")


def _session_with_final(path: Path, final_text: str = "Hello, Ram!") -> None:
    _write_jsonl(path, [
        {"type": "session", "id": "s1", "timestamp": "2026-03-01T12:00:00.000Z", "cwd": "/tmp"},
        {"type": "model_change", "id": "mc1", "parentId": None,
         "timestamp": "2026-03-01T12:00:01.000Z", "provider": "test", "modelId": "test-model"},
        {
            "type": "message", "id": "u1", "parentId": None,
            "timestamp": "2026-03-01T12:00:02.000Z",
            "message": {"role": "user", "content": [{"type": "text", "text": "hi"}], "timestamp": 1},
        },
        {
            "type": "message", "id": "a1", "parentId": "u1",
            "timestamp": "2026-03-01T12:00:03.000Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": f"<final>{final_text}</final>"}],
                "model": "test-model", "provider": "test",
                "usage": {"input": 10, "output": 5, "cacheRead": 0, "cacheWrite": 0,
                          "totalTokens": 15, "cost": {"input": 0, "output": 0,
                          "cacheRead": 0, "cacheWrite": 0, "total": 0}},
                "stopReason": "end_turn", "timestamp": 1,
            },
        },
    ])


def _session_with_plain_text(path: Path, text: str = "Plain response.") -> None:
    _write_jsonl(path, [
        {"type": "session", "id": "s1", "timestamp": "2026-03-01T12:00:00.000Z", "cwd": "/tmp"},
        {
            "type": "message", "id": "a1", "parentId": None,
            "timestamp": "2026-03-01T12:00:03.000Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
                "model": "test-model", "provider": "test",
                "usage": {"input": 10, "output": 5, "cacheRead": 0, "cacheWrite": 0,
                          "totalTokens": 15, "cost": {"input": 0, "output": 0,
                          "cacheRead": 0, "cacheWrite": 0, "total": 0}},
                "stopReason": "end_turn", "timestamp": 1,
            },
        },
    ])


# ---------------------------------------------------------------------------
# _is_final
# ---------------------------------------------------------------------------

class TestIsFinal:
    def test_detects_final_tags(self):
        assert _is_final("<final>Hello</final>") is True

    def test_detects_with_leading_whitespace(self):
        assert _is_final("  <final>Hello</final>  ") is True

    def test_rejects_plain_text(self):
        assert _is_final("Hello") is False

    def test_rejects_only_opening_tag(self):
        assert _is_final("<final>Hello") is False

    def test_rejects_only_closing_tag(self):
        assert _is_final("Hello</final>") is False

    def test_rejects_empty_string(self):
        assert _is_final("") is False

    def test_rejects_other_xml_tags(self):
        assert _is_final("<thinking>text</thinking>") is False

    def test_accepts_multiline_content(self):
        assert _is_final("<final>line one\nline two</final>") is True

    def test_rejects_final_not_at_start(self):
        assert _is_final("prefix <final>text</final>") is False


# ---------------------------------------------------------------------------
# _unwrap_final
# ---------------------------------------------------------------------------

class TestUnwrapFinal:
    def test_strips_tags(self):
        assert _unwrap_final("<final>Hello, Ram!</final>") == "Hello, Ram!"

    def test_strips_surrounding_whitespace(self):
        assert _unwrap_final("  <final>  text  </final>  ") == "text"

    def test_preserves_internal_newlines(self):
        result = _unwrap_final("<final>line one\nline two</final>")
        assert "line one\nline two" in result

    def test_preserves_inner_html_like_content(self):
        result = _unwrap_final("<final>Use <b>bold</b> here</final>")
        assert "<b>bold</b>" in result


# ---------------------------------------------------------------------------
# FinalBlock widget unit tests
# ---------------------------------------------------------------------------

class TestFinalBlock:
    def test_can_focus_is_true(self):
        assert FinalBlock("text").can_focus is True

    def test_starts_collapsed(self):
        assert FinalBlock("text").expanded is False

    def test_toggle_expands(self):
        b = FinalBlock("text")
        b.toggle()
        assert b.expanded is True

    def test_toggle_collapses(self):
        b = FinalBlock("text")
        b.toggle()
        b.toggle()
        assert b.expanded is False

    def test_action_toggle_expands(self):
        b = FinalBlock("text")
        b.action_toggle()
        assert b.expanded is True

    def test_has_enter_binding(self):
        keys = {binding.key for binding in FinalBlock.BINDINGS}
        assert "enter" in keys


# ---------------------------------------------------------------------------
# Integration: FinalBlock appears in app for <final>-wrapped text
# ---------------------------------------------------------------------------

class TestFinalBlockIntegration:
    @pytest.mark.asyncio
    async def test_final_text_renders_as_final_block(self, tmp_path):
        from eavesdrop.app import EavesdropApp
        p = tmp_path / "s.jsonl"
        _session_with_final(p, "Great news, Ram!")
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            blocks = app.query(FinalBlock)
            assert len(blocks) == 1

    @pytest.mark.asyncio
    async def test_final_block_starts_collapsed(self, tmp_path):
        from eavesdrop.app import EavesdropApp
        p = tmp_path / "s.jsonl"
        _session_with_final(p, "Response text")
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            block = app.query_one(FinalBlock)
            assert block.expanded is False

    @pytest.mark.asyncio
    async def test_final_block_toggles_with_enter(self, tmp_path):
        from eavesdrop.app import EavesdropApp
        p = tmp_path / "s.jsonl"
        _session_with_final(p, "Response text")
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            block = app.query_one(FinalBlock)
            block.focus()
            await pilot.press("enter")
            assert block.expanded is True
            await pilot.press("enter")
            assert block.expanded is False

    @pytest.mark.asyncio
    async def test_plain_text_does_not_render_as_final_block(self, tmp_path):
        from eavesdrop.app import EavesdropApp
        p = tmp_path / "s.jsonl"
        _session_with_plain_text(p, "Just a regular response.")
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            assert len(app.query(FinalBlock)) == 0

    @pytest.mark.asyncio
    async def test_final_block_content_is_unwrapped(self, tmp_path):
        from eavesdrop.app import EavesdropApp
        p = tmp_path / "s.jsonl"
        _session_with_final(p, "Unwrapped content here")
        app = EavesdropApp(sessions_dir=tmp_path, initial_session=p)
        async with app.run_test(size=(80, 24)) as pilot:
            block = app.query_one(FinalBlock)
            assert block._text == "Unwrapped content here"
