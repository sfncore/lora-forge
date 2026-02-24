"""Validate training data against Gas Town CLI documentation.

Checks that training samples contain correct CLI command usage,
proper workflows, and expected command patterns for each role.

Usage:
    python -m data.validate.cli_validator output/datasets/gastown_train.jsonl
    python -m data.validate.cli_validator output/datasets/gastown_train.jsonl --report output/cli_validation_report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ValidationResult:
    """Result of validating a single sample."""
    line_num: int
    role: str
    session_id: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    commands_found: list[str] = field(default_factory=list)
    workflows_detected: list[str] = field(default_factory=list)
    is_valid: bool = True


# Valid Gas Town commands by category
GT_COMMANDS = {
    # Session & context
    "gt prime", "gt hook", "gt handoff",
    # Mail
    "gt mail inbox", "gt mail read", "gt mail send", "gt mail hook",
    # Work management
    "gt done", "gt escalate", "gt nudge", "gt peek",
    # Molecule management
    "gt mol status", "gt mol attach", "gt mol attach-from-mail",
    # Beads
    "bd ready", "bd show", "bd create", "bd close", "bd update",
    "bd dep add", "bd dep remove", "bd blocked",
    "bd mol current", "bd mol list",
    "bd query", "bd history",
    # Git
    "git status", "git add", "git commit", "git push", "git pull",
    "git log", "git branch", "git checkout",
}

# Role-specific expected commands
ROLE_COMMANDS = {
    "polecat": {
        "required": ["gt hook", "bd mol current", "gt done"],
        "expected": ["bd show", "bd update", "bd close", "git status", "git commit", "git push"],
        "optional": ["gt escalate", "gt mail send", "gt prime"],
    },
    "mayor": {
        "required": ["gt mail inbox", "gt mail send", "bd ready"],
        "expected": ["bd create", "bd dep add", "gt nudge", "gt peek"],
        "optional": ["gt prime", "bd show", "bd close"],
    },
    "deacon": {
        "required": ["gt hook", "bd ready"],
        "expected": ["bd show", "bd update", "gt mail send", "gt peek"],
        "optional": ["gt prime", "bd create"],
    },
    "witness": {
        "required": ["gt hook", "bd ready"],
        "expected": ["bd show", "bd update", "gt mail send", "gt nudge"],
        "optional": ["gt prime", "bd query"],
    },
    "refinery": {
        "required": ["gt hook"],
        "expected": ["git pull", "git merge", "git push", "bd close"],
        "optional": ["bd show", "gt mail send"],
    },
    "crew": {
        "required": ["gt hook", "bd mol current"],
        "expected": ["bd show", "bd update", "bd close"],
        "optional": ["gt escalate", "gt mail send"],
    },
}

# Workflow patterns (regex)
WORKFLOW_PATTERNS = {
    "polecat_startup": r"gt\s+(prime|hook).*bd\s+mol\s+current",
    "polecat_completion": r"git\s+(status|add|commit|push).*gt\s+done",
    "mail_workflow": r"gt\s+mail\s+(inbox|read|send)",
    "bead_lifecycle": r"bd\s+(show|update|close)",
    "git_commit_cycle": r"git\s+status.*git\s+add.*git\s+commit.*git\s+push",
    "escalation": r"gt\s+(escalate|mail\s+send.*(?:witness|mayor))",
    "molecule_workflow": r"bd\s+mol\s+current.*bd\s+close",
}

# Common anti-patterns (things that indicate bad training data)
ANTI_PATTERNS = {
    "wrong_git_workflow": r"git\s+push\s+origin\s+main",  # Polecats shouldn't push to main directly
    "bd_close_root": r"bd\s+close.*root",  # Shouldn't close root issue manually
    "waiting_for_approval": r"(wait.*approval|waiting.*human|ask.*confirmation)",
    "wrong_done_command": r"gt\s+(unsling|exit|quit)",  # Not real commands
}


def extract_commands(text: str) -> list[str]:
    """Extract Gas Town commands from text."""
    found = []
    
    # Match gt commands
    for match in re.finditer(r'gt\s+\w+(?:\s+\w+)*', text):
        cmd = match.group(0).strip()
        # Normalize multi-word commands
        if any(cmd.startswith(base) for base in ["gt mail", "gt mol", "gt handoff"]):
            found.append(cmd)
        else:
            # Take first two words for simple commands
            parts = cmd.split()
            if len(parts) >= 2:
                found.append(f"{parts[0]} {parts[1]}")
    
    # Match bd commands
    for match in re.finditer(r'bd\s+\w+(?:\s+\w+)*', text):
        cmd = match.group(0).strip()
        parts = cmd.split()
        if len(parts) >= 2:
            found.append(f"{parts[0]} {parts[1]}")
    
    # Match git commands
    for match in re.finditer(r'git\s+\w+(?:\s+[\w\-]+)*', text):
        cmd = match.group(0).strip()
        parts = cmd.split()
        if len(parts) >= 2:
            found.append(f"{parts[0]} {parts[1]}")
    
    return found


def detect_workflows(text: str) -> list[str]:
    """Detect workflow patterns in text."""
    detected = []
    for name, pattern in WORKFLOW_PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            detected.append(name)
    return detected


def detect_anti_patterns(text: str) -> list[str]:
    """Detect anti-patterns in text."""
    found = []
    for name, pattern in ANTI_PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            found.append(name)
    return found


def validate_sample(sample: dict, line_num: int) -> ValidationResult:
    """Validate a single training sample against CLI docs."""
    result = ValidationResult(
        line_num=line_num,
        role=sample.get("metadata", {}).get("role", "unknown"),
        session_id=sample.get("metadata", {}).get("session_id", "unknown"),
    )
    
    # Extract all conversation text
    text_parts = []
    for msg in sample.get("conversations", []):
        if isinstance(msg.get("value"), str):
            text_parts.append(msg["value"])
    full_text = "\n".join(text_parts)
    
    # Extract commands
    commands = extract_commands(full_text)
    result.commands_found = list(set(commands))
    
    # Detect workflows
    result.workflows_detected = detect_workflows(full_text)
    
    # Detect anti-patterns
    anti_patterns = detect_anti_patterns(full_text)
    for ap in anti_patterns:
        result.errors.append(f"Anti-pattern detected: {ap}")
        result.is_valid = False
    
    # Role-specific validation
    role = result.role
    if role in ROLE_COMMANDS:
        role_config = ROLE_COMMANDS[role]
        
        # Check for required commands
        has_required = any(
            any(req in cmd for cmd in commands)
            for req in role_config["required"]
        )
        if not has_required and commands:
            result.warnings.append(
                f"Role '{role}' missing required commands. "
                f"Expected one of: {role_config['required']}"
            )
    
    # Check for unknown commands (potential hallucinations)
    for cmd in commands:
        # Check if it's a known command pattern
        is_known = False
        for known in GT_COMMANDS:
            if cmd.startswith(known.split()[0]):
                is_known = True
                break
        
        if not is_known:
            # Could be a valid subcommand we don't know about, or a hallucination
            if cmd.startswith("gt ") or cmd.startswith("bd "):
                # Flag suspicious commands
                suspicious_patterns = ["gt tool", "gt run", "bd exec", "bd shell"]
                if any(cmd.startswith(p) for p in suspicious_patterns):
                    result.warnings.append(f"Possibly hallucinated command: {cmd}")
    
    # Check conversation structure for command-response pairs
    conversations = sample.get("conversations", [])
    for i, msg in enumerate(conversations):
        if msg.get("from") == "human":
            value = msg.get("value", "")
            # Check if human message contains commands (should be rare)
            human_commands = extract_commands(value)
            if len(human_commands) > 2:
                result.warnings.append(
                    f"Human message at turn {i} contains many commands "
                    f"(may indicate incorrect role assignment)"
                )
    
    return result


def validate_file(path: Path) -> tuple[list[ValidationResult], dict]:
    """Validate a JSONL file. Returns (results, summary_stats)."""
    results = []
    stats = {
        "total_samples": 0,
        "valid_samples": 0,
        "invalid_samples": 0,
        "total_errors": 0,
        "total_warnings": 0,
        "role_distribution": Counter(),
        "command_frequency": Counter(),
        "workflow_frequency": Counter(),
        "anti_pattern_frequency": Counter(),
    }
    
    with open(path, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            stats["total_samples"] += 1
            
            try:
                sample = json.loads(line)
            except json.JSONDecodeError as e:
                results.append(ValidationResult(
                    line_num=line_num,
                    role="unknown",
                    session_id="unknown",
                    errors=[f"Invalid JSON: {e}"],
                    is_valid=False,
                ))
                stats["invalid_samples"] += 1
                stats["total_errors"] += 1
                continue
            
            result = validate_sample(sample, line_num)
            results.append(result)
            
            # Update stats
            stats["role_distribution"][result.role] += 1
            
            for cmd in result.commands_found:
                stats["command_frequency"][cmd] += 1
            
            for wf in result.workflows_detected:
                stats["workflow_frequency"][wf] += 1
            
            if result.is_valid:
                stats["valid_samples"] += 1
            else:
                stats["invalid_samples"] += 1
            
            stats["total_errors"] += len(result.errors)
            stats["total_warnings"] += len(result.warnings)
    
    # Convert Counters to dicts for JSON serialization
    stats["role_distribution"] = dict(stats["role_distribution"])
    stats["command_frequency"] = dict(stats["command_frequency"].most_common(30))
    stats["workflow_frequency"] = dict(stats["workflow_frequency"])
    stats["anti_pattern_frequency"] = dict(stats["anti_pattern_frequency"])
    
    return results, stats


def print_report(results: list[ValidationResult], stats: dict, path: Path) -> None:
    """Print validation report to console."""
    print(f"\n{'='*60}")
    print(f"CLI Validation Report: {path.name}")
    print(f"{'='*60}\n")
    
    # Summary
    print("SUMMARY")
    print(f"  Total samples:     {stats['total_samples']}")
    print(f"  Valid samples:     {stats['valid_samples']} ({stats['valid_samples']/max(stats['total_samples'],1)*100:.1f}%)")
    print(f"  Invalid samples:   {stats['invalid_samples']}")
    print(f"  Total errors:      {stats['total_errors']}")
    print(f"  Total warnings:    {stats['total_warnings']}\n")
    
    # Role distribution
    print("ROLE DISTRIBUTION")
    for role, count in sorted(stats["role_distribution"].items()):
        pct = count / max(stats["total_samples"], 1) * 100
        print(f"  {role}: {count} ({pct:.1f}%)")
    print()
    
    # Top commands
    print("TOP COMMANDS (by frequency)")
    for cmd, count in list(stats["command_frequency"].items())[:15]:
        print(f"  {cmd}: {count}")
    print()
    
    # Workflows detected
    print("WORKFLOWS DETECTED")
    for wf, count in sorted(stats["workflow_frequency"].items(), key=lambda x: -x[1]):
        print(f"  {wf}: {count}")
    print()
    
    # Errors (sample)
    error_results = [r for r in results if r.errors]
    if error_results:
        print("ERRORS (showing first 10)")
        for r in error_results[:10]:
            print(f"  Line {r.line_num} ({r.role}):")
            for err in r.errors:
                print(f"    - {err}")
        if len(error_results) > 10:
            print(f"  ... and {len(error_results) - 10} more samples with errors")
        print()
    
    # Warnings (sample)
    warning_results = [r for r in results if r.warnings and not r.errors]
    if warning_results:
        print("WARNINGS (showing first 10)")
        for r in warning_results[:10]:
            print(f"  Line {r.line_num} ({r.role}):")
            for warn in r.warnings:
                print(f"    - {warn}")
        if len(warning_results) > 10:
            print(f"  ... and {len(warning_results) - 10} more samples with warnings")
        print()


def save_json_report(stats: dict, output_path: Path) -> None:
    """Save detailed report as JSON."""
    report = {
        "summary": {
            "total_samples": stats["total_samples"],
            "valid_samples": stats["valid_samples"],
            "invalid_samples": stats["invalid_samples"],
            "total_errors": stats["total_errors"],
            "total_warnings": stats["total_warnings"],
            "validity_rate": stats["valid_samples"] / max(stats["total_samples"], 1),
        },
        "role_distribution": stats["role_distribution"],
        "command_frequency": stats["command_frequency"],
        "workflow_frequency": stats["workflow_frequency"],
        "anti_pattern_frequency": stats["anti_pattern_frequency"],
    }
    
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\nDetailed report saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Validate training data against Gas Town CLI documentation"
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Input JSONL file to validate"
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Output path for JSON report (optional)"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with error code if any validation errors found"
    )
    args = parser.parse_args()
    
    if not args.input_file.exists():
        print(f"File not found: {args.input_file}")
        sys.exit(1)
    
    results, stats = validate_file(args.input_file)
    print_report(results, stats, args.input_file)
    
    if args.report:
        save_json_report(stats, args.report)
    
    # Exit code
    if args.strict and stats["invalid_samples"] > 0:
        print(f"\n❌ Validation failed: {stats['invalid_samples']} invalid samples")
        sys.exit(1)
    elif stats["invalid_samples"] > 0:
        print(f"\n⚠️  Warning: {stats['invalid_samples']} samples have validation errors")
    else:
        print(f"\n✓ All samples passed CLI validation")
    
    sys.exit(0 if stats["invalid_samples"] == 0 else 1)


if __name__ == "__main__":
    main()
