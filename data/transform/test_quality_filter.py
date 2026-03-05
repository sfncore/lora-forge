"""Unit tests for quality_filter.py covering various quality assessment scenarios."""

import pytest
from data.transform.quality_filter import (
    assess_turns,
    _is_boilerplate,
    MIN_SUBSTANTIVE_TURNS,
    MIN_CONTENT_LENGTH
)
from data.extract.sessions import Turn


class TestQualityFilter:
    def test_too_few_turns_rejected(self):
        turns = [Turn(role="user", content="Hi")]
        result = assess_turns(turns)
        assert result.keep is False
        assert result.reason == "too few turns"
        assert result.score == 0.0

    def test_minimum_turns_accepted(self):
        turns = [
            Turn(role="user", content="Hello with sufficient content length to pass the minimum threshold that exceeds 200 characters total when combined with the assistant response."),
            Turn(role="assistant", content="Hi there! This is a detailed response with enough content to ensure the total character count exceeds the minimum threshold of 200 characters.")
        ]
        result = assess_turns(turns)
        assert result.keep is True

    def test_boilerplate_detection(self):
        assert _is_boilerplate("Mayor, checking in.")
        assert _is_boilerplate("Let me check my hook")
        assert _is_boilerplate("Nothing on hook")
        assert _is_boilerplate("No new messages")
        assert not _is_boilerplate("This is actual work content")
        assert not _is_boilerplate("Multiple lines\nwith actual content")

    def test_substantive_turns_counting(self):
        turns = [
            Turn(role="user", content="Mayor, checking in. This is boilerplate content that should be filtered out."),  # boilerplate
            Turn(role="assistant", content="Let me check my hook for any assigned work."),  # boilerplate  
            Turn(role="user", content="Actually do some real work here with substantial content that exceeds the minimum length requirement."),
            Turn(role="assistant", content="I'm implementing the feature now with comprehensive details and thorough explanation.")
        ]
        result = assess_turns(turns)
        # Should have 2 substantive turns (last two)
        assert result.keep is True

    def test_insufficient_substantive_turns_rejected(self):
        turns = [
            Turn(role="user", content="Mayor, checking in. This is boilerplate content."),
            Turn(role="assistant", content="Let me check my hook for work."),
            Turn(role="user", content="Nothing on hook, so no substantive work done.")
        ]
        result = assess_turns(turns)
        assert result.keep is False
        assert result.reason == "too few substantive turns"

    def test_content_length_too_short_rejected(self):
        # Create content that totals less than MIN_CONTENT_LENGTH (200)
        short_content = "A" * 100
        turns = [
            Turn(role="user", content=short_content),
            Turn(role="assistant", content="Short response")
        ]
        result = assess_turns(turns)
        assert result.keep is False
        assert result.reason == "content too short"
        assert result.keep is False
        assert result.reason == "content too short"

    def test_content_length_sufficient_accepted(self):
        sufficient_content = "A" * (MIN_CONTENT_LENGTH + 10)
        turns = [
            Turn(role="user", content=sufficient_content),
            Turn(role="assistant", content="Adequate response")
        ]
        result = assess_turns(turns)
        assert result.keep is True

    def test_tool_calls_increase_score(self):
        turns = [
            Turn(role="user", content="Please use a tool to accomplish this task with sufficient content."),
            Turn(role="assistant", content="Using tool to process the request.", tool_calls=[{"id": "t1"}]),
            Turn(role="user", content="tool_result showing successful execution with detailed output."),
            Turn(role="assistant", content="Task completed successfully with comprehensive results.")
        ]
        result = assess_turns(turns)
        assert result.keep is True
        assert result.score > 0.3  # Tool usage should contribute significantly

    def test_outcome_score_override(self):
        turns = [
            Turn(role="user", content="Test content with sufficient length to meet minimum requirements that exceeds 200 characters total."),
            Turn(role="assistant", content="Test response that provides adequate detail and meets content length thresholds with sufficient characters.")
        ]
        outcome_score = 0.85
        result = assess_turns(turns, outcome_score=outcome_score)
        assert result.keep is True
        assert result.score == outcome_score
        assert result.outcome_score == outcome_score

    def test_outcome_score_override_rejects_low_quality(self):
        turns = [Turn(role="user", content="Too short")]
        outcome_score = 0.9
        result = assess_turns(turns, outcome_score=outcome_score)
        assert result.keep is False
        assert result.score == outcome_score
        assert result.reason == "too few turns"

    def test_heuristic_scoring_components(self):
        # Create a high-quality session
        turns = []
        for i in range(10):  # Multiple turns
            turns.append(Turn(role="user", content=f"Question {i} with substantial content"))
            turns.append(Turn(role="assistant", content=f"Answer {i} with detailed explanation and tool usage", 
                            tool_calls=[{"id": f"tool{i}"}]))
        
        result = assess_turns(turns)
        assert result.keep is True
        assert result.score > 0.5  # Should be reasonably high

    def test_tool_results_in_user_turns(self):
        turns = [
            Turn(role="user", content="Initial request with sufficient content length."),
            Turn(role="assistant", content="tool_use to execute the requested operation.", tool_calls=[{"id": "t1"}]),
            Turn(role="user", content="<tool_result>Successful execution with detailed results.</tool_result>"),
            Turn(role="assistant", content="Completed successfully with comprehensive follow-up information.")
        ]
        result = assess_turns(turns)
        assert result.keep is True
        # User turn with tool_result should not be counted as boilerplate
        assert result.score > 0.3

    def test_mixed_boilerplate_and_substantive(self):
        turns = [
            Turn(role="user", content="Mayor, checking in. This is boilerplate startup protocol."),  # boilerplate
            Turn(role="assistant", content="Let me check my hook for any assigned tasks."),  # boilerplate
            Turn(role="user", content="Actually implement the feature properly with comprehensive details and thorough explanation that exceeds minimum length."),
            Turn(role="assistant", content="I'll create comprehensive tests for all components with detailed coverage and edge cases."),
            Turn(role="user", content="Great, that sounds good and provides sufficient substantive content.")
        ]
        result = assess_turns(turns)
        # Should have 3 substantive turns (last three)
        assert result.keep is True
        assert result.score > 0.3

    def test_empty_content_handling(self):
        turns = [
            Turn(role="user", content=""),
            Turn(role="assistant", content="")
        ]
        result = assess_turns(turns)
        assert result.keep is False
        assert result.reason == "content too short"