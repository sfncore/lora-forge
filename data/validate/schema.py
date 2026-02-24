"""Validate training data format against Axolotl's sharegpt expectations.

Usage:
    python -m data.validate.schema output/datasets/gastown_train.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

VALID_ROLES = {"system", "human", "gpt"}


def validate_sample(sample: dict, line_num: int) -> list[str]:
    """Validate a single training sample. Returns list of errors."""
    errors = []

    conversations = sample.get("conversations")
    if not isinstance(conversations, list):
        errors.append(f"line {line_num}: 'conversations' must be a list")
        return errors

    if len(conversations) < 2:
        errors.append(f"line {line_num}: need at least 2 conversation turns")
        return errors

    # Check first message is system.
    if conversations[0].get("from") != "system":
        errors.append(f"line {line_num}: first message must be 'system'")

    # Check alternation: after system, should alternate human/gpt.
    prev_role = "system"
    for i, msg in enumerate(conversations):
        from_role = msg.get("from")
        value = msg.get("value")

        if from_role not in VALID_ROLES:
            errors.append(f"line {line_num}, msg {i}: invalid role '{from_role}'")

        if not isinstance(value, str) or not value.strip():
            errors.append(f"line {line_num}, msg {i}: empty or non-string value")

        # Check alternation (after system).
        if i > 0:
            if prev_role == "human" and from_role != "gpt":
                errors.append(f"line {line_num}, msg {i}: expected 'gpt' after 'human', got '{from_role}'")
            elif prev_role == "gpt" and from_role != "human":
                errors.append(f"line {line_num}, msg {i}: expected 'human' after 'gpt', got '{from_role}'")
            elif prev_role == "system" and from_role != "human":
                errors.append(f"line {line_num}, msg {i}: expected 'human' after 'system', got '{from_role}'")

        prev_role = from_role

    # Must end with gpt.
    if conversations[-1].get("from") != "gpt":
        errors.append(f"line {line_num}: conversation must end with 'gpt' turn")

    return errors


def validate_file(path: Path) -> tuple[int, int, list[str]]:
    """Validate a JSONL file. Returns (total, valid, errors)."""
    total = 0
    valid = 0
    all_errors: list[str] = []

    with open(path, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            total += 1
            try:
                sample = json.loads(line)
            except json.JSONDecodeError as e:
                all_errors.append(f"line {line_num}: invalid JSON: {e}")
                continue

            errors = validate_sample(sample, line_num)
            if errors:
                all_errors.extend(errors)
            else:
                valid += 1

    return total, valid, all_errors


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m data.validate.schema <file.jsonl>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    total, valid, errors = validate_file(path)

    print(f"\nValidation: {path}")
    print(f"  Total samples: {total}")
    print(f"  Valid: {valid}")
    print(f"  Invalid: {total - valid}")

    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for err in errors[:20]:
            print(f"    {err}")
        if len(errors) > 20:
            print(f"    ... and {len(errors) - 20} more")
        sys.exit(1)
    else:
        print("  All samples valid.")


if __name__ == "__main__":
    main()
