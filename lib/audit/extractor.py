"""Formula and prompt extractor for audit framework."""

import json
import os
from pathlib import Path
from typing import Any


def find_formulas(base_path: str | Path) -> list[Path]:
    """Find all formula files in the given base path.
    
    Args:
        base_path: Root directory to search for formulas
        
    Returns:
        List of paths to formula files (*.formula.toml)
    """
    base = Path(base_path)
    formulas = []
    
    for pattern in ["**/*.formula.toml", "**/formulas/*.toml"]:
        formulas.extend(base.glob(pattern))
    
    return sorted(set(formulas))


def extract_formula_metadata(formula_path: Path) -> dict[str, Any]:
    """Extract metadata from a formula file.
    
    Args:
        formula_path: Path to the formula file
        
    Returns:
        Dictionary with formula metadata (formula name, type, version, description, steps)
    """
    import tomllib
    
    with open(formula_path, "rb") as f:
        data = tomllib.load(f)
    
    return {
        "file": str(formula_path),
        "formula": data.get("formula", ""),
        "type": data.get("type", ""),
        "version": data.get("version", 0),
        "description": data.get("description", ""),
        "steps": data.get("steps", []),
        "vars": data.get("vars", {}),
    }


def extract_steps_info(steps: list[dict]) -> list[dict]:
    """Extract structured information from formula steps.
    
    Args:
        steps: List of step dictionaries from formula
        
    Returns:
        List of step info dictionaries
    """
    step_info = []
    for step in steps:
        info = {
            "id": step.get("id", ""),
            "title": step.get("title", ""),
            "description": step.get("description", ""),
            "acceptance": step.get("acceptance", ""),
            "needs": step.get("needs", []),
        }
        step_info.append(info)
    return step_info


def find_prompts_in_formula(formula_path: Path) -> list[dict]:
    """Find embedded prompts within a formula file.
    
    Looks for prompt templates in step descriptions or dedicated prompt sections.
    
    Args:
        formula_path: Path to the formula file
        
    Returns:
        List of prompt dictionaries with location and content
    """
    import tomllib
    import re
    
    prompts = []
    
    with open(formula_path, "rb") as f:
        data = tomllib.load(f)
    
    steps = data.get("steps", [])
    for step_idx, step in enumerate(steps):
        description = step.get("description", "")
        
        # Look for code blocks that might contain prompts
        code_blocks = re.findall(r"```(?:json)?\n([\s\S]*?)\n```", description)
        for block_idx, block in enumerate(code_blocks):
            # Check if it looks like a prompt template
            if any(kw in block.lower() for kw in ["prompt", "user", "assistant", "system"]):
                prompts.append({
                    "formula": data.get("formula", ""),
                    "step_id": step.get("id", f"step-{step_idx}"),
                    "step_title": step.get("title", ""),
                    "location": f"step-{step_idx}-block-{block_idx}",
                    "content": block.strip(),
                })
    
    return prompts


def extract_all_formulas(base_path: str | Path) -> list[dict]:
    """Extract all formulas from a base path.
    
    Args:
        base_path: Root directory to search
        
    Returns:
        List of formula metadata dictionaries
    """
    formulas = find_formulas(base_path)
    results = []
    
    for formula_path in formulas:
        try:
            metadata = extract_formula_metadata(formula_path)
            metadata["steps_info"] = extract_steps_info(metadata["steps"])
            metadata["prompts"] = find_prompts_in_formula(formula_path)
            # Remove raw steps to avoid duplication
            del metadata["steps"]
            results.append(metadata)
        except Exception as e:
            results.append({
                "file": str(formula_path),
                "error": str(e),
            })
    
    return results


if __name__ == "__main__":
    import sys
    
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    formulas = extract_all_formulas(base)
    print(json.dumps(formulas, indent=2))
