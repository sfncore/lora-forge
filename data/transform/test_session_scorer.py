"""
Unit tests for session_scorer.py covering all three signal source scenarios.
"""

import pytest
from data.transform.session_scorer import (
    compute_turn_level_score,
    compute_step_level_score, 
    compute_formula_level_score,
    compose_quality_score,
    score_session
)


def test_turn_level_score_empty_session():
    """Test turn-level scoring with empty session."""
    session = {"conversations": []}
    score = compute_turn_level_score(session)
    assert score == 0.5


def test_turn_level_score_with_tool_calls():
    """Test turn-level scoring with successful tool calls."""
    session = {
        "conversations": [
            {"from": "human", "value": "Do something"},
            {"from": "gpt", "value": "tool_use_id=\"tool1\""},
            {"from": "human", "value": "tool_result success"},
            {"from": "gpt", "value": "Done"}
        ]
    }
    score = compute_turn_level_score(session)
    assert 0.0 <= score <= 1.0


def test_step_level_score_with_otel_signals():
    """Test step-level scoring with OTel signals (COMPLETED)."""
    session = {"conversations": [{"from": "human", "value": "test"}]}
    otel_signals = {"exit_type": "COMPLETED"}
    score = compute_step_level_score(session, otel_signals)
    assert score == 1.0


def test_step_level_score_with_otel_signals_escalated():
    """Test step-level scoring with OTel signals (ESCALATED)."""
    session = {"conversations": [{"from": "human", "value": "test"}]}
    otel_signals = {"exit_type": "ESCALATED"}
    score = compute_step_level_score(session, otel_signals)
    assert score == 0.6


def test_step_level_score_heuristic_fallback():
    """Test step-level scoring with heuristic fallback (no OTel signals)."""
    session = {
        "conversations": [
            {"from": "human", "value": "Create something"},
            {"from": "gpt", "value": "I created a file"}
        ]
    }
    score = compute_step_level_score(session, None)
    assert 0.0 <= score <= 1.0


def test_formula_level_score_with_otel_signals():
    """Test formula-level scoring with OTel signals."""
    session = {"role": "polecat", "conversations": [{"from": "human", "value": "test"}]}
    otel_signals = {"exit_type": "COMPLETED", "duration_ms": 200000}
    score = compute_formula_level_score(session, otel_signals)
    assert 0.0 <= score <= 1.0


def test_formula_level_score_heuristic_fallback():
    """Test formula-level scoring with heuristic fallback."""
    session = {
        "role": "polecat",
        "conversations": [
            {"from": "human", "value": "Do task"},
            {"from": "gpt", "value": "gt done"}
        ]
    }
    score = compute_formula_level_score(session, None)
    assert 0.0 <= score <= 1.0


def test_compose_quality_score_full_otel():
    """Test composing quality score with full OTel signals."""
    session = {
        "role": "polecat",
        "conversations": [
            {"from": "human", "value": "Complete task"},
            {"from": "gpt", "value": "tool_use_id=\"tool1\""},
            {"from": "human", "value": "tool_result success"},
            {"from": "gpt", "value": "gt done"}
        ]
    }
    otel_signals = {"exit_type": "COMPLETED", "duration_ms": 200000}
    weights = {"turn_level": 0.3, "step_level": 0.4, "formula_level": 0.3}
    score = compose_quality_score(session, otel_signals, weights)
    assert 0.0 <= score <= 1.0


def test_compose_quality_score_no_otel():
    """Test composing quality score with no OTel signals (heuristic only)."""
    session = {
        "role": "polecat", 
        "conversations": [
            {"from": "human", "value": "Complete task"},
            {"from": "gpt", "value": "I completed the task successfully"}
        ]
    }
    weights = {"turn_level": 0.3, "step_level": 0.4, "formula_level": 0.3}
    score = compose_quality_score(session, None, weights)
    assert 0.0 <= score <= 1.0


def test_score_session_with_otel_signals():
    """Test main entry point with OTel signals."""
    session = {
        "role": "polecat",
        "conversations": [
            {"from": "human", "value": "Test task"},
            {"from": "gpt", "value": "Working on it"},
            {"from": "gpt", "value": "gt done"}
        ],
        "otel_signals": {"exit_type": "COMPLETED", "duration_ms": 150000}
    }
    score = score_session(session)
    assert 0.0 <= score <= 1.0


def test_score_session_without_otel_signals():
    """Test main entry point without OTel signals (heuristic fallback)."""
    session = {
        "role": "polecat",
        "conversations": [
            {"from": "human", "value": "Test task"}, 
            {"from": "gpt", "value": "Completed successfully"}
        ]
    }
    score = score_session(session)
    assert 0.0 <= score <= 1.0


def test_score_distribution_reasonable():
    """Test that score distribution is reasonable (not all 0 or all 1)."""
    sessions = [
        # High quality session
        {
            "role": "polecat",
            "conversations": [
                {"from": "human", "value": "Do important task"},
                {"from": "gpt", "value": "tool_use_id=\"tool1\""},
                {"from": "human", "value": "tool_result success"},
                {"from": "gpt", "value": "gt done"}
            ],
            "otel_signals": {"exit_type": "COMPLETED", "duration_ms": 100000}
        },
        # Medium quality session  
        {
            "role": "polecat",
            "conversations": [
                {"from": "human", "value": "Try this task"},
                {"from": "gpt", "value": "I'll attempt it"},
                {"from": "gpt", "value": "Need help, escalating to witness"}
            ],
            "otel_signals": {"exit_type": "ESCALATED", "duration_ms": 300000}
        },
        # Low quality session
        {
            "role": "polecat", 
            "conversations": [
                {"from": "human", "value": "Simple task"},
                {"from": "gpt", "value": "I don't know how to do this"}
            ]
        }
    ]
    
    scores = [score_session(session) for session in sessions]
    
    # Should have variation in scores
    assert len(set(scores)) > 1
    # All scores should be in valid range
    assert all(0.0 <= score <= 1.0 for score in scores)
    # High quality should score higher than low quality
    assert scores[0] >= scores[2]