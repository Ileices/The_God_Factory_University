"""
Compatibility shims (aliases) used by UI pages for The God Factory University.
Extracted from database.py for modularity (DEVELOPMENT.md Rule 5).

Every function here delegates to the canonical database.py function
so pages that import from core.database keep working unchanged.
"""
from __future__ import annotations

import json


def make_shims(*, set_setting, get_setting, get_achievements, get_xp, append_chat,
               get_chat, get_level, compute_gpa, tx, save_llm_generated_raw):
    """Return a dict of shim functions bound to the real implementations."""

    def save_setting(key: str, value: str) -> None:
        """Alias for set_setting."""
        set_setting(key, value)

    def get_all_achievements() -> list[dict]:
        """Alias for get_achievements."""
        return get_achievements()

    def get_total_xp() -> int:
        """Alias for get_xp."""
        return get_xp()

    def save_chat_history(session_id: str, role: str, content: str) -> None:
        """Alias for append_chat."""
        append_chat(session_id, role, content)

    def get_chat_history(session_id: str, limit: int = 50) -> list[dict]:
        """Alias for get_chat."""
        return get_chat(session_id, limit)

    def get_xp_history(limit: int = 50) -> list[dict]:
        """Return most recent XP events, newest last."""
        with tx() as con:
            rows = con.execute(
                "SELECT * FROM xp_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return list(reversed([dict(r) for r in rows]))

    def get_level_info(total_xp: int | None = None) -> tuple[int, str, int, int]:
        """get_level() wrapper that optionally accepts a pre-fetched xp value."""
        return get_level()

    def get_gpa() -> float:
        """Return GPA as a plain float (not tuple)."""
        gpa, _ = compute_gpa()
        return gpa

    def save_llm_generated_flex(type_or_content: str, topic_or_type: str = "", content: str = "") -> int:
        """Flexible wrapper — accepts (content, type) or (type, topic, content_obj)."""
        if content:
            if isinstance(content, (dict, list)):
                stored = json.dumps(content)
            else:
                stored = str(content)
            return save_llm_generated_raw(stored, type_or_content)
        else:
            return save_llm_generated_raw(type_or_content, topic_or_type or "general")

    return {
        "save_setting": save_setting,
        "get_all_achievements": get_all_achievements,
        "get_total_xp": get_total_xp,
        "save_chat_history": save_chat_history,
        "get_chat_history": get_chat_history,
        "get_xp_history": get_xp_history,
        "get_level_info": get_level_info,
        "get_gpa": get_gpa,
        "save_llm_generated": save_llm_generated_flex,
    }
