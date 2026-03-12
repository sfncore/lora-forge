#!/usr/bin/env python3
"""
WARNING: NOT CONFIGURED FOR LORAFORGE
This script was copied from the sfgastown training system. The hardcoded
BASE_MODEL (Qwen3.5-2B), system prompts, and 16 patrol scenarios are
sfgastown-specific and do NOT match the loraforge v6+ training config
(Qwen3.5-9B, different prompts). Do not use without a full rewrite.

Original description:
Evaluation script for Qwen3.5-2B LoRA adapters (deacon-v1, witness-v1).

Adapts evaluate.py for PeftModel loading + 4-bit quantization.
Handles both Format B JSON and Claude XML tool call output formats.

Usage:
    cd /home/ubuntu/gt/loraforge/mayor/rig
    python scripts/evaluate_lora.py --adapter output/checkpoints/deacon-v1 --role deacon
    python scripts/evaluate_lora.py --adapter output/checkpoints/witness-v1 --role witness
"""

import argparse
import json
import os
import re
import sys
import time

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel

# Import scenarios and snapshot helpers from evaluate.py
sys.path.insert(0, os.path.dirname(__file__))
from evaluate import SCENARIOS_RICH, SCENARIOS_LEGACY, VALID_TOOLS

BASE_MODEL = "Qwen/Qwen3.5-2B"

SYSTEM_DEACON = """[GAS TOWN ROLE: deacon]
You are the Deacon, an autonomous patrol and coordination agent. You monitor system health, manage patrol cycles, dispatch work to polecats, and maintain the beads database. You operate without human prompting.

Respond with ONE JSON tool call:
{"tool": "<tool_name>", "args": {<arguments>}}

If no action is needed: {"tool": "none", "args": {}}

Available tools: gt_polecat_list, gt_polecat_nuke, gt_peek, gt_session_status, gt_nudge, gt_mail_inbox, gt_mail_read, gt_mail_send, gt_patrol_report, gt_handoff, gt_escalate, bd_show, bd_list, bd_close, bd_children, check_git_state, check_tmux_session, bash, none"""

SYSTEM_WITNESS = """You are a Witness agent. You respond ONLY with JSON tool calls.

For each turn, output exactly one JSON object:
{"tool": "<tool_name>", "args": {<arguments>}}

If no action is needed, output:
{"tool": "none", "args": {}}

Available tools: gt_polecat_list, gt_polecat_nuke, gt_peek, gt_session_status, gt_nudge, gt_mail_inbox, gt_mail_read, gt_mail_send, gt_patrol_report, gt_handoff, gt_escalate, bd_show, bd_list, bd_close, bd_children, check_git_state, check_tmux_session, bash"""


def load_model(adapter_path: str):
    """Load Qwen3.5-2B base + LoRA adapter in 4-bit."""
    print(f"Loading base model {BASE_MODEL} (4-bit)...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    )
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    print(f"Loading LoRA adapter from {adapter_path}...")
    model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()

    print(f"Loading tokenizer from {adapter_path}...")
    tokenizer = AutoTokenizer.from_pretrained(adapter_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"Model ready. Trainable: {trainable/1e6:.1f}M / {total/1e6:.1f}M params")
    return model, tokenizer


def generate_response(model, tokenizer, messages: list, system_prompt: str,
                      max_new_tokens: int = 200) -> tuple:
    """Generate a response and return (text, latency_ms)."""
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    prompt = tokenizer.apply_chat_template(
        full_messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    start = time.perf_counter()
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=None,
            top_p=None,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )
    latency = (time.perf_counter() - start) * 1000

    generated = tokenizer.decode(
        out[0][inputs.input_ids.shape[1]:],
        skip_special_tokens=True,
    )
    return generated.strip(), latency


def parse_output(text: str) -> dict | None:
    """
    Try to extract a tool call from model output.
    Handles:
    1. Format B: {"tool": "...", "args": {...}}
    2. Claude XML: <tool_call name="gt_nudge">{"args": ...}</tool_call>
    3. Partial / nested JSON
    """
    # 1. Direct JSON parse
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "tool" in data:
            return data
    except json.JSONDecodeError:
        pass

    # 2. JSON object in text
    for pattern in [r'\{"tool"[^}]*\}', r'\{[^{}]*\}', r'\{.*?\}', r'\{.*\}']:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group())
                if isinstance(data, dict):
                    # Ensure it has a tool key
                    if "tool" not in data:
                        # Try to infer from common patterns
                        if "name" in data:
                            data["tool"] = data.pop("name")
                        elif "action" in data:
                            data["tool"] = data.pop("action")
                    if "tool" in data:
                        if "args" not in data:
                            data["args"] = {}
                        return data
            except json.JSONDecodeError:
                pass

    # 3. Claude XML: <tool_call name="gt_nudge">...</tool_call>
    xml_m = re.search(r'<tool_call\s+name=["\']([^"\']+)["\']>(.*?)</tool_call>',
                      text, re.DOTALL)
    if xml_m:
        tool_name = xml_m.group(1)
        args_text = xml_m.group(2).strip()
        try:
            args = json.loads(args_text)
        except json.JSONDecodeError:
            args = {"raw": args_text}
        # Map tool name to our VALID_TOOLS if it's a gt command
        mapped = _map_tool_name(tool_name, args)
        return {"tool": mapped, "args": args, "_source": "xml"}

    # 4. Plain tool name on its own line
    for line in text.splitlines():
        line = line.strip().lower().replace("-", "_")
        if line in VALID_TOOLS:
            return {"tool": line, "args": {}, "_source": "plain"}

    # 5. Extract tool name from gt command (gt nudge → gt_nudge)
    gt_m = re.search(r'\bgt\s+([\w_]+)', text)
    if gt_m:
        candidate = f"gt_{gt_m.group(1).lower()}"
        if candidate in VALID_TOOLS:
            return {"tool": candidate, "args": {}, "_source": "gt_cmd"}

    return None


