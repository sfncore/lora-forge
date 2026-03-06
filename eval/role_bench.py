"""Gas Town role-specific evaluation benchmarks.

Evaluates a fine-tuned model against role-specific scenarios.
Each scenario has a system prompt, user prompt, and expected behaviors.

Usage:
    python -m eval.role_bench --scenarios eval/prompts/ --model output/adapters/mayor
    python -m eval.role_bench --scenarios eval/prompts/ --role mayor --output results.json
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


def load_model(base_model: str, adapter_path: str | None = None):
    """Load base model in 4-bit quantization with optional LoRA adapter.

    GPU imports are deferred to this function so scoring functions
    remain importable on CPU-only machines.
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )

    if adapter_path:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, adapter_path)

    model.eval()
    return model, tokenizer


def generate_response(model, tokenizer, system: str, user: str) -> str:
    """Generate a response using ChatML template."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    input_ids = tokenizer.apply_chat_template(
        messages, return_tensors="pt", add_generation_prompt=True
    ).to(model.device)

    with __import__("torch").no_grad():
        output_ids = model.generate(
            input_ids,
            max_new_tokens=1024,
            temperature=0.7,
            top_p=0.9,
            do_sample=True,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )

    # Extract only newly generated tokens
    generated = output_ids[0, input_ids.shape[1]:]
    return tokenizer.decode(generated, skip_special_tokens=True)


def evaluate(model, tokenizer, scenarios: list[dict]) -> list[dict]:
    """Run evaluation across all scenarios."""
    results = []

    for i, scenario in enumerate(scenarios, 1):
        role = scenario.get("role", "unknown")
        title = scenario.get("scenario", "untitled")
        print(f"  [{i}/{len(scenarios)}] {role}: {title}...", end=" ", flush=True)

        response = generate_response(
            model, tokenizer,
            scenario["system"],
            scenario["user"],
        )

        score = score_response(response, scenario["expected_behaviors"])
        print(f"{score['score']:.0%}")

        results.append({
            "role": role,
            "scenario": title,
            "response": response,
            "score": score,
        })

    return results


def main():
    parser = argparse.ArgumentParser(description="Gas Town role evaluation")
    parser.add_argument("--scenarios", type=Path, required=True,
                        help="Scenarios JSONL file or directory")
    parser.add_argument("--model", type=str, default=None,
                        help="Path to LoRA adapter")
    parser.add_argument("--base-model", type=str,
                        default="Qwen/Qwen2.5-7B-Instruct",
                        help="Base model name or path")
    parser.add_argument("--output", type=Path, default=None,
                        help="Save results JSON to this path")
    parser.add_argument("--role", type=str, default=None,
                        help="Filter scenarios to a single role")
    args = parser.parse_args()

    scenarios = load_scenarios(args.scenarios)
    if not scenarios:
        print("No scenarios found")
        sys.exit(1)

    if args.role:
        scenarios = [s for s in scenarios if s.get("role") == args.role]
        if not scenarios:
            print(f"No scenarios found for role: {args.role}")
            sys.exit(1)

    print(f"Loaded {len(scenarios)} evaluation scenarios")

    if args.model is None and not args.output:
        print("No --model specified. Dry run — scenarios loaded OK.")
        return

    print(f"Loading model: {args.base_model}")
    if args.model:
        print(f"  adapter: {args.model}")
    model, tokenizer = load_model(args.base_model, args.model)

    print("Running evaluation...")
    results = evaluate(model, tokenizer, scenarios)
    print_report(results)

    if args.output:
        avg_score = sum(r["score"]["score"] for r in results) / max(len(results), 1)

        per_role: dict[str, list[float]] = {}
        for r in results:
            per_role.setdefault(r["role"], []).append(r["score"]["score"])

        output_data = {
            "base_model": args.base_model,
            "adapter": args.model,
            "average_score": avg_score,
            "per_role": {
                role: sum(s) / len(s) for role, s in per_role.items()
            },
            "details": results,
        }

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
