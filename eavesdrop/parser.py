"""JSONL parser for openclaw session files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SessionMeta:
    id: str
    timestamp: str
    cwd: str


@dataclass
class ModelChange:
    id: str
    timestamp: str
    provider: str
    model_id: str


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    total: int = 0
    cost_total: float = 0.0


@dataclass
class ContentBlock:
    type: str  # "text", "thinking", "toolCall", "toolResult"
    text: str = ""
    thinking: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    arguments: Any = None


@dataclass
class Message:
    id: str
    parent_id: str | None
    timestamp: str
    role: str  # "user", "assistant", "toolResult"
    content: list[ContentBlock] = field(default_factory=list)
    # assistant-only
    model: str = ""
    provider: str = ""
    usage: Usage | None = None
    stop_reason: str = ""
    # toolResult-only
    tool_call_id: str = ""
    tool_name: str = ""
    is_error: bool = False
    details: dict = field(default_factory=dict)


@dataclass
class ParsedSession:
    meta: SessionMeta | None
    events: list[ModelChange | Message]
    error: str = ""


def _parse_content(content_list: list[dict]) -> list[ContentBlock]:
    blocks = []
    for c in content_list:
        t = c.get("type", "")
        if t == "text":
            blocks.append(ContentBlock(type="text", text=c.get("text", "")))
        elif t == "thinking":
            blocks.append(ContentBlock(type="thinking", thinking=c.get("thinking", "")))
        elif t == "toolCall":
            blocks.append(ContentBlock(
                type="toolCall",
                tool_call_id=c.get("id", ""),
                tool_name=c.get("name", ""),
                arguments=c.get("arguments"),
            ))
        else:
            # unknown block type — keep as text if it has text
            if "text" in c:
                blocks.append(ContentBlock(type="text", text=c["text"]))
    return blocks


def _parse_usage(usage_dict: dict | None) -> Usage | None:
    if not usage_dict:
        return None
    cost = usage_dict.get("cost", {}) or {}
    return Usage(
        input=usage_dict.get("input", 0),
        output=usage_dict.get("output", 0),
        cache_read=usage_dict.get("cacheRead", 0),
        cache_write=usage_dict.get("cacheWrite", 0),
        total=usage_dict.get("totalTokens", 0),
        cost_total=cost.get("total", 0.0),
    )


def parse_file(path: Path) -> ParsedSession:
    meta: SessionMeta | None = None
    events: list[ModelChange | Message] = []

    try:
        f_handle = open(path, encoding="utf-8")
    except (PermissionError, OSError) as e:
        return ParsedSession(meta=None, events=[], error=str(e))

    with f_handle as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            t = obj.get("type")

            if t == "session":
                meta = SessionMeta(
                    id=obj.get("id", ""),
                    timestamp=obj.get("timestamp", ""),
                    cwd=obj.get("cwd", ""),
                )

            elif t == "model_change":
                events.append(ModelChange(
                    id=obj.get("id", ""),
                    timestamp=obj.get("timestamp", ""),
                    provider=obj.get("provider", ""),
                    model_id=obj.get("modelId", ""),
                ))

            elif t == "message":
                msg = obj.get("message", {})
                role = msg.get("role", "")

                if role in ("user", "assistant"):
                    content = _parse_content(msg.get("content", []))
                    usage = _parse_usage(msg.get("usage")) if role == "assistant" else None
                    events.append(Message(
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
                    events.append(Message(
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

    return ParsedSession(meta=meta, events=events)


def tool_result_has_error(msg: Message) -> bool:
    """Return True if a toolResult message represents a real error.

    Checks both the protocol-level is_error flag and structural signals in
    details that openclaw sets even when is_error remains False:
      - details.exitCode != 0  (exec/process: non-zero shell exit)
      - details.status in ("failed", "error")  (process timeout; read ENOENT)
      - details.error key present  (read tool ENOENT)
    """
    if msg.is_error:
        return True
    d = msg.details
    if "exitCode" in d and d["exitCode"] != 0:
        return True
    if d.get("status") in ("failed", "error"):
        return True
    if "error" in d:
        return True
    return False


def session_uuid(path: Path) -> str:
    """Extract the UUID portion from any session filename.

    Handles plain (uuid.jsonl) and closed (uuid.jsonl.reset.TIMESTAMP) variants.
    """
    return path.name.split(".jsonl")[0]


def scan_sessions(sessions_dir: Path) -> list[Path]:
    """Return active session files sorted by mtime descending.

    Includes both plain (uuid.jsonl) and closed (uuid.jsonl.reset.TIMESTAMP) files.
    Excludes deleted sessions (uuid.jsonl.deleted.TIMESTAMP) and non-JSONL files.
    """
    files = []
    for p in sessions_dir.iterdir():
        name = p.name
        if ".jsonl" not in name:
            continue
        if ".deleted." in name:
            continue
        files.append(p)
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def session_summary(path: Path) -> dict:
    """Return lightweight metadata for the file browser without full parse."""
    meta_ts = ""
    last_event_ts = ""
    model = ""
    provider = ""
    user_count = 0
    assistant_count = 0
    tool_count = 0

    try:
        f_handle = open(path, encoding="utf-8")
    except (PermissionError, OSError) as e:
        return {
            "path": path,
            "timestamp": "",
            "last_event_ts": "",
            "model": "",
            "provider": "",
            "message_count": 0,
            "tool_count": 0,
            "error": str(e),
        }

    with f_handle as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = obj.get("type")
            ts = obj.get("timestamp", "")
            if ts:
                last_event_ts = ts
            if t == "session":
                meta_ts = ts
            elif t == "model_change" and not model:
                model = obj.get("modelId", "")
                provider = obj.get("provider", "")
            elif t == "message":
                role = obj.get("message", {}).get("role", "")
                if role == "user":
                    user_count += 1
                elif role == "assistant":
                    assistant_count += 1
                    for c in obj.get("message", {}).get("content", []):
                        if c.get("type") == "toolCall":
                            tool_count += 1

    return {
        "path": path,
        "timestamp": meta_ts,
        "last_event_ts": last_event_ts,
        "model": model,
        "provider": provider,
        "message_count": user_count + assistant_count,
        "tool_count": tool_count,
        "error": "",
    }
