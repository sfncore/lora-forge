#!/usr/bin/env python3
"""Audit CLI for LoRA Forge formulas and prompts.

Usage:
    python scripts/audit/audit_commands.py run <target> [--output-dir <dir>]
    python scripts/audit/audit_commands.py report <target> [--format md|json]
    python scripts/audit/audit_commands.py validate <formula-file>
"""

import argparse
import sys
from pathlib import Path


def get_base_path(target: str) -> Path:
    """Get the base path for a target."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    
    if target == "lora_forge":
        return project_root
    elif target == "gastown":
        return project_root.parent / "gastown"
    else:
        return Path(target)


def cmd_run(args: argparse.Namespace) -> int:
    """Run a full audit on a target."""
    from lib.audit.extractor import extract_all_formulas
    from lib.audit.validator import validate_all
    from lib.audit.reporter import generate_json_report, generate_markdown_report
    
    target = args.target
    output_dir = Path(args.output_dir) if args.output_dir else None
    
    print(f"🔍 Running audit on: {target}")
    
    base_path = get_base_path(target)
    print(f"   Base path: {base_path}")
    
    if not base_path.exists():
        print(f"❌ Error: Base path does not exist: {base_path}")
        return 1
    
    print("   📦 Extracting formulas...")
    formulas = extract_all_formulas(base_path)
    print(f"   ✓ Found {len(formulas)} formulas")
    
    print("   ✅ Validating...")
    findings = validate_all(formulas)
    print(f"   ✓ Found {len(findings)} findings")
    
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        
        md_path = output_dir / f"{target}-audit-report.md"
        json_path = output_dir / f"{target}-audit-report.json"
        
        print(f"   📝 Generating markdown report: {md_path}")
        generate_markdown_report(findings, len(formulas), target_name=target, output_path=md_path)
        
        print(f"   📝 Generating JSON report: {json_path}")
        generate_json_report(findings, len(formulas), target_name=target, output_path=json_path)
        
        print(f"\n✅ Audit complete! Reports saved to {output_dir}")
    else:
        from lib.audit.reporter import generate_summary
        summary = generate_summary(findings)
        print(f"\n📊 Summary: {summary}")
        print("\n💡 Use --output-dir to save full reports")
    
    critical_count = sum(1 for f in findings if f.severity.value == "critical")
    high_count = sum(1 for f in findings if f.severity.value == "high")
    
    if critical_count > 0 or high_count > 0:
        print(f"\n⚠️  {critical_count} critical, {high_count} high severity findings")
        return 2
    
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Generate a report from existing audit data."""
    from lib.audit.extractor import extract_all_formulas
    from lib.audit.validator import validate_all
    from lib.audit.reporter import generate_json_report, generate_markdown_report
    
    target = args.target
    fmt = args.format
    output_dir = Path(args.output_dir) if args.output_dir else None
    
    base_path = get_base_path(target)
    
    if not base_path.exists():
        print(f"❌ Error: Base path does not exist: {base_path}")
        return 1
    
    formulas = extract_all_formulas(base_path)
    findings = validate_all(formulas)
    
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
    
    if fmt == "md":
        generate_func = generate_markdown_report
    else:
        generate_func = generate_json_report
    
    output_path = output_dir / f"{target}-audit-report.{fmt}" if output_dir else None
    
    if output_path:
        print(f"📝 Generating {fmt.upper()} report: {output_path}")
    
    generate_func(findings, len(formulas), target_name=target, output_path=output_path)
    
    if not output_path:
        if fmt == "md":
            print(generate_markdown_report(findings, len(formulas), target))
        else:
            import json
            from datetime import datetime
            from lib.audit.validator import categorize_findings
            
            categorized = categorize_findings(findings)
            report = {
                "metadata": {
                    "generated": datetime.now().isoformat(),
                    "target": target,
                    "formulas_audited": len(formulas),
                },
                "findings": [f.to_dict() for f in findings],
            }
            print(json.dumps(report, indent=2))
    
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a single formula file."""
    from lib.audit.extractor import extract_formula_metadata
    from lib.audit.validator import FormulaValidator
    
    formula_path = Path(args.formula_file)
    
    if not formula_path.exists():
        print(f"❌ Error: Formula file not found: {formula_path}")
        return 1
    
    print(f"🔍 Validating: {formula_path}")
    
    try:
        metadata = extract_formula_metadata(formula_path)
        validator = FormulaValidator()
        findings = validator.validate_formula(metadata)
        
        if findings:
            print(f"\n⚠️  Found {len(findings)} issues:\n")
            for finding in findings:
                print(f"  [{finding.severity.value.upper()}] {finding.issue}")
                print(f"    Location: {finding.location}")
                print(f"    Recommendation: {finding.recommendation}")
                print()
        else:
            print("✅ No issues found!")
        
        return 0 if not findings else 1
        
    except Exception as e:
        print(f"❌ Error validating formula: {e}")
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Audit CLI for LoRA Forge formulas and prompts")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    run_parser = subparsers.add_parser("run", help="Run full audit on a target")
    run_parser.add_argument("target", help="Target to audit (lora_forge, gastown, or path)")
    run_parser.add_argument("--output-dir", "-o", help="Output directory for reports")
    run_parser.set_defaults(func=cmd_run)
    
    report_parser = subparsers.add_parser("report", help="Generate report for a target")
    report_parser.add_argument("target", help="Target to report on")
    report_parser.add_argument("--format", "-f", choices=["md", "json"], default="md")
    report_parser.add_argument("--output-dir", "-o", help="Output directory for report")
    report_parser.set_defaults(func=cmd_report)
    
    validate_parser = subparsers.add_parser("validate", help="Validate a single formula file")
    validate_parser.add_argument("formula_file", help="Path to formula file")
    validate_parser.set_defaults(func=cmd_validate)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
