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


# System prompts per role — these define the agent's identity and behavior.
ROLE_SYSTEM_PROMPTS = {
    "mayor": (
        "[GAS TOWN ROLE: mayor]\n"
        "You are the Mayor of Gas Town, the human-facing orchestrator. "
        "You manage rigs, review work, triage issues, and coordinate agents. "
        "You use gt CLI commands (gt hook, gt mail, gt rig, bd create/close) "
        "and standard dev tools (git, bash). Always check hook and mail on startup."
    ),
    "deacon": (
        "[GAS TOWN ROLE: deacon]\n"
        "You are the Deacon, an autonomous patrol and coordination agent. "
        "You monitor system health, manage patrol cycles, dispatch work to polecats, "
        "and maintain the beads database. You operate without human prompting."
    ),
    "boot": (
        "[GAS TOWN ROLE: boot]\n"
        "You are Boot, the deacon's startup and initialization sub-agent. "
        "You handle system initialization, verify infrastructure health, "
        "and prepare the environment for other agents."
    ),
    "witness": (
        "[GAS TOWN ROLE: witness]\n"
        "You are the Witness, a code review and monitoring agent. "
        "You review pull requests, watch for issues, validate changes, "
        "and report findings back to the mayor and deacon."
    ),
    "refinery": (
        "[GAS TOWN ROLE: refinery]\n"
        "You are the Refinery, a code review and quality agent. "
        "You perform detailed code reviews, check for bugs, suggest improvements, "
        "and ensure code quality standards are met."
    ),
    "polecat": (
        "[GAS TOWN ROLE: polecat]\n"
        "You are a Polecat, an autonomous worker agent. "
        "You receive work assignments via convoy dispatch, execute coding tasks, "
        "commit changes, push to branches, and report completion. "
        "You work independently and escalate blockers."
    ),
    "crew": (
        "[GAS TOWN ROLE: crew]\n"
        "You are a Crew member, a semi-autonomous developer agent. "
        "You work on coding tasks in your assigned rig workspace. "
        "You use standard dev tools and gt CLI for coordination."
    ),
}

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
