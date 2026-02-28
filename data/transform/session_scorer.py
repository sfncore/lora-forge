"""
Session scorer that aggregates multi-level signals into a single quality score.

This module implements the score composer that takes a session with linked bead_id
and OTel signals (from A.1 session_linker output) and computes scores at three levels:
- Turn-level: tool success rate, error recovery patterns
- Step-level: artifact production, escalation count  
- Formula-level: completion rate, duration vs role median

The final quality_score is composed via configurable weights dict, which will be
optimized by CMA-ES in Phase 3.
"""

from typing import Dict, List, Optional, Any
import statistics


def compute_turn_level_score(session: Dict[str, Any]) -> float:
    """
    Compute turn-level score based on tool success rate and error recovery patterns.
    
    Args:
        session: Session dictionary containing conversation turns
        
    Returns:
        float between 0.0 and 1.0 representing turn-level quality
    """
    if not session.get("conversations"):
        return 0.5  # Neutral score for empty sessions
    
    turns = session["conversations"]
    total_turns = len(turns)
    successful_tool_calls = 0
    error_recoveries = 0
    
    # Count successful tool calls and error recoveries
    for i, turn in enumerate(turns):
        if turn.get("from") == "gpt":
            content = turn.get("value", "")
            # Simple heuristic: look for tool call patterns
            if "tool_result" in content or "tool_use_id" in content:
                # Check if next turn indicates success (not an error message)
                if i + 1 < len(turns):
                    next_turn = turns[i + 1]
                    if next_turn.get("from") == "human":
                        next_content = next_turn.get("value", "")
                        if "error" not in next_content.lower() and "failed" not in next_content.lower():
                            successful_tool_calls += 1
                        else:
                            # Check if agent recovered from error in subsequent turns
                            for j in range(i + 2, min(i + 5, len(turns))):
                                if turns[j].get("from") == "gpt":
                                    recovery_content = turns[j].get("value", "")
                                    if "retry" in recovery_content.lower() or "attempt" in recovery_content.lower():
                                        error_recoveries += 1
                                        break
    
    # Calculate scores
    tool_success_rate = successful_tool_calls / max(total_turns, 1)
    recovery_rate = error_recoveries / max(total_turns, 1)
    
    # Weighted combination
    turn_score = 0.7 * tool_success_rate + 0.3 * recovery_rate
    return max(0.0, min(1.0, turn_score))


def compute_step_level_score(session: Dict[str, Any], otel_signals: Optional[Dict[str, Any]] = None) -> float:
    """
    Compute step-level score based on artifact production and escalation count.
    
    Args:
        session: Session dictionary
        otel_signals: Optional OpenTelemetry signals from A.1 session_linker
        
    Returns:
        float between 0.0 and 1.0 representing step-level quality
    """
    # Priority cascade: OTel signals -> bead lifecycle -> events trail -> heuristic
    if otel_signals:
        # Use OTel signals if available
        exit_type = otel_signals.get("exit_type")
        if exit_type == "COMPLETED":
            step_score = 1.0
        elif exit_type == "ESCALATED":
            step_score = 0.6
        elif exit_type == "DEFERRED":
            step_score = 0.4
        else:
            step_score = 0.5
    else:
        # Fallback to heuristic based on session content
        content = ""
        for turn in session.get("conversations", []):
            content += turn.get("value", "") + " "
            
        # Look for artifact production indicators
        artifact_indicators = ["created", "generated", "produced", "wrote", "implemented"]
        escalation_indicators = ["escalate", "help", "stuck", "blocked", "witness", "mayor"]
        
        artifact_count = sum(1 for indicator in artifact_indicators if indicator in content.lower())
        escalation_count = sum(1 for indicator in escalation_indicators if indicator in content.lower())
        
        # Normalize scores
        artifact_score = min(artifact_count / 3.0, 1.0)  # Cap at 3 artifacts
        escalation_penalty = min(escalation_count / 5.0, 1.0)  # Penalize up to 5 escalations
        
        step_score = artifact_score * (1.0 - escalation_penalty * 0.5)
    
    return max(0.0, min(1.0, step_score))


