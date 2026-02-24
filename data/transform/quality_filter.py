"""Filter low-quality training samples.

Quality criteria:
  - Minimum turn count (skip trivially short sessions)
  - Remove startup boilerplate-only sessions
  - Remove sessions that are only error messages
  - Score sessions by signal density (tool use, substantive responses)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from data.extract.sessions import Turn

# Patterns that indicate boilerplate/low-signal content.
_BOILERPLATE_PATTERNS = [
    re.compile(r"^Mayor,?\s+checking in\.?$", re.IGNORECASE),
    re.compile(r"^Let me check.*(hook|mail)", re.IGNORECASE),
    re.compile(r"^Nothing on hook", re.IGNORECASE),
    re.compile(r"^No .* messages", re.IGNORECASE),
]

# Minimum number of substantive turns to keep a sample.
MIN_SUBSTANTIVE_TURNS = 2

# Minimum total content length (characters) for a sample.
MIN_CONTENT_LENGTH = 200


@dataclass
class QualityResult:
    """Result of quality assessment."""

    keep: bool
    score: float  # 0.0 to 1.0
    reason: str = ""


def assess_turns(turns: list[Turn]) -> QualityResult:
    """Assess the quality of a list of conversation turns.

    Returns a QualityResult with keep=True/False and a quality score.
    """
    if len(turns) < 2:
        return QualityResult(keep=False, score=0.0, reason="too few turns")

    # Count substantive turns (non-boilerplate).
    substantive = 0
    total_content_len = 0
    tool_call_count = 0
    tool_result_count = 0

    for turn in turns:
        content = turn.content.strip()
        total_content_len += len(content)

        if turn.role == "assistant":
            if turn.tool_calls:
                tool_call_count += len(turn.tool_calls)
            if not _is_boilerplate(content):
                substantive += 1
        elif turn.role == "user":
            if turn.tool_results:
                tool_result_count += len(turn.tool_results)
            if not _is_boilerplate(content) and not content.startswith("<tool_result"):
                substantive += 1

    if substantive < MIN_SUBSTANTIVE_TURNS:
        return QualityResult(keep=False, score=0.1, reason="too few substantive turns")

    if total_content_len < MIN_CONTENT_LENGTH:
        return QualityResult(keep=False, score=0.1, reason="content too short")

    # Score based on signal density.
    score = 0.0

    # Base score from substantive turn ratio.
    total_turns = len(turns)
    score += 0.3 * min(substantive / max(total_turns, 1), 1.0)

    # Tool usage is high-signal (agents use tools to accomplish tasks).
    if tool_call_count > 0:
        score += 0.3 * min(tool_call_count / 10, 1.0)

    # Content density.
    avg_content = total_content_len / max(total_turns, 1)
    score += 0.2 * min(avg_content / 500, 1.0)

    # Conversation depth (more turns = more complex interaction).
    score += 0.2 * min(total_turns / 20, 1.0)

    return QualityResult(keep=True, score=round(score, 3))


def _is_boilerplate(content: str) -> bool:
    """Check if content is boilerplate (startup protocol, etc.)."""
    # Check first line only (multi-line responses are usually substantive).
    first_line = content.split("\n")[0].strip()
    return any(p.match(first_line) for p in _BOILERPLATE_PATTERNS)
