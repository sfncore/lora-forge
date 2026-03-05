"""Unit tests for chunker.py covering session chunking with various scenarios."""

import pytest
from dataclasses import dataclass
from data.transform.chunker import (
    chunk_turns,
    _adjust_for_tool_boundary,
    _trim_to_char_budget,
    DEFAULT_WINDOW_TURNS,
    DEFAULT_STRIDE,
    DEFAULT_MAX_CHARS
)
from data.extract.sessions import Turn


class TestChunker:
    def test_short_session_single_chunk(self):
        turns = [
            Turn(role="user", content="Hi"),
            Turn(role="assistant", content="Hello")
        ]
        chunks = chunk_turns(turns)
        assert len(chunks) == 1
        assert len(chunks[0].turns) == 2
        assert chunks[0].chunk_index == 0
        assert chunks[0].total_chunks == 1

    def test_exact_window_size_single_chunk(self):
        turns = [
            Turn(role="user" if i % 2 == 0 else "assistant", content=f"Turn {i}")
            for i in range(DEFAULT_WINDOW_TURNS)
        ]
        chunks = chunk_turns(turns)
        assert len(chunks) == 1
        assert len(chunks[0].turns) == DEFAULT_WINDOW_TURNS

    def test_long_session_multiple_chunks(self):
        turns = [
            Turn(role="user" if i % 2 == 0 else "assistant", content=f"Turn {i}")
            for i in range(20)
        ]
        chunks = chunk_turns(turns, window_size=8, stride=4)
        assert len(chunks) > 1
        # Verify overlapping chunks
        assert chunks[0].turns[-1].content == chunks[1].turns[3].content  # 50% overlap

    def test_chunk_metadata_correct(self):
        turns = [
            Turn(role="user", content="Hi"),
            Turn(role="assistant", content="Hello"),
            Turn(role="user", content="How are you?"),
            Turn(role="assistant", content="I'm good!")
        ]
        chunks = chunk_turns(turns, window_size=2, stride=1)
        assert len(chunks) == 3
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert chunk.total_chunks == 3

    def test_minimum_viable_chunk_size(self):
        turns = [
            Turn(role="user", content="A"),
            Turn(role="assistant", content="B"),
            Turn(role="user", content="C")
        ]
        chunks = chunk_turns(turns, window_size=2, stride=1)
        # Should only keep chunks with at least 2 turns
        assert len(chunks) == 2
        assert len(chunks[0].turns) == 2
        assert len(chunks[1].turns) == 2

    def test_tool_call_boundary_respected(self):
        turns = [
            Turn(role="user", content="Call a tool"),
            Turn(role="assistant", content="tool_use", tool_calls=[{"id": "t1"}]),
            Turn(role="user", content="tool_result", tool_results=[{"tool_use_id": "t1"}]),
            Turn(role="assistant", content="Done")
        ]
        # Try to split right after tool_use - should extend to include tool_result
        chunks = chunk_turns(turns, window_size=4, stride=2)
        assert len(chunks) == 1  # All 4 turns should be in one chunk
        assert len(chunks[0].turns) == 4

    def test_tool_call_at_end_no_extension_needed(self):
        turns = [
            Turn(role="user", content="Call a tool"),
            Turn(role="assistant", content="tool_use", tool_calls=[{"id": "t1"}]),
            Turn(role="user", content="tool_result", tool_results=[{"tool_use_id": "t1"}])
        ]
        chunks = chunk_turns(turns, window_size=3, stride=1)
        # First chunk: turns 0-2 (includes tool_result), second chunk would be too small
        assert len(chunks) == 1
        assert len(chunks[0].turns) == 3

    def test_no_tool_calls_normal_splitting(self):
        turns = [
            Turn(role="user", content=f"Question {i}") for i in range(10)
        ] + [
            Turn(role="assistant", content=f"Answer {i}") for i in range(10)
        ]
        # Interleave properly
        interleaved = []
        for i in range(10):
            interleaved.append(turns[i])
            interleaved.append(turns[i + 10])
        
        chunks = chunk_turns(interleaved, window_size=4, stride=2)
        assert len(chunks) > 1
        # Verify no tool boundary adjustments were made
        total_turns_in_chunks = sum(len(chunk.turns) for chunk in chunks)
        assert total_turns_in_chunks >= len(interleaved) - 2  # Allow for final incomplete chunk

    def test_character_budget_trimming(self):
        long_content = "A" * 10000
        turns = [
            Turn(role="user", content="Short"),
            Turn(role="assistant", content=long_content),
            Turn(role="user", content="Another short"),
            Turn(role="assistant", content="Final short")
        ]
        chunks = chunk_turns(turns, max_chars=10100)
        # Should trim the long turn to fit within budget
        assert len(chunks) == 1
        total_chars = sum(len(t.content) for t in chunks[0].turns)
        assert total_chars <= 10100

    def test_character_budget_preserves_minimum_chunk(self):
        very_long_content = "A" * 20000
        turns = [
            Turn(role="user", content="Start"),
            Turn(role="assistant", content=very_long_content),
            Turn(role="user", content="End")
        ]
        chunks = chunk_turns(turns, max_chars=1000)
        # Should preserve at least 2 turns even if over budget
        assert len(chunks) == 1
        assert len(chunks[0].turns) >= 2

    def test_adjust_for_tool_boundary_no_tool_calls(self):
        turns = [
            Turn(role="user", content="Hi"),
            Turn(role="assistant", content="Hello"),
            Turn(role="user", content="Bye"),
            Turn(role="assistant", content="Goodbye")
        ]
        end = _adjust_for_tool_boundary(turns, 2)
        assert end == 2  # No adjustment needed

    def test_adjust_for_tool_boundary_with_tool_calls(self):
        turns = [
            Turn(role="user", content="Hi"),
            Turn(role="assistant", content="tool_use", tool_calls=[{"id": "t1"}]),
            Turn(role="user", content="tool_result", tool_results=[{"tool_use_id": "t1"}]),
            Turn(role="assistant", content="Done")
        ]
        end = _adjust_for_tool_boundary(turns, 2)  # Would split after tool_use
        assert end == 3  # Extended to include tool_result

    def test_adjust_for_tool_boundary_at_end(self):
        turns = [
            Turn(role="user", content="Hi"),
            Turn(role="assistant", content="tool_use", tool_calls=[{"id": "t1"}])
        ]
        end = _adjust_for_tool_boundary(turns, 2)  # At end of list
        assert end == 2  # No extension possible

    def test_trim_to_char_budget_no_trimming_needed(self):
        turns = [
            Turn(role="user", content="Short"),
            Turn(role="assistant", content="Also short")
        ]
        result = _trim_to_char_budget(turns, max_chars=1000)
        assert result == turns

    def test_trim_to_char_budget_trims_excess(self):
        turns = [
            Turn(role="user", content="A" * 3000),
            Turn(role="assistant", content="B" * 3000),
            Turn(role="user", content="C" * 3000)
        ]
        # Set max_chars to force trimming
        result = _trim_to_char_budget(turns, max_chars=5000)
        assert len(result) == 2  # Third turn removed

    def test_trim_to_char_budget_preserves_minimum(self):
        turns = [
            Turn(role="user", content="A" * 6000),
            Turn(role="assistant", content="B" * 6000)
        ]
        result = _trim_to_char_budget(turns, max_chars=1000)
        assert len(result) == 2  # Minimum of 2 turns preserved despite being over budget