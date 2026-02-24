"""Generate comprehensive reports for training data quality and coverage.

Produces detailed reports about:
- Dataset statistics and distributions
- Role coverage and balance
- Command usage patterns
- Quality score distributions
- Workflow coverage
- Gaps and recommendations

Usage:
    python -m data.validate.reporter output/datasets/gastown_train.jsonl
    python -m data.validate.reporter output/datasets/gastown_train.jsonl --output output/report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class DatasetReport:
    """Comprehensive dataset report."""
    path: str
    generated_at: str
    total_samples: int
    total_chars: int
    approx_tokens: int
    
    # Distributions
    role_distribution: dict[str, int] = field(default_factory=dict)
    source_distribution: dict[str, int] = field(default_factory=dict)
    quality_score_stats: dict[str, float] = field(default_factory=dict)
    
    # Conversation stats
    turns_per_sample: dict[str, float] = field(default_factory=dict)
    chars_per_sample: dict[str, float] = field(default_factory=dict)
    
    # Content analysis
    command_coverage: dict[str, Any] = field(default_factory=dict)
    workflow_coverage: dict[str, int] = field(default_factory=dict)
    tool_call_stats: dict[str, Any] = field(default_factory=dict)
    
    # Quality flags
    potential_issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def compute_turn_stats(conversations: list[dict]) -> dict:
    """Compute statistics for a conversation."""
    non_system = [m for m in conversations if m.get("from") != "system"]
    turns = len(non_system)
    chars = sum(len(m.get("value", "")) for m in conversations)
    
    # Count tool calls
    tool_calls = 0
    for msg in conversations:
        if msg.get("from") == "gpt" and "<tool_call" in msg.get("value", ""):
            tool_calls += 1
    
    return {
        "turns": turns,
        "chars": chars,
        "tool_calls": tool_calls,
    }


def analyze_commands(text: str) -> dict:
    """Analyze command usage in text."""
    import re
    
    commands = {
        "gt_commands": [],
        "bd_commands": [],
        "git_commands": [],
    }
    
    # Extract gt commands
    for match in re.finditer(r'gt\s+(\w+)(?:\s+(\w+))?', text):
        cmd = f"gt {match.group(1)}"
        if match.group(2):
            cmd = f"gt {match.group(1)} {match.group(2)}"
        commands["gt_commands"].append(cmd)
    
    # Extract bd commands
    for match in re.finditer(r'bd\s+(\w+)(?:\s+(\w+))?', text):
        cmd = f"bd {match.group(1)}"
        if match.group(2):
            cmd = f"bd {match.group(1)} {match.group(2)}"
        commands["bd_commands"].append(cmd)
    
    # Extract git commands
    for match in re.finditer(r'git\s+(\w+)', text):
        commands["git_commands"].append(f"git {match.group(1)}")
    
    # Deduplicate
    for key in commands:
        commands[key] = list(set(commands[key]))
    
    return commands


def generate_report(path: Path) -> DatasetReport:
    """Generate comprehensive report for a dataset."""
    report = DatasetReport(
        path=str(path),
        generated_at=datetime.now().isoformat(),
        total_samples=0,
        total_chars=0,
        approx_tokens=0,
    )
    
    role_counts: Counter = Counter()
    source_counts: Counter = Counter()
    quality_scores: list[float] = []
    turn_counts: list[int] = []
    char_counts: list[int] = []
    tool_call_samples = 0
    total_tool_calls = 0
    
    command_frequency: Counter = Counter()
    workflow_patterns: Counter = Counter()
    
    # Workflow pattern definitions
    workflows = {
        "polecat_complete": ["gt hook", "bd mol current", "gt done"],
        "mail_workflow": ["gt mail inbox", "gt mail read", "gt mail send"],
        "bead_lifecycle": ["bd show", "bd update", "bd close"],
        "git_cycle": ["git status", "git add", "git commit", "git push"],
        "escalation": ["gt escalate", "gt mail send"],
    }
    
    issues: list[str] = []
    
    with open(path, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            report.total_samples += 1
            
            try:
                sample = json.loads(line)
            except json.JSONDecodeError:
                issues.append(f"Line {line_num}: Invalid JSON")
                continue
            
            conversations = sample.get("conversations", [])
            metadata = sample.get("metadata", {})
            
            # Extract text
            full_text = "\n".join(m.get("value", "") for m in conversations)
            
            # Basic stats
            turn_stats = compute_turn_stats(conversations)
            turn_counts.append(turn_stats["turns"])
            char_counts.append(turn_stats["chars"])
            report.total_chars += turn_stats["chars"]
            
            if turn_stats["tool_calls"] > 0:
                tool_call_samples += 1
                total_tool_calls += turn_stats["tool_calls"]
            
            # Role and source
            role = metadata.get("role", "unknown")
            source = metadata.get("source", "unknown")
            role_counts[role] += 1
            source_counts[source] += 1
            
            # Quality score
            score = metadata.get("quality_score", 0.0)
            if score:
                quality_scores.append(score)
            
            # Command analysis
            commands = analyze_commands(full_text)
            for cmd_list in commands.values():
                for cmd in cmd_list:
                    command_frequency[cmd] += 1
            
            # Workflow detection
            for wf_name, wf_commands in workflows.items():
                if any(cmd in full_text for cmd in wf_commands):
                    workflow_patterns[wf_name] += 1
    
    # Compute statistics
    report.role_distribution = dict(role_counts.most_common())
    report.source_distribution = dict(source_counts.most_common())
    
    if quality_scores:
        report.quality_score_stats = {
            "min": round(min(quality_scores), 3),
            "max": round(max(quality_scores), 3),
            "mean": round(sum(quality_scores) / len(quality_scores), 3),
            "median": round(sorted(quality_scores)[len(quality_scores) // 2], 3),
        }
    
    if turn_counts:
        sorted_turns = sorted(turn_counts)
        report.turns_per_sample = {
            "min": min(turn_counts),
            "max": max(turn_counts),
            "mean": round(sum(turn_counts) / len(turn_counts), 1),
            "median": sorted_turns[len(turn_counts) // 2],
        }
    
    if char_counts:
        report.chars_per_sample = {
            "min": min(char_counts),
            "max": max(char_counts),
            "mean": round(sum(char_counts) / len(char_counts), 0),
            "total_mb": round(sum(char_counts) / 1_000_000, 2),
        }
    
    report.approx_tokens = report.total_chars // 4
    
    # Command coverage
    top_commands = command_frequency.most_common(50)
    report.command_coverage = {
        "unique_commands": len(command_frequency),
        "top_commands": dict(top_commands),
        "by_type": {
            "gt": len([c for c in command_frequency if c.startswith("gt ")]),
            "bd": len([c for c in command_frequency if c.startswith("bd ")]),
            "git": len([c for c in command_frequency if c.startswith("git ")]),
        }
    }
    
    report.workflow_coverage = dict(workflow_patterns)
    
    report.tool_call_stats = {
        "samples_with_tool_calls": tool_call_samples,
        "total_tool_calls": total_tool_calls,
        "ratio": round(tool_call_samples / max(report.total_samples, 1), 3),
    }
    
    # Generate recommendations
    report.recommendations = generate_recommendations(report, issues)
    report.potential_issues = issues[:20]  # Limit issues shown
    
    return report


def generate_recommendations(report: DatasetReport, issues: list[str]) -> list[str]:
    """Generate recommendations based on report analysis."""
    recs = []
    
    # Check role balance
    if report.role_distribution:
        total = sum(report.role_distribution.values())
        for role, count in report.role_distribution.items():
            pct = count / total * 100
            if pct < 5:
                recs.append(f"Consider collecting more {role} samples (currently {pct:.1f}%)")
            elif pct > 50:
                recs.append(f"{role} dominates dataset ({pct:.1f}%) - consider balancing")
    
    # Check quality scores
    if report.quality_score_stats:
        mean_q = report.quality_score_stats.get("mean", 0)
        if mean_q < 0.5:
            recs.append(f"Average quality score is low ({mean_q:.2f}) - review quality filters")
    
    # Check tool call ratio
    if report.tool_call_stats["ratio"] < 0.1:
        recs.append("Low tool call ratio - ensure training data includes tool usage examples")
    
    # Check workflow coverage
    if not report.workflow_coverage.get("polecat_complete", 0):
        recs.append("Missing polecat completion workflows - add examples with 'gt done'")
    
    # Check for issues
    if issues:
        recs.append(f"Fix {len(issues)} data quality issues (see potential_issues)")
    
    # Check command diversity
    if report.command_coverage.get("unique_commands", 0) < 10:
        recs.append("Low command diversity - ensure varied CLI usage in training data")
    
    return recs


def print_report(report: DatasetReport) -> None:
    """Print report to console."""
    print(f"\n{'='*70}")
    print(f"TRAINING DATA REPORT: {Path(report.path).name}")
    print(f"Generated: {report.generated_at}")
    print(f"{'='*70}\n")
    
    # Overview
    print("📊 OVERVIEW")
    print(f"  Total samples:     {report.total_samples:,}")
    print(f"  Total characters:  {report.total_chars:,} ({report.chars_per_sample.get('total_mb', 0):.2f} MB)")
    print(f"  Approx tokens:     {report.approx_tokens:,}")
    print()
    
    # Role distribution
    print("🎭 ROLE DISTRIBUTION")
    for role, count in report.role_distribution.items():
        pct = count / max(report.total_samples, 1) * 100
        bar = "█" * int(pct / 5)
        print(f"  {role:15} {count:6,} ({pct:5.1f}%) {bar}")
    print()
    
    # Source distribution
    if report.source_distribution:
        print("📁 SOURCE DISTRIBUTION")
        for source, count in list(report.source_distribution.items())[:10]:
            pct = count / max(report.total_samples, 1) * 100
            print(f"  {source:30} {count:6,} ({pct:5.1f}%)")
        print()
    
    # Quality scores
    if report.quality_score_stats:
        print("⭐ QUALITY SCORES")
        for stat, value in report.quality_score_stats.items():
            print(f"  {stat:10} {value:.3f}")
        print()
    
    # Turn statistics
    if report.turns_per_sample:
        print("💬 TURNS PER SAMPLE")
        for stat, value in report.turns_per_sample.items():
            print(f"  {stat:10} {value:.1f}")
        print()
    
    # Command coverage
    print("🔧 COMMAND COVERAGE")
    print(f"  Unique commands: {report.command_coverage.get('unique_commands', 0)}")
    if report.command_coverage.get("by_type"):
        by_type = report.command_coverage["by_type"]
        print(f"    gt commands: {by_type.get('gt', 0)}")
        print(f"    bd commands: {by_type.get('bd', 0)}")
        print(f"    git commands: {by_type.get('git', 0)}")
    
    print("\n  Top commands:")
    top_cmds = list(report.command_coverage.get("top_commands", {}).items())[:10]
    for cmd, count in top_cmds:
        print(f"    {cmd}: {count}")
    print()
    
    # Workflow coverage
    print("🔄 WORKFLOW COVERAGE")
    for wf, count in sorted(report.workflow_coverage.items(), key=lambda x: -x[1]):
        print(f"  {wf}: {count}")
    print()
    
    # Tool call stats
    print("🛠️  TOOL USAGE")
    ts = report.tool_call_stats
    print(f"  Samples with tool calls: {ts.get('samples_with_tool_calls', 0):,}")
    print(f"  Total tool calls:        {ts.get('total_tool_calls', 0):,}")
    print(f"  Ratio:                   {ts.get('ratio', 0):.1%}")
    print()
    
    # Issues
    if report.potential_issues:
        print("⚠️  POTENTIAL ISSUES")
        for issue in report.potential_issues[:10]:
            print(f"  - {issue}")
        if len(report.potential_issues) > 10:
            print(f"  ... and {len(report.potential_issues) - 10} more")
        print()
    
    # Recommendations
    if report.recommendations:
        print("💡 RECOMMENDATIONS")
        for rec in report.recommendations:
            print(f"  • {rec}")
        print()


def save_markdown_report(report: DatasetReport, output_path: Path) -> None:
    """Save report as Markdown."""
    md_lines = [
        "# Training Data Report",
        "",
        f"**File:** {Path(report.path).name}",
        f"**Generated:** {report.generated_at}",
        "",
        "---",
        "",
        "## Overview",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total samples | {report.total_samples:,} |",
        f"| Total characters | {report.total_chars:,} |",
        f"| Approx tokens | {report.approx_tokens:,} |",
        f"| Total size | {report.chars_per_sample.get('total_mb', 0):.2f} MB |",
        "",
        "---",
        "",
        "## Role Distribution",
        "",
        "| Role | Count | Percentage |",
        "|------|-------|------------|",
    ]
    
    for role, count in report.role_distribution.items():
        pct = count / max(report.total_samples, 1) * 100
        md_lines.append(f"| {role} | {count:,} | {pct:.1f}% |")
    
    md_lines.extend([
        "",
        "---",
        "",
        "## Quality Scores",
        "",
    ])
    
    if report.quality_score_stats:
        for stat, value in report.quality_score_stats.items():
            md_lines.append(f"- **{stat}:** {value:.3f}")
    
    md_lines.extend([
        "",
        "---",
        "",
        "## Command Coverage",
        "",
        f"- **Unique commands:** {report.command_coverage.get('unique_commands', 0)}",
    ])
    
    if report.command_coverage.get("by_type"):
        by_type = report.command_coverage["by_type"]
        md_lines.append(f"- **gt commands:** {by_type.get('gt', 0)}")
        md_lines.append(f"- **bd commands:** {by_type.get('bd', 0)}")
        md_lines.append(f"- **git commands:** {by_type.get('git', 0)}")
    
    md_lines.extend([
        "",
        "### Top Commands",
        "",
    ])
    
    for cmd, count in list(report.command_coverage.get("top_commands", {}).items())[:15]:
        md_lines.append(f"- `{cmd}`: {count}")
    
    md_lines.extend([
        "",
        "---",
        "",
        "## Workflow Coverage",
        "",
    ])
    
    for wf, count in sorted(report.workflow_coverage.items(), key=lambda x: -x[1]):
        md_lines.append(f"- **{wf}:** {count}")
    
    if report.recommendations:
        md_lines.extend([
            "",
            "---",
            "",
            "## Recommendations",
            "",
        ])
        for rec in report.recommendations:
            md_lines.append(f"- {rec}")
    
    with open(output_path, "w") as f:
        f.write("\n".join(md_lines))
    
    print(f"\n📄 Markdown report saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate comprehensive training data reports"
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Input JSONL file to analyze"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for Markdown report (optional)"
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Output path for JSON report (optional)"
    )
    args = parser.parse_args()
    
    if not args.input_file.exists():
        print(f"File not found: {args.input_file}")
        sys.exit(1)
    
    report = generate_report(args.input_file)
    print_report(report)
    
    if args.output:
        save_markdown_report(report, args.output)
    
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report.__dict__, f, indent=2)
        print(f"\n📄 JSON report saved to: {args.json}")
    
    sys.exit(0)


if __name__ == "__main__":
    main()
