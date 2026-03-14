"""
File-based chat history storage for The God Factory University.

Saves every Professor AI conversation to labelled JSON files on disk so they
can be loaded back later (even by small models with limited context).

Directory layout:
    data/chats/
        <session_id>/
            meta.json          — {session_id, label, created_at, message_count, topics}
            messages.jsonl     — one JSON object per line {role, content, occurred_at}

Functions:
    save_message()    — append a single message to disk
    save_full_chat()  — write an entire conversation at once
    list_sessions()   — list all saved sessions with metadata
    load_session()    — load all messages from a session
    label_session()   — update the human-readable label for a session
    export_for_llm()  — export a compact summary for LLM context injection
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

CHAT_DIR = Path(__file__).resolve().parent.parent / "data" / "chats"


def _session_dir(session_id: str) -> Path:
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
    return CHAT_DIR / safe_id


def save_message(session_id: str, role: str, content: str, label: str = "") -> None:
    """Append a single message to the session's JSONL file."""
    d = _session_dir(session_id)
    d.mkdir(parents=True, exist_ok=True)

    msg = {"role": role, "content": content, "occurred_at": time.time()}
    with open(d / "messages.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    _update_meta(session_id, label)


def save_full_chat(session_id: str, messages: list[dict], label: str = "") -> None:
    """Write an entire conversation to disk (overwrites existing)."""
    d = _session_dir(session_id)
    d.mkdir(parents=True, exist_ok=True)

    with open(d / "messages.jsonl", "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    _update_meta(session_id, label, count=len(messages))


def _update_meta(session_id: str, label: str = "", count: int | None = None) -> None:
    d = _session_dir(session_id)
    meta_path = d / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    else:
        meta = {
            "session_id": session_id,
            "label": label or session_id,
            "created_at": time.time(),
            "message_count": 0,
            "topics": [],
        }
    if label:
        meta["label"] = label
    meta["updated_at"] = time.time()
    if count is not None:
        meta["message_count"] = count
    else:
        # count lines in JSONL
        msg_path = d / "messages.jsonl"
        if msg_path.exists():
            meta["message_count"] = sum(1 for _ in open(msg_path, encoding="utf-8"))
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def label_session(session_id: str, label: str) -> None:
    """Update the human-readable label for a session."""
    _update_meta(session_id, label=label)


def list_sessions() -> list[dict]:
    """Return metadata for all saved chat sessions, newest first."""
    if not CHAT_DIR.exists():
        return []
    sessions = []
    for d in CHAT_DIR.iterdir():
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                sessions.append(meta)
            except (json.JSONDecodeError, OSError):
                continue
    sessions.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
    return sessions


def load_session(session_id: str) -> list[dict]:
    """Load all messages from a session."""
    msg_path = _session_dir(session_id) / "messages.jsonl"
    if not msg_path.exists():
        return []
    messages = []
    with open(msg_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return messages


def export_for_llm(session_id: str, max_messages: int = 20) -> str:
    """Export a compact chat summary suitable for LLM context injection."""
    messages = load_session(session_id)
    meta = {}
    meta_path = _session_dir(session_id) / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    label = meta.get("label", session_id)
    recent = messages[-max_messages:] if len(messages) > max_messages else messages

    lines = [f"[Chat: {label} | {len(messages)} messages total]"]
    for msg in recent:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")[:500]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def export_all_for_llm(max_sessions: int = 5, max_messages: int = 10) -> str:
    """Export recent chat summaries across sessions for LLM context."""
    sessions = list_sessions()[:max_sessions]
    parts = []
    for s in sessions:
        sid = s.get("session_id", "")
        if sid:
            parts.append(export_for_llm(sid, max_messages))
    return "\n---\n".join(parts)
