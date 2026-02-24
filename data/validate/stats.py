"""Print dataset statistics for a training JSONL file.

Usage:
    python -m data.validate.stats output/datasets/gastown_train.jsonl
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def compute_stats(path: Path) -> dict:
    """Compute statistics for a training JSONL file."""
    total = 0
    role_counts: Counter = Counter()
    turn_counts: list[int] = []
    char_counts: list[int] = []
    quality_scores: list[float] = []
    tool_call_samples = 0
    source_counts: Counter = Counter()

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            sample = json.loads(line)
            total += 1

            meta = sample.get("metadata", {})
            role = meta.get("role", "unknown")
            role_counts[role] += 1

            score = meta.get("quality_score", 0.0)
            if score:
                quality_scores.append(score)

            source = meta.get("source", "unknown")
            source_counts[source] += 1

            conversations = sample.get("conversations", [])
            # Count non-system turns.
            turns = [m for m in conversations if m.get("from") != "system"]
            turn_counts.append(len(turns))

            total_chars = sum(len(m.get("value", "")) for m in conversations)
            char_counts.append(total_chars)

            # Check for tool calls.
            for msg in conversations:
                if msg.get("from") == "gpt" and "<tool_call" in msg.get("value", ""):
                    tool_call_samples += 1
                    break

    return {
        "total_samples": total,
        "role_distribution": dict(role_counts.most_common()),
        "source_distribution": dict(source_counts.most_common()),
        "turns_per_sample": {
            "min": min(turn_counts) if turn_counts else 0,
            "max": max(turn_counts) if turn_counts else 0,
            "mean": round(sum(turn_counts) / max(len(turn_counts), 1), 1),
            "median": sorted(turn_counts)[len(turn_counts) // 2] if turn_counts else 0,
        },
        "chars_per_sample": {
            "min": min(char_counts) if char_counts else 0,
            "max": max(char_counts) if char_counts else 0,
            "mean": round(sum(char_counts) / max(len(char_counts), 1), 0),
            "total_mb": round(sum(char_counts) / 1_000_000, 2),
        },
        "approx_tokens_per_sample": {
            "mean": round(sum(char_counts) / max(len(char_counts), 1) / 4, 0),
        },
        "quality_score": {
            "min": round(min(quality_scores), 3) if quality_scores else 0,
            "max": round(max(quality_scores), 3) if quality_scores else 0,
            "mean": round(sum(quality_scores) / max(len(quality_scores), 1), 3),
        },
        "samples_with_tool_calls": tool_call_samples,
        "tool_call_ratio": round(tool_call_samples / max(total, 1), 3),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m data.validate.stats <file.jsonl>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    stats = compute_stats(path)

    print(f"\n--- Dataset Statistics: {path.name} ---\n")
    for key, value in stats.items():
        if isinstance(value, dict):
            print(f"  {key}:")
            for k, v in value.items():
                print(f"    {k}: {v}")
        else:
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
