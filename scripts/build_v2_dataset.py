#!/usr/bin/env python3
"""
Build v2 training dataset for deacon/witness LoRA adapters.

Combines:
1. Synthetic scenario examples (from synthetic_scenarios.py) — targeted decision coverage
2. Existing decision-focused training data (optional)

Converts synthetic examples from flat list format → ShareGPT format
(conversations with from/value fields) for Axolotl.

Usage:
    cd /home/ubuntu/gt/loraforge/mayor/rig
    python scripts/build_v2_dataset.py --role deacon --n-synthetic 300 --output output/datasets/deacon_v2.jsonl
    python scripts/build_v2_dataset.py --role witness --n-synthetic 300 --output output/datasets/witness_v2.jsonl
"""

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from synthetic_scenarios import generate_examples

DEACON_SYSTEM = """[GAS TOWN ROLE: deacon]
You are the Deacon, an autonomous patrol and coordination agent. You monitor system health, manage patrol cycles, dispatch work to polecats, and maintain the beads database. You operate without human prompting.

Respond with ONE JSON tool call:
{"tool": "<tool_name>", "args": {<arguments>}}

If no action is needed: {"tool": "none", "args": {}}

Available tools: gt_polecat_list, gt_polecat_nuke, gt_peek, gt_session_status, gt_nudge, gt_mail_inbox, gt_mail_read, gt_mail_send, gt_patrol_report, gt_handoff, gt_escalate, bd_show, bd_list, bd_close, bd_children, check_git_state, check_tmux_session, bash, none"""

WITNESS_SYSTEM = """You are a Witness agent. You respond ONLY with JSON tool calls.

For each turn, output exactly one JSON object:
{"tool": "<tool_name>", "args": {<arguments>}}

If no action is needed, output:
{"tool": "none", "args": {}}

Available tools: gt_polecat_list, gt_polecat_nuke, gt_peek, gt_session_status, gt_nudge, gt_mail_inbox, gt_mail_read, gt_mail_send, gt_patrol_report, gt_handoff, gt_escalate, bd_show, bd_list, bd_close, bd_children, check_git_state, check_tmux_session, bash"""


def flat_to_sharegpt(flat_example: list, system_override: str | None = None) -> dict:
    """
    Convert flat [{"role":..,"content":..}] to ShareGPT format.

    ShareGPT format: {"conversations": [{"from": "system", "value": "..."}, ...]}
    Role mapping: system→system, user→human, assistant→gpt
    """
    role_map = {"system": "system", "user": "human", "assistant": "gpt"}
    conversations = []
    for msg in flat_example:
        role = role_map.get(msg["role"], msg["role"])
        content = msg["content"]
        if role == "system" and system_override:
            content = system_override
        conversations.append({"from": role, "value": content})
    return {"conversations": conversations}


def load_existing(path: str) -> list:
    """Load existing JSONL training data."""
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["deacon", "witness"], default="deacon")
    parser.add_argument("--n-synthetic", type=int, default=300,
                        help="Number of synthetic scenario examples to generate")
    parser.add_argument("--scenario-format", choices=["legacy", "rich", "both"], default="both",
                        help="Scenario format: legacy (short), rich (snapshot), both")
    parser.add_argument("--existing", type=str, default=None,
                        help="Path to existing training data to merge (optional)")
    parser.add_argument("--output", type=str, required=True,
                        help="Output JSONL path")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    system_prompt = DEACON_SYSTEM if args.role == "deacon" else WITNESS_SYSTEM

    # Generate synthetic examples
    print(f"Generating {args.n_synthetic} synthetic examples (format={args.scenario_format})...")
    raw_examples = generate_examples(args.n_synthetic, args.seed, fmt=args.scenario_format)
    synthetic = [flat_to_sharegpt(ex, system_override=system_prompt) for ex in raw_examples]
    print(f"  Generated: {len(synthetic)} synthetic examples")

    # Tool distribution
    from collections import Counter
    tool_counts = Counter()
    for ex in synthetic:
        assistant_turn = next((c for c in ex["conversations"] if c["from"] == "gpt"), None)
        if assistant_turn:
            try:
                tool = json.loads(assistant_turn["value"]).get("tool", "?")
                tool_counts[tool] += 1
            except Exception:
                pass

    print(f"\n  Tool distribution (synthetic):")
    for tool, count in tool_counts.most_common():
        print(f"    {tool:30s} {count:4d} ({count/len(synthetic)*100:.1f}%)")

    # Load and merge existing data
    existing = []
    if args.existing:
        existing = load_existing(args.existing)
        print(f"\n  Existing examples: {len(existing)}")
    elif args.role == "deacon":
        default_path = "output/datasets/deacon_train.jsonl"
        if os.path.exists(default_path):
            existing = load_existing(default_path)
            print(f"\n  Auto-loaded existing deacon data: {len(existing)} examples from {default_path}")
    elif args.role == "witness":
        default_path = "output/datasets/witness_train.jsonl"
        if os.path.exists(default_path):
            existing = load_existing(default_path)
            print(f"\n  Auto-loaded existing witness data: {len(existing)} examples from {default_path}")

    # Combine and shuffle
    combined = existing + synthetic
    rng = random.Random(args.seed)
    rng.shuffle(combined)

    print(f"\n  Total combined: {len(combined)} examples")
    print(f"  Breakdown: {len(existing)} existing + {len(synthetic)} synthetic")

    # Write output
    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)
    with open(args.output, "w") as f:
        for ex in combined:
            f.write(json.dumps(ex) + "\n")

    print(f"\nWritten to {args.output}")

    # Show a sample synthetic example
    sample = next((ex for ex in synthetic[:5]
                   if any(c["from"] == "gpt" and '"tool":' in c["value"]
                          and '"none"' not in c["value"]
                          for c in ex["conversations"])), synthetic[0])
    user = next(c for c in sample["conversations"] if c["from"] == "human")["value"]
    asst = next(c for c in sample["conversations"] if c["from"] == "gpt")["value"]
    print(f"\nSample synthetic example:")
    print(f"  User:      {user[:100].replace(chr(10), ' ')}")
    print(f"  Assistant: {asst[:100]}")


if __name__ == "__main__":
    main()
