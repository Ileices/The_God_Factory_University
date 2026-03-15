"""
Agent loop engine for The God Factory University.

Provides:
  - Tool-calling agent loop (bounded or unlimited mode)
  - Auto-commit vs review-gated draft queue
  - Persistent crash-recoverable state in data/agent_jobs/
  - Rate limiting and progress callbacks
  - Small-model-aware context management
"""
from __future__ import annotations

import json
import re
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from llm.providers import LLMConfig, chat, cfg_from_settings, PROVIDER_CAPABILITIES
from llm.context_manager import (
    build_budget, build_system_prompt, count_tokens, get_context_window,
    is_small_model, trim_history, compress_course_manifest,
)
from llm.tools import call_tool, get_schemas, get_tool, list_tools

ROOT = Path(__file__).resolve().parent.parent
JOBS_DIR = ROOT / "data" / "agent_jobs"

# ─── Enums & config ──────────────────────────────────────────────────────────

class AgentMode(str, Enum):
    BOUNDED = "bounded"       # Run N steps then stop
    UNLIMITED = "unlimited"   # Run until task complete or manually stopped

class ReviewMode(str, Enum):
    AUTO = "auto"             # Auto-commit tool results
    REVIEW = "review"         # Queue results for user review


@dataclass
class AgentConfig:
    mode: AgentMode = AgentMode.BOUNDED
    max_steps: int = 20
    review_mode: ReviewMode = ReviewMode.AUTO
    rate_limit_delay: float = 1.0  # seconds between LLM calls
    tool_categories: list[str] = field(default_factory=lambda: ["course", "video", "utility"])
    task_description: str = ""


@dataclass
class AgentStep:
    """A single step in the agent's execution."""
    step_num: int
    action: str       # "think", "tool_call", "tool_result", "error", "done"
    content: str      # The text/data for this step
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_result: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    tokens_used: int = 0


@dataclass
class AgentJob:
    """Persistent agent job state."""
    job_id: str
    config: AgentConfig
    steps: list[AgentStep] = field(default_factory=list)
    status: str = "pending"  # pending, running, paused, completed, failed
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    draft_queue: list[dict] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "config": {
                "mode": self.config.mode.value,
                "max_steps": self.config.max_steps,
                "review_mode": self.config.review_mode.value,
                "rate_limit_delay": self.config.rate_limit_delay,
                "tool_categories": self.config.tool_categories,
                "task_description": self.config.task_description,
            },
            "steps": [
                {
                    "step_num": s.step_num,
                    "action": s.action,
                    "content": s.content[:2000],
                    "tool_name": s.tool_name,
                    "tool_args": s.tool_args,
                    "tool_result": s.tool_result,
                    "timestamp": s.timestamp,
                    "tokens_used": s.tokens_used,
                }
                for s in self.steps[-50:]  # Keep last 50 steps in state
            ],
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "draft_queue": self.draft_queue[-20:],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> AgentJob:
        cfg_d = d.get("config", {})
        config = AgentConfig(
            mode=AgentMode(cfg_d.get("mode", "bounded")),
            max_steps=cfg_d.get("max_steps", 20),
            review_mode=ReviewMode(cfg_d.get("review_mode", "auto")),
            rate_limit_delay=cfg_d.get("rate_limit_delay", 1.0),
            tool_categories=cfg_d.get("tool_categories", ["course", "video", "utility"]),
            task_description=cfg_d.get("task_description", ""),
        )
        steps = [
            AgentStep(
                step_num=s["step_num"],
                action=s["action"],
                content=s["content"],
                tool_name=s.get("tool_name", ""),
                tool_args=s.get("tool_args", {}),
                tool_result=s.get("tool_result", {}),
                timestamp=s.get("timestamp", 0),
                tokens_used=s.get("tokens_used", 0),
            )
            for s in d.get("steps", [])
        ]
        job = cls(
            job_id=d["job_id"],
            config=config,
            steps=steps,
            status=d.get("status", "pending"),
            created_at=d.get("created_at", 0),
            updated_at=d.get("updated_at", 0),
            draft_queue=d.get("draft_queue", []),
            error=d.get("error", ""),
        )
        return job


# ─── Job persistence ──────────────────────────────────────────────────────────

def _job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def save_job(job: AgentJob) -> None:
    """Save agent job state to disk for crash recovery."""
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    job.updated_at = time.time()
    _job_path(job.job_id).write_text(json.dumps(job.to_dict(), indent=2), encoding="utf-8")


