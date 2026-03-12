#!/usr/bin/env python3
"""
Build v3 training dataset for deacon/witness LoRA adapters.

V3 improvements over V2:
1. Synthetic-ONLY (no real session data with mismatched XML tool format)
2. Compact training system prompt (~400 tokens vs 3400 tokens for full gt prime)
   Full gt prime prompt causes OOM with sequence_len=2048; at inference it is injected normally
3. 750 examples (2.5x more than v2's 300 synthetic)
4. Clear tool format instruction in system prompt

Usage:
    cd /home/ubuntu/gt/loraforge/mayor/rig
    python scripts/build_v3_dataset.py --role deacon --output output/datasets/deacon_v3.jsonl
    python scripts/build_v3_dataset.py --role witness --output output/datasets/witness_v3.jsonl
"""

import argparse
import json
import os
import random
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from synthetic_scenarios import generate_examples

# Load real gt prime system prompts
_PROMPTS_FILE = Path(__file__).parent.parent / "data/transform/gt_prime_prompts.json"

def _load_system_prompt(role: str) -> str:
    """Load the real gt prime system prompt for the given role.

    V4: Use the full gt prime prompt (sequence_len=4096 gives enough room).
    Training with the actual runtime prompt eliminates train/inference mismatch.
    """
    if _PROMPTS_FILE.exists():
        with open(_PROMPTS_FILE) as f:
            all_prompts = json.load(f)
        if role in all_prompts:
            return all_prompts[role]

    raise FileNotFoundError(
        f"gt prime prompt not found for role '{role}'. "
        f"Run: python scripts/refresh_gt_prime_prompts.py"
    )
    return prompts.get(role, f"[GAS TOWN ROLE: {role}]\nYou are a Gas Town agent.")


def flat_to_sharegpt(flat_example: list, system_prompt: str) -> dict:
    """Convert flat [{"role":..,"content":..}] to ShareGPT format."""
    role_map = {"system": "system", "user": "human", "assistant": "gpt"}
    conversations = []
    for msg in flat_example:
        role = role_map.get(msg["role"], msg["role"])
        content = msg["content"]
        if role == "system":
            content = system_prompt
        conversations.append({"from": role, "value": content})
    return {"conversations": conversations}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["deacon", "witness"], default="deacon")
    parser.add_argument("--n-synthetic", type=int, default=750,
                        help="Number of synthetic scenario examples (default 750)")
    parser.add_argument("--scenario-format", choices=["legacy", "rich", "both"], default="both")
    parser.add_argument("--output", type=str, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    system_prompt = _load_system_prompt(args.role)
    print(f"System prompt: {len(system_prompt)} chars (role: {args.role})")
    print(f"Generating {args.n_synthetic} synthetic examples...")

    raw_examples = generate_examples(args.n_synthetic, args.seed, fmt=args.scenario_format)
    examples = [flat_to_sharegpt(ex, system_prompt) for ex in raw_examples]
    print(f"  Generated: {len(examples)} examples")

    # Show tool distribution
    tool_counts = Counter()
    for ex in examples:
        for c in ex["conversations"]:
            if c["from"] == "gpt":
                try:
                    tool = json.loads(c["value"]).get("tool", "?")
                    tool_counts[tool] += 1
                except Exception:
                    tool_counts["_unparsed"] += 1

    total = sum(tool_counts.values())
    print(f"\nTool distribution ({total} total assistant turns):")
    for tool, count in tool_counts.most_common():
        print(f"  {tool:35s} {count:4d} ({count/total*100:.1f}%)")

    # Shuffle
    rng = random.Random(args.seed)
    rng.shuffle(examples)

    # Write output
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")

    print(f"\nWritten {len(examples)} examples to {args.output}")

    # Show sample
    sample = next(
        (ex for ex in examples[:10]
         if any(c["from"] == "gpt" and '"tool"' in c["value"] and '"none"' not in c["value"]
                for c in ex["conversations"])),
        examples[0]
    )
    user = next(c for c in sample["conversations"] if c["from"] == "human")["value"]
    asst = next(c for c in sample["conversations"] if c["from"] == "gpt")["value"]
    print(f"\nSample:")
    print(f"  User:  {user[:120].replace(chr(10), ' ')}")
    print(f"  Asst:  {asst[:120]}")


if __name__ == "__main__":
    main()
