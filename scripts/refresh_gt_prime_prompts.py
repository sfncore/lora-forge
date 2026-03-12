#!/usr/bin/env python3
"""
Capture gt prime output for all Gas Town roles and save to
data/transform/gt_prime_prompts.json for use as training system prompts.

Run from the rig root:
    python scripts/refresh_gt_prime_prompts.py
"""

import json
import os
import subprocess
from pathlib import Path

ROLES = ["mayor", "deacon", "boot", "witness", "refinery", "polecat", "crew"]
OUTPUT = Path("data/transform/gt_prime_prompts.json")


def capture_gt_prime(role: str) -> str:
    result = subprocess.run(
        ["gt", "prime"],
        env={**os.environ, "GT_ROLE": role},
        capture_output=True, text=True,
    )
    lines = result.stdout.splitlines()
    # Skip mismatch warning lines and the dynamic [GAS TOWN] role:... pid:... session:... header
    start = next((i for i, l in enumerate(lines) if l.startswith("[GAS TOWN]")), 0)
    content = "\n".join(lines[start + 1:]).strip()
    return content


def main():
    prompts = {}
    for role in ROLES:
        content = capture_gt_prime(role)
        prompts[role] = content
        print(f"  {role:12s} {len(content):6d} chars  ({content.splitlines()[0][:50]})")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(prompts, f, indent=2)
    print(f"\nSaved {len(prompts)} role prompts to {OUTPUT}")


if __name__ == "__main__":
    main()