def compute_formula_level_score(session: Dict[str, Any], otel_signals: Optional[Dict[str, Any]] = None) -> float:
    """
    Compute formula-level score based on completion rate and duration vs role median.
    
    Args:
        session: Session dictionary  
        otel_signals: Optional OpenTelemetry signals from A.1 session_linker
        
    Returns:
        float between 0.0 and 1.0 representing formula-level quality
    """
    if otel_signals:
        # Use OTel duration data if available
        duration_ms = otel_signals.get("duration_ms", 0)
        role = session.get("role", "unknown")
        
        # These would normally come from role-specific medians
        # For now, use reasonable defaults
        role_medians = {
            "polecat": 300000,  # 5 minutes
            "witness": 600000,  # 10 minutes  
            "deacon": 900000,   # 15 minutes
            "mayor": 1200000,   # 20 minutes
            "refinery": 600000, # 10 minutes
            "crew": 300000      # 5 minutes
        }
        
        median_duration = role_medians.get(role, 600000)  # Default to 10 minutes
        
        # Score based on duration efficiency (shorter than median = better)
        if duration_ms <= median_duration:
            duration_score = 1.0 - (duration_ms / (2 * median_duration))
        else:
            duration_score = 0.5 - min((duration_ms - median_duration) / (2 * median_duration), 0.5)
            
        # Completion rate from exit type
        exit_type = otel_signals.get("exit_type")
        if exit_type == "COMPLETED":
            completion_score = 1.0
        elif exit_type == "ESCALATED":
            completion_score = 0.7
        elif exit_type == "DEFERRED":
            completion_score = 0.3
        else:
            completion_score = 0.5
            
        formula_score = 0.6 * completion_score + 0.4 * duration_score
    else:
        # Heuristic fallback based on session length and content
        turn_count = len(session.get("conversations", []))
        
        # Reasonable turn counts by role
        role_turn_targets = {
            "polecat": 10,
            "witness": 15, 
            "deacon": 20,
            "mayor": 25,
            "refinery": 15,
            "crew": 10
        }
        
        role = session.get("role", "unknown")
        target_turns = role_turn_targets.get(role, 15)
        
        # Score based on appropriate length (not too short, not too long)
        if turn_count <= target_turns:
            length_score = turn_count / target_turns
        else:
            length_score = 1.0 - min((turn_count - target_turns) / target_turns, 0.5)
            
        # Content quality heuristic
        content_quality = 0.5
        if session.get("conversations"):
            last_turn = session["conversations"][-1]
            if last_turn.get("from") == "gpt":
                last_content = last_turn.get("value", "")
                if "gt done" in last_content or "completed" in last_content.lower():
                    content_quality = 1.0
                elif "escalate" in last_content.lower() or "help" in last_content.lower():
                    content_quality = 0.6
                    
        formula_score = 0.7 * content_quality + 0.3 * length_score
        
    return max(0.0, min(1.0, formula_score))


def compose_quality_score(
    session: Dict[str, Any], 
    otel_signals: Optional[Dict[str, Any]] = None,
    weights: Optional[Dict[str, float]] = None
) -> float:
    """
    Compose final quality score from turn, step, and formula level scores.
    
    Args:
        session: Session dictionary with conversations and metadata
        otel_signals: Optional OTel signals from A.1 session_linker output
        weights: Configurable weights for each level (default provided)
        
    Returns:
        float between 0.0 and 1.0 representing overall session quality
    """
    if weights is None:
        # Default weights - these will be optimized by CMA-ES in Phase 3
        weights = {
            "turn_level": 0.3,
            "step_level": 0.4, 
            "formula_level": 0.3
        }
    
    # Compute individual level scores
    turn_score = compute_turn_level_score(session)
    step_score = compute_step_level_score(session, otel_signals)
    formula_score = compute_formula_level_score(session, otel_signals)
    
    # Compose final score
    quality_score = (
        weights["turn_level"] * turn_score +
        weights["step_level"] * step_score +
        weights["formula_level"] * formula_score
    )
    
    return max(0.0, min(1.0, quality_score))


def score_session(session: Dict[str, Any]) -> float:
    """
    Main entry point to score a session.
    
    Accepts session dict with optional otel_signals (from A.1 session_linker output).
    Returns quality_score float between 0.0 and 1.0.
    
    Args:
        session: Session dictionary containing:
            - conversations: list of conversation turns
            - role: agent role 
            - otel_signals: optional OTel signals (from A.1 output)
            
    Returns:
        float between 0.0 and 1.0 representing session quality
    """
    otel_signals = session.get("otel_signals")
    return compose_quality_score(session, otel_signals)