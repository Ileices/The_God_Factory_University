"""
Model-aware context budgeting for The God Factory University.

Handles:
  - Token estimation (tiktoken when available, char fallback)
  - Context window budgeting per provider
  - Compressed course manifests for small models
  - Sliding-window history with LLM summarization
  - Dual prompt formatting (full for large models, compressed for 3B)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from llm.providers import (
    LLMConfig, PROVIDER_CAPABILITIES, estimate_tokens, simple_complete,
)

# ─── Token estimation (improved) ─────────────────────────────────────────────

_tokenizer = None


def _load_tokenizer():
    global _tokenizer
    if _tokenizer is not None:
        return _tokenizer
    try:
        import tiktoken
        _tokenizer = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _tokenizer = False  # sentinel: tried and failed
    return _tokenizer


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken if available, else char/4 fallback."""
    tok = _load_tokenizer()
    if tok and tok is not False:
        return len(tok.encode(text))
    return max(1, len(text) // 4)


def count_message_tokens(messages: list[dict]) -> int:
    """Estimate total tokens for a message list."""
    total = 0
    for m in messages:
        total += count_tokens(m.get("content", "")) + 4  # per-message overhead
    return total


# ─── Context budget ──────────────────────────────────────────────────────────

@dataclass
class ContextBudget:
    """Tracks how much context window is used vs available."""
    context_window: int
    system_tokens: int = 0
    tool_tokens: int = 0
    history_tokens: int = 0
    reserved_for_output: int = 1024

    @property
    def used(self) -> int:
        return self.system_tokens + self.tool_tokens + self.history_tokens

    @property
    def remaining(self) -> int:
        return max(0, self.context_window - self.used - self.reserved_for_output)

    @property
    def user_content_budget(self) -> int:
        """Tokens available for the actual user content/prompt."""
        return self.remaining

    def fits(self, text: str) -> bool:
        return count_tokens(text) <= self.remaining


def get_context_window(cfg: LLMConfig) -> int:
    """Get context window size for a provider/model."""
    caps = PROVIDER_CAPABILITIES.get(cfg.provider, {})
    return caps.get("context_window", 4096)


def is_small_model(cfg: LLMConfig) -> bool:
    """Heuristic: is this a small (≤8K context) model?"""
    return get_context_window(cfg) <= 8192


def build_budget(cfg: LLMConfig, system_prompt: str,
                 tool_descriptions: str = "", history: list[dict] | None = None) -> ContextBudget:
    """Calculate a full context budget for a given configuration."""
    ctx_win = get_context_window(cfg)
    budget = ContextBudget(
        context_window=ctx_win,
        system_tokens=count_tokens(system_prompt),
        tool_tokens=count_tokens(tool_descriptions) if tool_descriptions else 0,
        history_tokens=count_message_tokens(history) if history else 0,
        reserved_for_output=min(cfg.max_tokens, ctx_win // 4),
    )
    return budget


# ─── Compressed course manifests ─────────────────────────────────────────────

def compress_course_manifest(course: dict, modules: list[dict] | None = None) -> str:
    """Create a minimal text manifest of a course for small-model context.

    Format: one line per item, abbreviated keys, no JSON overhead.
    Example: "C:CS101 Introduction to CS|M:CS101-M1 Variables|L:CS101-M1-L1 What is a variable?"
    """
    lines = []
    cid = course.get("course_id") or course.get("id", "")
    title = course.get("title", "")
    credits = course.get("credits", 3)
    lines.append(f"C:{cid} {title} ({credits}cr)")

    if modules:
        for m in modules:
            mid = m.get("module_id") or m.get("id", "")
            lines.append(f"  M:{mid} {m.get('title', '')}")
            for lec in m.get("lectures", []):
                lid = lec.get("lecture_id") or lec.get("id", "")
                lines.append(f"    L:{lid} {lec.get('title', '')}")
    return "\n".join(lines)


def compress_all_courses(courses: list[dict]) -> str:
    """One-line-per-course summary for context injection."""
    lines = []
    for c in courses:
        cid = c.get("course_id") or c.get("id", "")
        title = c.get("title", "")
        lines.append(f"{cid}: {title}")
    return "\n".join(lines)


# ─── Sliding-window history ──────────────────────────────────────────────────

def trim_history(messages: list[dict], budget_tokens: int) -> list[dict]:
    """Keep the most recent messages that fit within budget_tokens."""
    kept: list[dict] = []
    total = 0
    for msg in reversed(messages):
        tokens = count_tokens(msg.get("content", "")) + 4
        if total + tokens > budget_tokens:
            break
        kept.append(msg)
        total += tokens
    kept.reverse()
    return kept


def summarize_history(messages: list[dict], cfg: LLMConfig) -> str:
    """Use the LLM to create a compressed summary of conversation history."""
    if not messages:
        return ""
    text = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in messages[:20])
    prompt = (
        "Summarize this conversation in 2-3 sentences. "
        "Focus on key decisions, topics discussed, and any pending tasks:\n\n"
        f"{text}"
    )
    result = simple_complete(cfg, prompt)
    if isinstance(result, str) and result.startswith("[LLM ERROR]"):
        # Fallback: just take the last few messages
        return "\n".join(m["content"][:100] for m in messages[-3:])
    return result


# ─── Dual prompt formatting ─────────────────────────────────────────────────

def format_tool_for_model(tool: dict, small: bool) -> str:
    """Format a tool description for the model size.

    Large models get full JSON schema.
    Small models get compressed one-liners.
    """
    name = tool.get("name", "")
    desc = tool.get("description", "")
    params = tool.get("parameters", {})

    if small:
        # Compressed: name(param1, param2) - description
        param_names = list(params.get("properties", {}).keys()) if isinstance(params, dict) else []
        required = params.get("required", []) if isinstance(params, dict) else []
        param_str = ", ".join(
            f"{p}*" if p in required else p for p in param_names
        )
        return f"{name}({param_str}) - {desc[:80]}"
    else:
        # Full JSON schema
        return json.dumps(tool, indent=2)


def format_tools_block(tools: list[dict], small: bool) -> str:
    """Format all tools into a single text block for the system prompt."""
    if small:
        header = "Available tools (call by name with params):\n"
        lines = [format_tool_for_model(t, True) for t in tools]
        return header + "\n".join(lines)
    else:
        header = "You have access to these tools. Call them by outputting JSON:\n"
        blocks = [format_tool_for_model(t, False) for t in tools]
        return header + "\n\n".join(blocks)


def build_system_prompt(base_prompt: str, tools: list[dict],
                        cfg: LLMConfig, course_context: str = "") -> str:
    """Build a complete system prompt that fits the model's context.

    For small models: compresses tools and course context.
    For large models: includes full detail.
    """
    small = is_small_model(cfg)
    parts = [base_prompt]

    if tools:
        tools_block = format_tools_block(tools, small)
        parts.append(tools_block)

    tool_call_instructions = (
        "\nTo call a tool, output EXACTLY this JSON format on its own line:\n"
        '{"tool": "tool_name", "args": {"param1": "value1"}}\n'
        "After the tool result, continue your response.\n"
        "Only call ONE tool at a time. Wait for the result before calling another."
    )
    parts.append(tool_call_instructions)

    if course_context:
        if small:
            # Truncate context for small models
            max_ctx = 300
            if count_tokens(course_context) > max_ctx:
                course_context = course_context[:max_ctx * 4] + "\n..."
        parts.append(f"\nCurrent course context:\n{course_context}")

    return "\n\n".join(parts)
