"""Gas Town role-specific evaluation benchmarks.

Evaluates a fine-tuned model against role-specific scenarios.
Each scenario has a system prompt, user prompt, and expected behaviors.

Usage:
    python -m eval.role_bench --scenarios eval/prompts/mayor_scenarios.jsonl
    python -m eval.role_bench --scenarios eval/prompts/ --all-roles
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def load_scenarios(path: Path) -> list[dict]:
    """Load evaluation scenarios from a JSONL file or directory."""
    scenarios = []
    paths = list(path.glob("*.jsonl")) if path.is_dir() else [path]

    for p in paths:
        with open(p) as f:
            for line in f:
                line = line.strip()
                if line:
                    scenarios.append(json.loads(line))

    return scenarios


def score_response(response: str, expected_behaviors: list[str]) -> dict:
    """Score a model response against expected behaviors.

    Returns a dict with per-behavior matches and overall score.
    """
    results = {}
    matched = 0

    for behavior in expected_behaviors:
        # Simple keyword/pattern matching for v1.
        # Future: use an LLM judge for semantic matching.
        pattern = _behavior_to_pattern(behavior)
        found = bool(re.search(pattern, response, re.IGNORECASE | re.DOTALL))
        results[behavior] = found
        if found:
            matched += 1

    return {
        "behaviors": results,
        "matched": matched,
        "total": len(expected_behaviors),
        "score": matched / max(len(expected_behaviors), 1),
    }


def _behavior_to_pattern(behavior: str) -> str:
    """Convert an expected behavior description to a regex pattern.

    Maps natural language behaviors to patterns that match tool calls
    and text in the response.
    """
    # Common Gas Town command patterns.
    command_patterns = {
        "runs gt hook": r"gt hook",
        "runs gt mail inbox": r"gt mail inbox",
        "runs gt mail read": r"gt mail read",
        "runs gt prime": r"gt prime",
        "runs bd create": r"bd create",
        "runs bd close": r"bd close",
        "runs git status": r"git status",
        "runs git commit": r"git commit",
        "runs git push": r"git push",
        "checks hook": r"gt hook",
        "checks mail": r"gt mail",
    }

    for key, pattern in command_patterns.items():
        if key in behavior.lower():
            return pattern

    # Fallback: use the behavior text as a loose pattern.
    words = behavior.lower().split()
    return r".*".join(re.escape(w) for w in words[:3])


def print_report(results: list[dict]) -> None:
    """Print evaluation results summary."""
    total_scenarios = len(results)
    total_score = sum(r["score"]["score"] for r in results)
    avg_score = total_score / max(total_scenarios, 1)

    print(f"\n--- Evaluation Report ---")
    print(f"Scenarios: {total_scenarios}")
    print(f"Average score: {avg_score:.1%}")
    print()

    by_role: dict[str, list[float]] = {}
    for r in results:
        role = r.get("role", "unknown")
        by_role.setdefault(role, []).append(r["score"]["score"])

    for role, scores in sorted(by_role.items()):
        avg = sum(scores) / len(scores)
        print(f"  {role}: {avg:.1%} ({len(scores)} scenarios)")


def main():
    parser = argparse.ArgumentParser(description="Gas Town role evaluation")
    parser.add_argument("--scenarios", type=Path, required=True, help="Scenarios JSONL file or directory")
    args = parser.parse_args()

    scenarios = load_scenarios(args.scenarios)
    if not scenarios:
        print("No scenarios found")
        sys.exit(1)

    print(f"Loaded {len(scenarios)} evaluation scenarios")
    print("Note: actual model inference not implemented yet.")
    print("This framework scores responses against expected behaviors.")


if __name__ == "__main__":
    main()
