"""Normalize tool_use and tool_result blocks to consistent XML format.

The session extractor already formats tool calls as XML tags. This module
provides additional normalization:
  - Truncate very long tool results (> max_result_tokens chars)
  - Remove redundant/noisy tool results (bash progress, empty output)
  - Standardize tool names
"""

from __future__ import annotations

import re

# Default max characters for a single tool result.
DEFAULT_MAX_RESULT_CHARS = 2000

# Tool results that are pure noise and should be removed entirely.
_NOISE_PATTERNS = [
    re.compile(r"^Shell cwd was reset to"),
    re.compile(r"^WARNING: This binary was built with"),
]


def truncate_tool_result(content: str, max_chars: int = DEFAULT_MAX_RESULT_CHARS) -> str:
    """Truncate a tool result to max_chars, preserving the beginning and end."""
    if len(content) <= max_chars:
        return content

    # Keep first 60% and last 40% of the budget.
    head_budget = int(max_chars * 0.6)
    tail_budget = max_chars - head_budget - 20  # 20 chars for truncation marker

    head = content[:head_budget]
    tail = content[-tail_budget:] if tail_budget > 0 else ""
    return f"{head}\n... [truncated] ...\n{tail}"


def clean_tool_result(content: str) -> str:
    """Remove noise lines from tool result content."""
    lines = content.split("\n")
    cleaned = []
    for line in lines:
        if any(p.search(line) for p in _NOISE_PATTERNS):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def normalize_turn_content(content: str, max_result_chars: int = DEFAULT_MAX_RESULT_CHARS) -> str:
    """Normalize all tool results within a turn's content string.

    Finds <tool_result> blocks and applies truncation and cleaning.
    """
    def replace_result(match: re.Match) -> str:
        tag = match.group(1)  # opening tag with attributes
        body = match.group(2)
        body = clean_tool_result(body)
        body = truncate_tool_result(body, max_result_chars)
        return f"{tag}\n{body}\n</tool_result>"

    return re.sub(
        r"(<tool_result[^>]*>)\n(.*?)\n</tool_result>",
        replace_result,
        content,
        flags=re.DOTALL,
    )
