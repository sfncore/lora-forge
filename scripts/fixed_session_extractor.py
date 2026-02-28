#!/usr/bin/env python3
"""
Fixed Session Data Extractor

Direct extraction from Claude session JSONL files using the proven data pipeline.
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.extract.sessions import extract_session
from data.transform.chat_formatter import format_sharegpt, write_jsonl


def main():
    # Get all JSONL files in the projects directory
    projects_dir = Path.home() / ".claude" / "projects"
    jsonl_files = list(projects_dir.glob("**/*.jsonl"))
    
    print(f"Found {len(jsonl_files)} JSONL files")
    
    # Process first 5 files for testing
    samples = []
    processed = 0
    
    for jsonl_file in jsonl_files[:5]:
        try:
            session = extract_session(jsonl_file)
            if session and session.turns:
                # Extract role from path
                parent_name = jsonl_file.parent.name
                if parent_name.startswith("-home-ubuntu-gt-"):
                    role = parent_name[len("-home-ubuntu-gt-"):]
                    if "/" in role:
                        role = role.split("/")[-1]
                else:
                    role = "unknown"
                
                # Format as sharegpt
                sample = format_sharegpt(
                    turns=session.turns,
                    role=role,
                    session_id=session.session_id,
                    quality_score=0.8
                )
                samples.append(sample)
                processed += 1
                print(f"Processed session: {session.session_id} ({len(session.turns)} turns)")
                
        except Exception as e:
            print(f"Error processing {jsonl_file}: {e}")
            continue
    
    print(f"Successfully processed {processed} sessions")
    
    # Write output
    output_file = Path("output/fixed_training_data.jsonl")
    output_file.parent.mkdir(exist_ok=True)
    written = write_jsonl(samples, output_file)
    print(f"Wrote {written} samples to {output_file}")


if __name__ == "__main__":
    main()