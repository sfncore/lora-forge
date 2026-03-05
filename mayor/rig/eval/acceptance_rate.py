"""Offline acceptance rate evaluation for speculative decoding.

Simulates speculative decoding acceptance without running inference.
Takes held-out (input, target_logits) pairs, runs a draft model forward pass,
compares draft tokens to target tokens, and reports acceptance rate overall
and per-role. Integrates with Optuna for hyperparameter search.

Usage:
    # Evaluate a single adapter
    python -m mayor.rig.eval.acceptance_rate \
        --draft-model output/checkpoints/mayor-v1 \
        --base-model Qwen/Qwen2.5-7B-Instruct \
        --eval-data output/datasets/eval_holdout.jsonl \
        --seed 42

    # Run Optuna hyperparameter search
    python -m mayor.rig.eval.acceptance_rate \
        --optuna --n-trials 50 \
        --base-model Qwen/Qwen2.5-7B-Instruct \
        --eval-data output/datasets/eval_holdout.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.nn.functional import log_softmax

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EvalSample:
    """A held-out evaluation sample with input tokens and target logits."""

    input_ids: list[int]
    target_token_ids: list[int]
    target_logprobs: list[list[float]] | None  # per-position vocab logprobs
    role: str = "unknown"
    sample_id: str = ""


@dataclass
class AcceptanceResult:
    """Result of acceptance rate evaluation for a single sample."""

    sample_id: str
    role: str
    n_draft_tokens: int
    n_accepted: int
    acceptance_rate: float
    per_token_accepted: list[bool] = field(default_factory=list)


@dataclass
class EvalReport:
    """Aggregated evaluation report across all samples."""

    overall_acceptance_rate: float
    per_role_acceptance_rate: dict[str, float]
    per_role_sample_count: dict[str, int]
    total_samples: int
    total_tokens_drafted: int
    total_tokens_accepted: int
    results: list[AcceptanceResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_acceptance_rate": self.overall_acceptance_rate,
            "per_role_acceptance_rate": self.per_role_acceptance_rate,
            "per_role_sample_count": self.per_role_sample_count,
            "total_samples": self.total_samples,
            "total_tokens_drafted": self.total_tokens_drafted,
            "total_tokens_accepted": self.total_tokens_accepted,
        }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_eval_data(eval_path: Path) -> list[EvalSample]:
    """Load held-out evaluation data from JSONL.

    Expected format per line:
    {
        "input_ids": [int, ...],
        "target_token_ids": [int, ...],
        "target_logprobs": [[float, ...], ...] | null,
        "role": "mayor",
        "sample_id": "sample_001"
    }
    """
    samples = []
    with open(eval_path) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            samples.append(EvalSample(
                input_ids=record["input_ids"],
                target_token_ids=record["target_token_ids"],
                target_logprobs=record.get("target_logprobs"),
                role=record.get("role", "unknown"),
                sample_id=record.get("sample_id", f"sample_{i:04d}"),
            ))
    logger.info("Loaded %d eval samples from %s", len(samples), eval_path)
    return samples


# ---------------------------------------------------------------------------
# Draft model interface
# ---------------------------------------------------------------------------

def load_draft_model(
    base_model: str,
    adapter_path: str | None = None,
    device: str = "auto",
    load_in_4bit: bool = True,
) -> tuple[Any, Any]:
    """Load the draft model (base + optional LoRA adapter).

    Returns (model, tokenizer) tuple.
    """
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)

    model_kwargs: dict[str, Any] = {
        "trust_remote_code": True,
        "torch_dtype": torch.bfloat16,
    }

    if load_in_4bit:
        from transformers import BitsAndBytesConfig
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )

    if device != "auto":
        model_kwargs["device_map"] = device
    else:
        model_kwargs["device_map"] = "auto"

    model = AutoModelForCausalLM.from_pretrained(base_model, **model_kwargs)

    if adapter_path:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter_path)
        logger.info("Loaded adapter from %s", adapter_path)

    model.eval()
    return model, tokenizer


def draft_forward_pass(
    model: Any,
    input_ids: list[int],
    n_tokens: int,
    device: str | None = None,
) -> tuple[list[int], torch.Tensor]:
    """Run draft model forward pass to get predicted tokens and logits.

    Args:
        model: The draft model.
        input_ids: Input token IDs (context).
        n_tokens: Number of tokens to draft (matches target sequence length).
        device: Device to use. If None, uses model's device.

    Returns:
        (draft_token_ids, draft_logits) where draft_logits has shape
        [n_tokens, vocab_size].
    """
    if device is None:
        device = next(model.parameters()).device

    input_tensor = torch.tensor([input_ids], dtype=torch.long, device=device)
    draft_token_ids = []
    all_logits = []

    with torch.no_grad():
        for _ in range(n_tokens):
            outputs = model(input_tensor)
            # logits shape: [1, seq_len, vocab_size]
            next_logits = outputs.logits[:, -1, :]  # [1, vocab_size]
            all_logits.append(next_logits.squeeze(0))

            next_token = next_logits.argmax(dim=-1)  # greedy
            draft_token_ids.append(next_token.item())

            input_tensor = torch.cat(
                [input_tensor, next_token.unsqueeze(0)], dim=1
            )

    return draft_token_ids, torch.stack(all_logits)


# ---------------------------------------------------------------------------
# Acceptance rate computation
# ---------------------------------------------------------------------------

def compute_acceptance_greedy(
    draft_tokens: list[int],
    target_tokens: list[int],
) -> AcceptanceResult:
    """Compute acceptance rate using greedy token matching.

    In speculative decoding, a draft token is accepted if it matches
    the target model's greedy choice.
    """
    n = min(len(draft_tokens), len(target_tokens))
    per_token = [draft_tokens[i] == target_tokens[i] for i in range(n)]
    n_accepted = sum(per_token)

    return AcceptanceResult(
        sample_id="",
        role="",
        n_draft_tokens=n,
        n_accepted=n_accepted,
        acceptance_rate=n_accepted / n if n > 0 else 0.0,
        per_token_accepted=per_token,
    )


def compute_acceptance_stochastic(
    draft_logits: torch.Tensor,
    target_logprobs: list[list[float]],
    draft_tokens: list[int],
    rng: np.random.Generator,
) -> AcceptanceResult:
    """Compute acceptance rate using stochastic acceptance criterion.

    Uses the standard speculative decoding acceptance probability:
        P(accept) = min(1, p_target(x) / p_draft(x))

    where x is the draft token. This gives the expected acceptance rate
    for stochastic speculative decoding.
    """
    n = min(len(draft_tokens), len(target_logprobs))
    draft_log_probs = log_softmax(draft_logits[:n], dim=-1)

    per_token = []
    for i in range(n):
        token = draft_tokens[i]

        # Draft model log-probability for this token
        draft_lp = draft_log_probs[i, token].item()

        # Target model log-probability for this token
        target_lp_vec = target_logprobs[i]
        if token < len(target_lp_vec):
            target_lp = target_lp_vec[token]
        else:
            target_lp = -float("inf")

        # Acceptance probability: min(1, p_target / p_draft)
        log_ratio = target_lp - draft_lp
        accept_prob = min(1.0, math.exp(log_ratio)) if not math.isinf(log_ratio) else 0.0

        # Stochastic accept
        accepted = rng.random() < accept_prob
        per_token.append(accepted)

    n_accepted = sum(per_token)
    return AcceptanceResult(
        sample_id="",
        role="",
        n_draft_tokens=n,
        n_accepted=n_accepted,
        acceptance_rate=n_accepted / n if n > 0 else 0.0,
        per_token_accepted=per_token,
    )


# ---------------------------------------------------------------------------
# Evaluation orchestrator
# ---------------------------------------------------------------------------

def evaluate_acceptance_rate(
    model: Any,
    samples: list[EvalSample],
    seed: int = 42,
    use_stochastic: bool = True,
    device: str | None = None,
) -> EvalReport:
    """Evaluate acceptance rate across all held-out samples.

    Args:
        model: The draft model (already loaded).
        samples: List of evaluation samples.
        seed: Random seed for reproducibility.
        use_stochastic: Use stochastic acceptance (requires target_logprobs).
        device: Device override.

    Returns:
        EvalReport with overall and per-role metrics.
    """
    rng = np.random.default_rng(seed)
    torch.manual_seed(seed)

    results: list[AcceptanceResult] = []
    role_accepted: dict[str, int] = defaultdict(int)
    role_drafted: dict[str, int] = defaultdict(int)
    role_count: dict[str, int] = defaultdict(int)

    for sample in samples:
        n_target = len(sample.target_token_ids)
        if n_target == 0:
            continue

        draft_tokens, draft_logits = draft_forward_pass(
            model, sample.input_ids, n_target, device=device,
        )

        if use_stochastic and sample.target_logprobs is not None:
            result = compute_acceptance_stochastic(
                draft_logits, sample.target_logprobs, draft_tokens, rng,
            )
        else:
            result = compute_acceptance_greedy(draft_tokens, sample.target_token_ids)

        result.sample_id = sample.sample_id
        result.role = sample.role
        results.append(result)

        role_accepted[sample.role] += result.n_accepted
        role_drafted[sample.role] += result.n_draft_tokens
        role_count[sample.role] += 1

    total_accepted = sum(r.n_accepted for r in results)
    total_drafted = sum(r.n_draft_tokens for r in results)

    per_role_rate = {
        role: role_accepted[role] / role_drafted[role]
        for role in role_drafted
        if role_drafted[role] > 0
    }

    return EvalReport(
        overall_acceptance_rate=total_accepted / total_drafted if total_drafted > 0 else 0.0,
        per_role_acceptance_rate=per_role_rate,
        per_role_sample_count=dict(role_count),
        total_samples=len(results),
        total_tokens_drafted=total_drafted,
        total_tokens_accepted=total_accepted,
        results=results,
    )


# ---------------------------------------------------------------------------
# Optuna integration
# ---------------------------------------------------------------------------

def optuna_objective(
    trial: Any,
    base_model: str,
    eval_data_path: Path,
    seed: int = 42,
) -> float:
    """Optuna objective: maximize acceptance rate for a LoRA config.

    Searches over:
        - lora_r: LoRA rank
        - lora_alpha: LoRA alpha scaling
        - learning_rate: Training LR
        - num_epochs: Number of training epochs
        - unfreeze_layers: Number of layers to unfreeze (unfreezing schedule)
    """
    import optuna

    # Hyperparameters to search
    lora_r = trial.suggest_categorical("lora_r", [16, 32, 64, 128])
    lora_alpha = trial.suggest_int("lora_alpha", lora_r, lora_r * 4, step=lora_r)
    learning_rate = trial.suggest_float("learning_rate", 1e-5, 5e-4, log=True)
    num_epochs = trial.suggest_int("num_epochs", 1, 5)
    unfreeze_layers = trial.suggest_int("unfreeze_layers", 0, 8)

    logger.info(
        "Trial %d: r=%d, alpha=%d, lr=%.2e, epochs=%d, unfreeze=%d",
        trial.number, lora_r, lora_alpha, learning_rate, num_epochs, unfreeze_layers,
    )

    # Generate training config for this trial
    config = {
        "base_model": base_model,
        "adapter": "qlora",
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
        "lora_dropout": 0.05,
        "lora_target_linear": True,
        "learning_rate": learning_rate,
        "num_epochs": num_epochs,
        "unfreeze_layers": unfreeze_layers,
        "load_in_4bit": True,
        "bf16": "auto",
        "flash_attention": True,
        "micro_batch_size": 2,
        "gradient_accumulation_steps": 4,
        "sequence_len": 4096,
        "sample_packing": True,
        "lr_scheduler": "cosine",
        "warmup_steps": 100,
        "optimizer": "adamw_torch",
    }

    # Write trial config
    trial_dir = Path(f"output/optuna_trials/trial_{trial.number:04d}")
    trial_dir.mkdir(parents=True, exist_ok=True)
    config_path = trial_dir / "config.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    # In a real pipeline, this would:
    # 1. Train the adapter with axolotl using the config
    # 2. Load the trained adapter
    # 3. Evaluate acceptance rate
    # For offline evaluation, we load an existing adapter if available.
    adapter_path = trial_dir / "adapter"
    if not adapter_path.exists():
        logger.warning(
            "Trial %d: No trained adapter at %s. "
            "Run training first, then re-evaluate. Returning 0.0.",
            trial.number, adapter_path,
        )
        # Report intermediate value for pruning
        trial.report(0.0, step=0)
        if trial.should_prune():
            raise optuna.TrialPruned()
        return 0.0

    model, _tokenizer = load_draft_model(
        base_model=base_model,
        adapter_path=str(adapter_path),
    )

    samples = load_eval_data(eval_data_path)
    report = evaluate_acceptance_rate(model, samples, seed=seed)

    # Save report
    report_path = trial_dir / "eval_report.json"
    with open(report_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)

    logger.info(
        "Trial %d: acceptance_rate=%.4f", trial.number, report.overall_acceptance_rate,
    )

    return report.overall_acceptance_rate


def run_optuna_search(
    base_model: str,
    eval_data_path: Path,
    n_trials: int = 50,
    seed: int = 42,
    study_name: str = "acceptance_rate_search",
    storage: str | None = None,
) -> Any:
    """Run Optuna hyperparameter search to maximize acceptance rate.

    Uses CMA-ES sampler as specified in the lora_forge architecture.
    """
    import optuna

    sampler = optuna.samplers.CmaEsSampler(seed=seed)
    pruner = optuna.pruners.MedianPruner(n_startup_trials=5)

    study = optuna.create_study(
        study_name=study_name,
        direction="maximize",
        sampler=sampler,
        pruner=pruner,
        storage=storage,
        load_if_exists=True,
    )

    study.optimize(
        lambda trial: optuna_objective(trial, base_model, eval_data_path, seed),
        n_trials=n_trials,
    )

    logger.info("Best trial: %d", study.best_trial.number)
    logger.info("Best acceptance rate: %.4f", study.best_value)
    logger.info("Best params: %s", study.best_params)

    # Save best config
    output_dir = Path("output/optuna_trials")
    output_dir.mkdir(parents=True, exist_ok=True)
    best_path = output_dir / "best_config.json"
    with open(best_path, "w") as f:
        json.dump(
            {"best_params": study.best_params, "best_value": study.best_value},
            f, indent=2,
        )

    return study


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline acceptance rate evaluation for speculative decoding.",
    )
    parser.add_argument(
        "--base-model", default="Qwen/Qwen2.5-7B-Instruct",
        help="Base model name or path.",
    )
    parser.add_argument(
        "--draft-model", default=None,
        help="Path to trained LoRA adapter. If omitted, evaluates base model only.",
    )
    parser.add_argument(
        "--eval-data", required=True, type=Path,
        help="Path to held-out evaluation JSONL.",
    )
    parser.add_argument(
        "--output", default=None, type=Path,
        help="Path to write evaluation report JSON.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--greedy", action="store_true",
        help="Use greedy matching instead of stochastic acceptance.",
    )
    parser.add_argument(
        "--device", default="auto", help="Device (auto, cuda, cpu).",
    )
    parser.add_argument(
        "--no-4bit", action="store_true",
        help="Disable 4-bit quantization (use full precision).",
    )

    # Optuna arguments
    parser.add_argument(
        "--optuna", action="store_true", help="Run Optuna hyperparameter search.",
    )
    parser.add_argument(
        "--n-trials", type=int, default=50, help="Number of Optuna trials.",
    )
    parser.add_argument(
        "--study-name", default="acceptance_rate_search",
        help="Optuna study name.",
    )
    parser.add_argument(
        "--storage", default=None,
        help="Optuna storage URL (e.g. sqlite:///optuna.db).",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if args.optuna:
        study = run_optuna_search(
            base_model=args.base_model,
            eval_data_path=args.eval_data,
            n_trials=args.n_trials,
            seed=args.seed,
            study_name=args.study_name,
            storage=args.storage,
        )
        print(f"\nBest acceptance rate: {study.best_value:.4f}")
        print(f"Best params: {study.best_params}")
        return

    # Single evaluation
    model, _tokenizer = load_draft_model(
        base_model=args.base_model,
        adapter_path=args.draft_model,
        device=args.device,
        load_in_4bit=not args.no_4bit,
    )

    samples = load_eval_data(args.eval_data)
    report = evaluate_acceptance_rate(
        model, samples,
        seed=args.seed,
        use_stochastic=not args.greedy,
    )

    # Print report
    print(f"\n{'='*60}")
    print("Acceptance Rate Evaluation Report")
    print(f"{'='*60}")
    print(f"Total samples:     {report.total_samples}")
    print(f"Tokens drafted:    {report.total_tokens_drafted}")
    print(f"Tokens accepted:   {report.total_tokens_accepted}")
    print(f"Overall rate:      {report.overall_acceptance_rate:.4f}")
    print(f"\nPer-role breakdown:")
    for role in sorted(report.per_role_acceptance_rate):
        rate = report.per_role_acceptance_rate[role]
        count = report.per_role_sample_count[role]
        print(f"  {role:20s}  {rate:.4f}  (n={count})")

    # Save report
    output_path = args.output or Path("output/eval_acceptance_report.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)
    print(f"\nReport saved to {output_path}")


if __name__ == "__main__":
    main()