def _map_tool_name(name: str, args: dict) -> str:
    """Map a raw tool name (possibly 'Bash', 'gt', etc.) to a VALID_TOOLS name."""
    # Direct hit
    if name.lower() in VALID_TOOLS:
        return name.lower()

    # Bash tool with gt command inside
    if name.lower() in ("bash", "computer"):
        cmd = args.get("command", "")
        gt_m = re.search(r'\bgt\s+([\w_]+)', cmd)
        if gt_m:
            candidate = f"gt_{gt_m.group(1).lower()}"
            if candidate in VALID_TOOLS:
                return candidate
        return "bash"

    return name.lower()


def evaluate_scenarios(model, tokenizer, system_prompt: str, scenarios: list) -> list:
    """Run scenario-based evaluation."""
    results = []
    print(f"\n{'='*70}")
    print("SCENARIO EVALUATION")
    print(f"{'='*70}")

    for scenario in scenarios:
        output, latency = generate_response(model, tokenizer, scenario["messages"], system_prompt)
        parsed = parse_output(output)

        is_valid = parsed is not None
        tool_name = parsed.get("tool", "") if parsed else ""
        is_valid_tool = tool_name in VALID_TOOLS
        is_correct = tool_name in scenario["expected_tools"]
        parse_source = parsed.get("_source", "json") if parsed else "none"

        result = {
            "scenario": scenario["name"],
            "description": scenario["description"],
            "output": output[:300],
            "parsed": parsed,
            "valid_output": is_valid,
            "valid_tool": is_valid_tool,
            "correct_tool": is_correct,
            "parse_source": parse_source,
            "latency_ms": latency,
        }
        results.append(result)

        status = "OK  " if is_correct else "FAIL" if not is_valid else "WRONG"
        print(f"\n  [{status}] {scenario['name']}")
        print(f"         Expected: {scenario['expected_tools']}")
        print(f"         Got:      {tool_name!r}  (via {parse_source})")
        print(f"         Latency:  {latency:.0f}ms")
        if not is_correct:
            print(f"         Output:   {output[:150]}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Evaluate a Qwen3.5-2B LoRA adapter")
    parser.add_argument("--adapter", required=True, help="Path to LoRA adapter checkpoint")
    parser.add_argument("--role", choices=["deacon", "witness"], default="witness",
                        help="Role determines system prompt (default: witness)")
    parser.add_argument("--scenarios", choices=["rich", "legacy"], default="rich")
    parser.add_argument("--max-tokens", type=int, default=200)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    system_prompt = SYSTEM_DEACON if args.role == "deacon" else SYSTEM_WITNESS
    scenarios = SCENARIOS_RICH if args.scenarios == "rich" else SCENARIOS_LEGACY

    print(f"\nEvaluating: {args.adapter}")
    print(f"Role: {args.role} | Scenarios: {args.scenarios} ({len(scenarios)} total)")

    model, tokenizer = load_model(args.adapter)
    results = evaluate_scenarios(model, tokenizer, system_prompt, scenarios)

    # Summary
    n = len(results)
    n_correct = sum(1 for r in results if r["correct_tool"])
    n_valid = sum(1 for r in results if r["valid_output"])
    avg_lat = sum(r["latency_ms"] for r in results) / n
    parse_sources = {}
    for r in results:
        s = r["parse_source"]
        parse_sources[s] = parse_sources.get(s, 0) + 1

    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"  Scenarios:     {n_correct}/{n} correct ({n_correct/n*100:.0f}%)")
    print(f"  Valid output:  {n_valid}/{n} ({n_valid/n*100:.0f}%)")
    print(f"  Avg latency:   {avg_lat:.0f}ms")
    print(f"  Parse sources: {parse_sources}")

    output_path = args.output or os.path.join(args.adapter, "eval_lora_results.json")
    with open(output_path, "w") as f:
        json.dump({
            "adapter": args.adapter,
            "role": args.role,
            "scenario_format": args.scenarios,
            "summary": {
                "n_scenarios": n,
                "correct_tool_rate": n_correct / n,
                "valid_output_rate": n_valid / n,
                "avg_latency_ms": avg_lat,
                "parse_sources": parse_sources,
            },
            "scenarios": results,
        }, f, indent=2, default=str)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
