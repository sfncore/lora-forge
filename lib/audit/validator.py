"""Formula and prompt validator for audit framework."""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(Enum):
    """Severity levels for audit findings."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class Finding:
    """Represents an audit finding."""
    severity: Severity
    category: str
    formula: str
    location: str
    issue: str
    recommendation: str
    details: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "category": self.category,
            "formula": self.formula,
            "location": self.location,
            "issue": self.issue,
            "recommendation": self.recommendation,
            "details": self.details,
        }


class FormulaValidator:
    """Validates formula structure and content."""
    
    REQUIRED_FIELDS = ["formula", "type", "version", "description"]
    VALID_TYPES = ["workflow", "prompt", "data", "config"]
    
    def __init__(self):
        self.findings: list[Finding] = []
    
    def validate_formula(self, formula_data: dict) -> list[Finding]:
        """Validate a single formula."""
        self.findings = []
        formula_name = formula_data.get("formula", "<unknown>")
        
        for req_field in self.REQUIRED_FIELDS:
            if not formula_data.get(req_field):
                self.findings.append(Finding(
                    severity=Severity.HIGH,
                    category="structure",
                    formula=formula_name,
                    location="root",
                    issue=f"Missing required field: {req_field}",
                    recommendation=f"Add '{req_field}' field to formula metadata",
                ))
        
        formula_type = formula_data.get("type", "")
        if formula_type and formula_type not in self.VALID_TYPES:
            self.findings.append(Finding(
                severity=Severity.MEDIUM,
                category="structure",
                formula=formula_name,
                location="type",
                issue=f"Invalid formula type: {formula_type}",
                recommendation=f"Use one of: {', '.join(self.VALID_TYPES)}",
            ))
        
        version = formula_data.get("version")
        if version is None:
            self.findings.append(Finding(
                severity=Severity.LOW,
                category="structure",
                formula=formula_name,
                location="version",
                issue="Version not specified",
                recommendation="Add version number (start with 1)",
            ))
        
        steps_info = formula_data.get("steps_info", [])
        self._validate_steps(formula_name, steps_info)
        
        vars_section = formula_data.get("vars", {})
        self._validate_vars(formula_name, vars_section)
        
        return self.findings
    
    def _validate_steps(self, formula_name: str, steps: list[dict]) -> None:
        """Validate formula steps."""
        if not steps:
            self.findings.append(Finding(
                severity=Severity.MEDIUM,
                category="workflow",
                formula=formula_name,
                location="steps",
                issue="No steps defined",
                recommendation="Add at least one step to the workflow",
            ))
            return
        
        step_ids = set()
        for idx, step in enumerate(steps):
            step_id = step.get("id", f"step-{idx}")
            
            if step_id in step_ids:
                self.findings.append(Finding(
                    severity=Severity.HIGH,
                    category="workflow",
                    formula=formula_name,
                    location=f"step:{step_id}",
                    issue=f"Duplicate step ID: {step_id}",
                    recommendation="Use unique step IDs",
                ))
            step_ids.add(step_id)
            
            if not step.get("title"):
                self.findings.append(Finding(
                    severity=Severity.LOW,
                    category="workflow",
                    formula=formula_name,
                    location=f"step:{step_id}",
                    issue="Step missing title",
                    recommendation="Add descriptive title to step",
                ))
            
            if not step.get("acceptance"):
                self.findings.append(Finding(
                    severity=Severity.LOW,
                    category="workflow",
                    formula=formula_name,
                    location=f"step:{step_id}",
                    issue="Step missing acceptance criteria",
                    recommendation="Add acceptance criteria to define step completion",
                ))
            
            needs = step.get("needs", [])
            for need in needs:
                if need not in step_ids:
                    self.findings.append(Finding(
                        severity=Severity.MEDIUM,
                        category="workflow",
                        formula=formula_name,
                        location=f"step:{step_id}",
                        issue=f"Step references unknown dependency: {need}",
                        recommendation="Ensure all 'needs' references point to valid step IDs",
                    ))
    
    def _validate_vars(self, formula_name: str, vars_section: dict) -> None:
        """Validate variables section."""
        if not vars_section:
            return
        
        for var_name, var_data in vars_section.items():
            if not isinstance(var_data, dict):
                continue
            
            if not var_data.get("description"):
                self.findings.append(Finding(
                    severity=Severity.LOW,
                    category="variables",
                    formula=formula_name,
                    location=f"vars:{var_name}",
                    issue=f"Variable '{var_name}' missing description",
                    recommendation="Add description for variable",
                ))
            
            is_required = var_data.get("required", False)
            has_default = "default" in var_data
            
            if is_required and has_default:
                self.findings.append(Finding(
                    severity=Severity.LOW,
                    category="variables",
                    formula=formula_name,
                    location=f"vars:{var_name}",
                    issue=f"Variable '{var_name}' marked required but has default",
                    recommendation="Either remove 'required' or remove 'default'",
                ))


class PromptValidator:
    """Validates prompt quality and structure."""
    
    def __init__(self):
        self.findings: list[Finding] = []
    
    def validate_prompt(self, prompt_data: dict, formula_name: str) -> list[Finding]:
        """Validate a single prompt."""
        self.findings = []
        content = prompt_data.get("content", "")
        location = prompt_data.get("location", "unknown")
        
        if not content:
            self.findings.append(Finding(
                severity=Severity.HIGH,
                category="prompt",
                formula=formula_name,
                location=location,
                issue="Empty prompt content",
                recommendation="Add prompt content",
            ))
            return self.findings
        
        if "{{" in content and "}}" not in content:
            self.findings.append(Finding(
                severity=Severity.MEDIUM,
                category="prompt",
                formula=formula_name,
                location=location,
                issue="Unmatched variable placeholder (has {{ without }})",
                recommendation="Fix variable placeholder syntax",
            ))
        
        instruction_keywords = ["you must", "you should", "do not", "ensure", "verify", "check"]
        has_instruction = any(kw in content.lower() for kw in instruction_keywords)
        
        if not has_instruction:
            self.findings.append(Finding(
                severity=Severity.LOW,
                category="prompt",
                formula=formula_name,
                location=location,
                issue="Prompt may lack clear instructions",
                recommendation="Consider adding explicit instructions (must/should/do not)",
            ))
        
        context_indicators = ["example", "context", "background", "given", "assume"]
        has_context = any(kw in content.lower() for kw in context_indicators)
        
        if not has_context and len(content) > 100:
            self.findings.append(Finding(
                severity=Severity.INFO,
                category="prompt",
                formula=formula_name,
                location=location,
                issue="Prompt might benefit from examples or context",
                recommendation="Consider adding examples or background context",
            ))
        
        return self.findings


def validate_all(formulas: list[dict]) -> list[Finding]:
    """Validate all formulas and their prompts."""
    all_findings = []
    formula_validator = FormulaValidator()
    prompt_validator = PromptValidator()
    
    for formula in formulas:
        formula_name = formula.get("formula", formula.get("file", "<unknown>"))
        
        if "error" in formula:
            all_findings.append(Finding(
                severity=Severity.CRITICAL,
                category="extraction",
                formula=formula_name,
                location="file",
                issue=f"Formula extraction failed: {formula['error']}",
                recommendation="Fix formula file syntax",
                details={"error": formula["error"]},
            ))
            continue
        
        findings = formula_validator.validate_formula(formula)
        all_findings.extend(findings)
        
        prompts = formula.get("prompts", [])
        for prompt in prompts:
            prompt_findings = prompt_validator.validate_prompt(prompt, formula_name)
            all_findings.extend(prompt_findings)
    
    return all_findings


def categorize_findings(findings: list[Finding]) -> dict[str, list[Finding]]:
    """Categorize findings by severity."""
    categories = {
        "critical": [],
        "high": [],
        "medium": [],
        "low": [],
        "info": [],
    }
    
    for finding in findings:
        categories[finding.severity.value].append(finding)
    
    return categories


if __name__ == "__main__":
    import json
    import sys
    from extractor import extract_all_formulas
    
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    formulas = extract_all_formulas(base)
    findings = validate_all(formulas)
    
    categorized = categorize_findings(findings)
    print(json.dumps({k: [f.to_dict() for f in v] for k, v in categorized.items()}, indent=2))
