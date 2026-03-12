"""Format extracted and transformed turns into Axolotl's sharegpt JSONL format.

Output format (one JSON object per line):
{
  "conversations": [
    {"from": "system", "value": "[GAS TOWN ROLE: mayor] You are..."},
    {"from": "human", "value": "Check your hook..."},
    {"from": "gpt", "value": "Mayor, checking in.\n<tool_call>..."}
  ],
  "metadata": {
    "role": "mayor",
    "session_id": "abc-123",
    "chunk_index": 0,
    "quality_score": 0.85
  }
}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TextIO

from data.extract.sessions import Turn


# System prompts per role — loaded from gt_prime_prompts.json (captured from
# `GT_ROLE=<role> gt prime`, stripped of dynamic pid/session header).
# Run scripts/refresh_gt_prime_prompts.py to regenerate after gt prime changes.
_PROMPTS_FILE = Path(__file__).parent / "gt_prime_prompts.json"

def _load_prompts() -> dict:
    if _PROMPTS_FILE.exists():
        with open(_PROMPTS_FILE) as f:
            return json.load(f)
    return {}

ROLE_SYSTEM_PROMPTS = _load_prompts()

DEFAULT_SYSTEM_PROMPT = (
    "[GAS TOWN ROLE: agent]\n"
    "You are a Gas Town agent. You use gt CLI commands and standard "
    "dev tools to accomplish software engineering tasks."
)


def format_sharegpt(
    turns: list[Turn],
    role: str,
    session_id: str = "",
    chunk_index: int = 0,
    quality_score: float = 0.0,
    source: str = "claude-session",
    runtime_type: str = "unknown",
    mcp_servers: list[str] | None = None,
) -> dict:
    """Format a list of turns into Axolotl's sharegpt format.

    Returns a dict ready for JSON serialization.
    """
    system_prompt = ROLE_SYSTEM_PROMPTS.get(role, DEFAULT_SYSTEM_PROMPT)

    conversations = [{"from": "system", "value": system_prompt}]

    for turn in turns:
        if turn.role == "user":
            conversations.append({"from": "human", "value": turn.content})
        elif turn.role == "assistant":
            conversations.append({"from": "gpt", "value": turn.content})

    # Merge consecutive same-role messages (can happen after filtering).
    conversations = _merge_consecutive(conversations)

    # Ensure conversation alternates human/gpt after system.
    conversations = _ensure_alternating(conversations)

    return {
        "conversations": conversations,
        "metadata": {
            "role": role,
            "session_id": session_id,
            "chunk_index": chunk_index,
            "quality_score": quality_score,
            "source": source,
            "runtime_type": runtime_type,
            "mcp_servers": mcp_servers or [],
        },
    }


def write_jsonl(samples: list[dict], output_path: Path) -> int:
    """Write samples to a JSONL file. Returns count written."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
            count += 1
    return count


def append_jsonl(sample: dict, f: TextIO) -> None:
    """Append a single sample to an open JSONL file handle."""
    f.write(json.dumps(sample, ensure_ascii=False) + "\n")


def _merge_consecutive(conversations: list[dict]) -> list[dict]:
    """Merge consecutive messages from the same role."""
    if not conversations:
        return []

    merged = [conversations[0]]
    for msg in conversations[1:]:
        if msg["from"] == merged[-1]["from"]:
            merged[-1]["value"] += "\n" + msg["value"]
        else:
            merged.append(msg)
    return merged


def _ensure_alternating(conversations: list[dict]) -> list[dict]:
    """Ensure conversation alternates human/gpt after system prompt.

    Axolotl's sharegpt format requires strict alternation.
    Drop messages that break the pattern.
    """
    if not conversations:
        return []

    result = []
    # Keep system prompt if present.
    start = 0
    if conversations[0]["from"] == "system":
        result.append(conversations[0])
        start = 1

    expected = "human"  # After system, expect human first.
    for msg in conversations[start:]:
        if msg["from"] == expected:
            result.append(msg)
            expected = "gpt" if expected == "human" else "human"

    # Must end with gpt (assistant response).
    while result and result[-1]["from"] != "gpt":
        result.pop()

    return result