def load_job(job_id: str) -> AgentJob | None:
    """Load a job from disk."""
    path = _job_path(job_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return AgentJob.from_dict(data)


def list_jobs() -> list[dict]:
    """List all saved jobs (summary only)."""
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    jobs = []
    for f in sorted(JOBS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            jobs.append({
                "job_id": data["job_id"],
                "status": data.get("status", "?"),
                "task": data.get("config", {}).get("task_description", "")[:80],
                "steps": len(data.get("steps", [])),
                "created_at": data.get("created_at", 0),
                "updated_at": data.get("updated_at", 0),
            })
        except Exception:
            pass
    return jobs


def delete_job(job_id: str) -> bool:
    path = _job_path(job_id)
    if path.exists():
        path.unlink()
        return True
    return False


# ─── Tool call parsing ────────────────────────────────────────────────────────

_TOOL_CALL_RE = re.compile(
    r'\{\s*"tool"\s*:\s*"([^"]+)"\s*,\s*"args"\s*:\s*(\{[^}]*\})\s*\}',
    re.DOTALL,
)


def parse_tool_call(text: str) -> tuple[str, dict] | None:
    """Extract a tool call from LLM output. Returns (tool_name, args) or None."""
    m = _TOOL_CALL_RE.search(text)
    if not m:
        return None
    tool_name = m.group(1)
    try:
        args = json.loads(m.group(2))
    except (json.JSONDecodeError, ValueError):
        # Try with bracket balancing
        raw_args = m.group(2)
        try:
            # Attempt more lenient parse
            fixed = re.sub(r",\s*}", "}", raw_args)
            args = json.loads(fixed)
        except Exception:
            return None
    return tool_name, args


# ─── Agent system prompt ──────────────────────────────────────────────────────

AGENT_SYSTEM_BASE = """You are Professor Ileices, the autonomous agent of The God Factory University.

You are executing a task step by step. You have tools available to create courses, edit videos, and manage the university.

Rules:
1. Think about what to do next, then call ONE tool at a time
2. Wait for the tool result before deciding the next action
3. When the task is complete, say "TASK_COMPLETE" on its own line
4. If you cannot proceed, say "TASK_BLOCKED: <reason>" on its own line
5. Be efficient — don't repeat work already done
6. Check existing data before creating duplicates

Current task: {task_description}
"""


# ─── Agent loop ───────────────────────────────────────────────────────────────

def run_agent(
    job: AgentJob,
    progress_callback: Callable[[AgentJob], None] | None = None,
    stop_flag: Callable[[], bool] | None = None,
) -> AgentJob:
    """Execute the agent loop.

    Args:
        job: The agent job to execute
        progress_callback: Called after each step with the updated job
        stop_flag: Callable that returns True to stop the agent

    Returns the completed/paused job.
    """
    job.status = "running"
    save_job(job)

    cfg = cfg_from_settings()
    small = is_small_model(cfg)

    # Get available tools
    all_tools = []
    for cat in job.config.tool_categories:
        all_tools.extend(get_schemas(cat))

    # Build system prompt
    system_prompt = build_system_prompt(
        AGENT_SYSTEM_BASE.format(task_description=job.config.task_description),
        all_tools if not small else all_tools[:10],  # Limit tools for small models
        cfg,
    )
    cfg.system_prompt = system_prompt
    cfg.temperature = 0.4  # Lower temp for agent reliability

    step_num = len(job.steps)
    max_steps = job.config.max_steps if job.config.mode == AgentMode.BOUNDED else 10000

    while step_num < max_steps:
        # Check stop flag
        if stop_flag and stop_flag():
            job.status = "paused"
            save_job(job)
            break

        # Rate limiting
        if job.config.rate_limit_delay > 0 and step_num > 0:
            time.sleep(job.config.rate_limit_delay)

        try:
            # Build message history from recent steps
            messages = _build_messages(job.steps, cfg)

            # Call LLM
            result = chat(cfg, messages)
            if isinstance(result, str) and result.startswith("[LLM ERROR]"):
                step = AgentStep(step_num=step_num, action="error",
                                 content=result, tokens_used=0)
                job.steps.append(step)
                job.error = result
                job.status = "failed"
                save_job(job)
                break

            response_text = str(result)
            tokens = count_tokens(response_text)

            # Check for task completion
            if "TASK_COMPLETE" in response_text:
                step = AgentStep(step_num=step_num, action="done",
                                 content=response_text, tokens_used=tokens)
                job.steps.append(step)
                job.status = "completed"
                save_job(job)
                if progress_callback:
                    progress_callback(job)
                break

            if "TASK_BLOCKED" in response_text:
                step = AgentStep(step_num=step_num, action="error",
                                 content=response_text, tokens_used=tokens)
                job.steps.append(step)
                job.status = "failed"
                job.error = response_text
                save_job(job)
                break

            # Try to parse tool call
            tool_call = parse_tool_call(response_text)
            if tool_call:
                tool_name, tool_args = tool_call

                # Record the think + tool call step
                step = AgentStep(
                    step_num=step_num, action="tool_call",
                    content=response_text, tool_name=tool_name,
                    tool_args=tool_args, tokens_used=tokens,
                )
                job.steps.append(step)
                step_num += 1

                # Check if tool requires review
                tool_obj = get_tool(tool_name)
                if tool_obj and tool_obj.requires_review and job.config.review_mode == ReviewMode.REVIEW:
                    job.draft_queue.append({
                        "step": step_num,
                        "tool": tool_name,
                        "args": tool_args,
                        "status": "pending",
                    })
                    result_step = AgentStep(
                        step_num=step_num, action="tool_result",
                        content="Queued for review. Moving to next task.",
                        tool_name=tool_name, tool_result={"queued": True},
                    )
                else:
                    # Execute tool
                    tool_result = call_tool(tool_name, tool_args)
                    result_step = AgentStep(
                        step_num=step_num, action="tool_result",
                        content=json.dumps(tool_result)[:2000],
                        tool_name=tool_name, tool_result=tool_result,
                    )
                job.steps.append(result_step)
            else:
                # No tool call — just thinking
                step = AgentStep(step_num=step_num, action="think",
                                 content=response_text, tokens_used=tokens)
                job.steps.append(step)

            step_num += 1
            save_job(job)

            if progress_callback:
                progress_callback(job)

        except Exception as e:
            step = AgentStep(step_num=step_num, action="error",
                             content=f"Exception: {e}\n{traceback.format_exc()}")
            job.steps.append(step)
            job.error = str(e)
            job.status = "failed"
            save_job(job)
            break

    # If we hit max steps in bounded mode
    if step_num >= max_steps and job.status == "running":
        job.status = "completed" if job.config.mode == AgentMode.BOUNDED else "paused"
        save_job(job)

    return job


def _build_messages(steps: list[AgentStep], cfg: LLMConfig) -> list[dict]:
    """Convert agent steps into chat messages for the LLM."""
    messages: list[dict] = []

    # Initial task prompt (if first step)
    if not steps:
        messages.append({
            "role": "user",
            "content": "Begin the task. Start by analyzing what needs to be done, then use tools to accomplish it.",
        })
        return messages

    # Convert recent steps to messages
    for step in steps[-20:]:  # Keep last 20 steps
        if step.action == "tool_call":
            messages.append({"role": "assistant", "content": step.content})
        elif step.action == "tool_result":
            messages.append({
                "role": "user",
                "content": f"Tool result for {step.tool_name}:\n{step.content[:1500]}",
            })
        elif step.action == "think":
            messages.append({"role": "assistant", "content": step.content})
        elif step.action == "error":
            messages.append({
                "role": "user",
                "content": f"Error occurred: {step.content[:500]}\nPlease adjust your approach.",
            })

    # Trim to fit context
    budget = get_context_window(cfg) // 2  # Use half for history
    messages = trim_history(messages, budget)

    # Always end with a user message prompting next action
    if messages and messages[-1]["role"] == "assistant":
        messages.append({
            "role": "user",
            "content": "Continue with the next step.",
        })

    return messages


# ─── Convenience helpers ──────────────────────────────────────────────────────

def create_job(task: str, mode: str = "bounded", max_steps: int = 20,
               review: str = "auto", categories: list[str] | None = None) -> AgentJob:
    """Create a new agent job."""
    job_id = f"job_{int(time.time())}_{hash(task) & 0xFFFF:04x}"
    config = AgentConfig(
        mode=AgentMode(mode),
        max_steps=max_steps,
        review_mode=ReviewMode(review),
        tool_categories=categories or ["course", "video", "utility"],
        task_description=task,
    )
    job = AgentJob(job_id=job_id, config=config)
    save_job(job)
    return job


def resume_job(job_id: str, **kwargs) -> AgentJob | None:
    """Resume a paused or failed job."""
    job = load_job(job_id)
    if not job:
        return None
    if job.status in ("paused", "failed"):
        job.status = "pending"
        job.error = ""
        return run_agent(job, **kwargs)
    return job
