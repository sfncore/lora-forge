"""Pipeline orchestrator: extract → transform → validate.

Usage:
    python -m data.pipeline                          # Full pipeline
    python -m data.pipeline --step extract           # Extract only
    python -m data.pipeline --step transform         # Transform only
    python -m data.pipeline --sessions-dir ~/.claude/projects  # Custom source
    python -m data.pipeline --output-dir output/datasets       # Custom output
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from data.extract.sessions import ExtractedSession, discover_sessions, extract_session
from data.transform.chat_formatter import append_jsonl, format_sharegpt
from data.transform.chunker import Chunk, chunk_turns
from data.transform.deduplicator import deduplicate
from data.transform.quality_filter import assess_turns
from data.transform.role_tagger import tag_role
from data.transform.secret_scrubber import scrub_sample
from data.transform.tool_normalizer import normalize_turn_content

logger = logging.getLogger(__name__)

DEFAULT_SESSIONS_DIR = Path.home() / ".claude" / "projects"
DEFAULT_OUTPUT_DIR = Path("output") / "datasets"


def extract_all(sessions_dir: Path) -> list[ExtractedSession]:
    """Extract all Gas Town sessions from the Claude projects directory."""
    session_files = discover_sessions(sessions_dir)
    logger.info("Discovered %d session files", len(session_files))

    sessions: list[ExtractedSession] = []
    for i, path in enumerate(session_files):
        if i % 50 == 0:
            logger.info("  Extracting %d/%d...", i, len(session_files))

        session = extract_session(path)
        if session:
            sessions.append(session)

    logger.info("Extracted %d sessions with data (from %d files)", len(sessions), len(session_files))
    return sessions


def transform_session(session: ExtractedSession) -> list[dict]:
    """Transform an extracted session into training samples.

    Pipeline: role tag → tool normalize → chunk → quality filter → format
    """
    # 1. Determine role.
    first_user_content = ""
    for turn in session.turns:
        if turn.role == "user":
            first_user_content = turn.content
            break
    role = tag_role(Path(session.source_path), first_user_content)

    # 2. Normalize tool results in each turn.
    for turn in session.turns:
        turn.content = normalize_turn_content(turn.content)

    # 3. Chunk long sessions.
    chunks = chunk_turns(session.turns)

    # 4. Quality filter and format each chunk.
    samples = []
    for chunk in chunks:
        quality = assess_turns(chunk.turns)
        if not quality.keep:
            continue

        sample = format_sharegpt(
            turns=chunk.turns,
            role=role,
            session_id=session.session_id,
            chunk_index=chunk.chunk_index,
            quality_score=quality.score,
        )

        # Only keep samples with at least one human and one gpt message.
        roles_present = {msg["from"] for msg in sample["conversations"]}
        if "human" in roles_present and "gpt" in roles_present:
            samples.append(sample)

    return samples


def run_pipeline(
    sessions_dir: Path = DEFAULT_SESSIONS_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    step: str = "all",
) -> dict:
    """Run the full pipeline or a specific step.

    Returns statistics about the pipeline run.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stats: dict = {}

    # Step 1: Extract.
    raw_path = output_dir / "raw_sessions.jsonl"
    if step in ("all", "extract"):
        sessions = extract_all(sessions_dir)
        stats["sessions_extracted"] = len(sessions)
        stats["total_turns"] = sum(len(s.turns) for s in sessions)

        # Save raw extractions for debugging.
        with open(raw_path, "w") as f:
            for s in sessions:
                record = {
                    "session_id": s.session_id,
                    "source_path": s.source_path,
                    "num_turns": len(s.turns),
                    "metadata": s.metadata,
                }
                f.write(json.dumps(record) + "\n")

        logger.info("Extracted %d sessions, %d total turns", stats["sessions_extracted"], stats["total_turns"])
    else:
        sessions = []

    # Step 2: Transform.
    if step in ("all", "transform"):
        if not sessions:
            # Re-extract if transform-only.
            sessions = extract_all(sessions_dir)

        all_samples: list[dict] = []
        role_counts: dict[str, int] = {}

        for session in sessions:
            samples = transform_session(session)
            for sample in samples:
                role = sample.get("metadata", {}).get("role", "unknown")
                role_counts[role] = role_counts.get(role, 0) + 1
            all_samples.extend(samples)

        logger.info("Generated %d samples before dedup", len(all_samples))

        # Scrub secrets from all samples.
        total_secrets = 0
        for sample in all_samples:
            _, count = scrub_sample(sample)
            total_secrets += count
        if total_secrets:
            logger.info("Scrubbed %d secrets from training data", total_secrets)
        stats["secrets_scrubbed"] = total_secrets

        # Deduplicate.
        before_dedup = len(all_samples)
        all_samples = deduplicate(all_samples)
        stats["samples_before_dedup"] = before_dedup
        stats["samples_after_dedup"] = len(all_samples)
        stats["duplicates_removed"] = before_dedup - len(all_samples)
        stats["role_distribution"] = role_counts

        # Split into train/val (95/5).
        val_size = max(1, len(all_samples) // 20)
        val_samples = all_samples[:val_size]
        train_samples = all_samples[val_size:]

        # Write output.
        train_path = output_dir / "gastown_train.jsonl"
        val_path = output_dir / "gastown_val.jsonl"

        with open(train_path, "w") as f:
            for sample in train_samples:
                append_jsonl(sample, f)

        with open(val_path, "w") as f:
            for sample in val_samples:
                append_jsonl(sample, f)

        stats["train_samples"] = len(train_samples)
        stats["val_samples"] = len(val_samples)
        stats["train_path"] = str(train_path)
        stats["val_path"] = str(val_path)

        logger.info(
            "Wrote %d train + %d val samples (removed %d duplicates)",
            len(train_samples),
            len(val_samples),
            stats["duplicates_removed"],
        )

    return stats


def main():
    parser = argparse.ArgumentParser(description="Gas Town LoRA training data pipeline")
    parser.add_argument("--sessions-dir", type=Path, default=DEFAULT_SESSIONS_DIR, help="Claude projects directory")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory for datasets")
    parser.add_argument("--step", choices=["all", "extract", "transform"], default="all", help="Pipeline step to run")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    stats = run_pipeline(
        sessions_dir=args.sessions_dir,
        output_dir=args.output_dir,
        step=args.step,
    )

    print("\n--- Pipeline Statistics ---")
    for key, value in sorted(stats.items()):
        if isinstance(value, dict):
            print(f"  {key}:")
            for k, v in sorted(value.items()):
                print(f"    {k}: {v}")
        else:
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
