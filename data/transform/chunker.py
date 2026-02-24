"""Chunk long sessions into training-sized windows.

Strategy:
  - Sliding window of N turn-pairs (user+assistant), configurable
  - 50% overlap between windows for context continuity
  - Never split mid tool-call (if tool_use is in window, tool_result must be too)
  - Always prefix each chunk with the role system prompt
  - Max token budget per chunk (approximate, using character count / 4 as estimate)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from data.extract.sessions import Turn

# Default parameters.
DEFAULT_WINDOW_TURNS = 16  # 8 user-assistant pairs
DEFAULT_STRIDE = 8  # 50% overlap
DEFAULT_MAX_CHARS = 16384  # ~4096 tokens at ~4 chars/token


@dataclass
class Chunk:
    """A training-sized window of conversation turns."""

    turns: list[Turn]
    chunk_index: int = 0
    total_chunks: int = 0
    metadata: dict = field(default_factory=dict)


def chunk_turns(
    turns: list[Turn],
    window_size: int = DEFAULT_WINDOW_TURNS,
    stride: int = DEFAULT_STRIDE,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[Chunk]:
    """Split a list of turns into overlapping chunks.

    Each chunk contains up to window_size turns, with stride turns
    between chunk starts. Chunks are adjusted to respect tool-call
    boundaries and max character limits.
    """
    if len(turns) <= window_size:
        return [Chunk(turns=turns, chunk_index=0, total_chunks=1)]

    chunks: list[Chunk] = []
    start = 0

    while start < len(turns):
        end = min(start + window_size, len(turns))

        # Adjust end to not split mid tool-call.
        end = _adjust_for_tool_boundary(turns, end)

        # Trim from end if over character budget.
        chunk_turns_list = turns[start:end]
        chunk_turns_list = _trim_to_char_budget(chunk_turns_list, max_chars)

        if len(chunk_turns_list) >= 2:  # Minimum viable chunk.
            chunks.append(Chunk(turns=chunk_turns_list, chunk_index=len(chunks)))

        start += stride
        if start >= len(turns):
            break
        # If the next window would be too small, stop.
        if len(turns) - start < 2:
            break

    # Set total_chunks on all.
    for chunk in chunks:
        chunk.total_chunks = len(chunks)

    return chunks


def _adjust_for_tool_boundary(turns: list[Turn], end: int) -> int:
    """Adjust the end index to not split between tool_use and tool_result.

    If the turn at end-1 is an assistant with tool_calls, and the next
    turn is a user with tool_results, extend to include the result.
    """
    if end >= len(turns):
        return end

    last_turn = turns[end - 1]
    if last_turn.role == "assistant" and last_turn.tool_calls:
        # Check if next turn has matching tool results.
        if end < len(turns) and turns[end].role == "user" and turns[end].tool_results:
            return end + 1

    return end


def _trim_to_char_budget(turns: list[Turn], max_chars: int) -> list[Turn]:
    """Remove turns from the end until under the character budget."""
    total = sum(len(t.content) for t in turns)
    result = list(turns)

    while total > max_chars and len(result) > 2:
        removed = result.pop()
        total -= len(removed.content)

    return result
