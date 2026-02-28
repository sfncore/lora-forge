#!/usr/bin/env python3
"""
VictoriaLogs Training Data Extractor

This script extracts training data from Gas Town agent sessions and produces
OpenAI chat JSONL training files. Since VictoriaLogs doesn't contain the actual
session telemetry data, this script works with the existing Claude session JSONL
files that contain the full conversation history.

The script:
1. Discovers session files in ~/.claude/projects/
2. Extracts conversations correlated by session_id 
3. Reconstructs assistant/user/tool message sequences
4. Filters for quality (completed tasks, no error loops, reasonable token counts)
5. Outputs valid OpenAI JSONL with system/user/assistant messages
"""

import argparse
import json
import logging
from pathlib import Path
from typing import List, Optional

from data.extract.sessions import extract_session, discover_sessions
from data.transform.chat_formatter import format_sharegpt, write_jsonl


def setup_logging(verbose: bool = False) -> None:
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


def filter_quality_sessions(sessions: List) -> List:
    """
    Filter sessions for quality based on:
    - Completed tasks (non-empty turns)
    - Reasonable token counts (< 50k tokens)
    - No obvious error loops
    """
    filtered = []
    for session in sessions:
        if not session.turns:
            continue
            
        # Estimate token count (rough approximation)
        total_chars = sum(len(turn.content) for turn in session.turns)
        estimated_tokens = total_chars // 4  # Rough estimate: 4 chars per token
        
        if estimated_tokens > 50000:  # Skip very long sessions
            continue
            
        # Skip sessions that look like error loops (repetitive content)
        if _is_error_loop(session.turns):
            continue
            
        filtered.append(session)
        
    return filtered


def _is_error_loop(turns: List) -> bool:
    """Detect obvious error loops in conversation turns."""
    if len(turns) < 3:
        return False
        
    # Check for repetitive patterns in last few turns
    contents = [turn.content.strip() for turn in turns[-3:]]
    if len(set(contents)) == 1 and contents[0]:
        # Same content repeated 3 times
        return True
        
    return False


def get_role_from_session_path(session_path: Path) -> str:
    """Extract role from session path (e.g., 'mayor', 'witness', 'polecat')."""
    # Path format: ~/.claude/projects/-home-ubuntu-gt-<role>/session.jsonl
    parent_name = session_path.parent.name
    if parent_name.startswith("-home-ubuntu-gt-"):
        role = parent_name[len("-home-ubuntu-gt-"):]
        # Handle compound roles like "lora_forge/witness"
        if "/" in role:
            role = role.split("/")[-1]
        return role
    return "unknown"


def main():
    parser = argparse.ArgumentParser(description="Extract training data from Gas Town sessions")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path.home() / ".claude" / "projects",
        help="Directory containing session JSONL files"
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=Path("output/training_data.jsonl"),
        help="Output JSONL file path"
    )
    parser.add_argument(
        "--role",
        type=str,
        help="Filter sessions by specific role (e.g., 'polecat', 'witness')"
    )
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=1000,
        help="Maximum number of sessions to process"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    
    logger = logging.getLogger(__name__)
    
    # Discover session files
    logger.info(f"Discovering sessions in {args.input_dir}")
    session_files = discover_sessions(args.input_dir)
    logger.info(f"Found {len(session_files)} session files")
    
    if not session_files:
        logger.warning("No session files found")
        return
        
    # Process sessions
    extracted_sessions = []
    processed_count = 0
    
    for session_file in session_files[:args.max_sessions]:
        try:
            session = extract_session(session_file)
            if session:
                # Apply role filter if specified
                if args.role:
                    session_role = get_role_from_session_path(session_file)
                    if session_role != args.role:
                        continue
                        
                extracted_sessions.append(session)
                processed_count += 1
                
                if processed_count % 100 == 0:
                    logger.info(f"Processed {processed_count} sessions")
                    
        except Exception as e:
            logger.error(f"Error processing {session_file}: {e}")
            continue
    
    logger.info(f"Successfully extracted {len(extracted_sessions)} sessions")
    
    # Filter for quality
    logger.info("Filtering sessions for quality...")
    quality_sessions = filter_quality_sessions(extracted_sessions)
    logger.info(f"Filtered down to {len(quality_sessions)} quality sessions")
    
    # Format and write output
    logger.info(f"Writing output to {args.output_file}")
    samples = []
    
    for session in quality_sessions:
        role = get_role_from_session_path(Path(session.source_path))
        sample = format_sharegpt(
            turns=session.turns,
            role=role,
            session_id=session.session_id,
            quality_score=0.8  # Placeholder quality score
        )
        samples.append(sample)
    
    written_count = write_jsonl(samples, args.output_file)
    logger.info(f"Wrote {written_count} samples to {args.output_file}")


if __name__ == "__main__":
    main()