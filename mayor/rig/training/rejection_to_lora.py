"""Convert rejection Parquet data to LoRA training format.

Reads rejection data from SSD distillation (Parquet files), filters by role,
converts to sharegpt JSONL format, and mixes with general data for LoRA
fine-tuning. Supports soft labels via KL divergence where the draft model
disagreed with the target.

Usage:
    python -m mayor.rig.training.rejection_to_lora \\
        --rejection-dir output/rejection_data \\
        --general-dir output/datasets \\
        --output-dir output/datasets/rejection_lora \\
        --role mayor

    # All roles at once:
    python -m mayor.rig.training.rejection_to_lora \\
        --rejection-dir output/rejection_data \\
        --general-dir output/datasets \\
        --output-dir output/datasets/rejection_lora

Dependencies:
    pip install pyarrow pandas
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Canonical Gas Town roles.
ROLES = ("mayor", "deacon", "witness", "refinery", "polecat", "crew")

# Mix ratio: 90% rejection data, 10% general data.
REJECTION_RATIO = 0.9
GENERAL_RATIO = 0.1


def load_rejection_parquet(rejection_dir: Path, role: str | None = None) -> list[dict]:
    """Load rejection data from Parquet files.

    Expected Parquet schema:
        - session_id: str
        - role: str (mayor, polecat, etc.)
        - prompt: str (user message)
        - draft_response: str (draft model's rejected response)
        - target_response: str (target model's accepted response)
        - draft_logprobs: list[float] (optional, for KL divergence)
        - target_logprobs: list[float] (optional, for KL divergence)
        - rejection_reason: str (why draft was rejected)
        - acceptance_score: float (0-1, how close draft was to acceptable)

    Args:
        rejection_dir: Directory containing rejection Parquet files.
        role: If provided, filter to only this role.

    Returns:
        List of rejection records as dicts.
    """
    import pyarrow.parquet as pq

    parquet_files = sorted(rejection_dir.glob("*.parquet"))
    if not parquet_files:
        logger.warning("No Parquet files found in %s", rejection_dir)
        return []

    records: list[dict] = []
    for pf in parquet_files:
        table = pq.read_table(pf)
        df_records = table.to_pylist()
        records.extend(df_records)

    logger.info("Loaded %d rejection records from %d files", len(records), len(parquet_files))

    if role:
        records = [r for r in records if r.get("role") == role]
        logger.info("Filtered to %d records for role=%s", len(records), role)

    return records


def rejection_to_sharegpt(record: dict) -> dict[str, Any]:
    """Convert a single rejection record to sharegpt format.

    The target_response is used as the training signal (what the model
    should have said). The draft_response is preserved in metadata for
    analysis but not used in the conversation.

    Returns:
        A sharegpt-formatted dict compatible with Axolotl.
    """
    role = record.get("role", "unknown")
    conversations = []

    # System message with role identity.
    conversations.append({
        "from": "system",
        "value": _system_prompt_for_role(role),
    })

    # User prompt.
    prompt = record.get("prompt", "")
    if prompt:
        conversations.append({
            "from": "human",
            "value": prompt,
        })

    # Target (correct) response as the training signal.
    target = record.get("target_response", "")
    if target:
        conversations.append({
            "from": "gpt",
            "value": target,
        })

    # Build metadata.
    metadata = {
        "role": role,
        "session_id": record.get("session_id", ""),
        "source": "rejection_data",
        "rejection_reason": record.get("rejection_reason", ""),
        "acceptance_score": record.get("acceptance_score", 0.0),
    }

    # Include KL divergence info if logprobs are available.
    draft_logprobs = record.get("draft_logprobs")
    target_logprobs = record.get("target_logprobs")
    if draft_logprobs and target_logprobs:
        kl_div = compute_kl_divergence(draft_logprobs, target_logprobs)
        metadata["kl_divergence"] = kl_div
        metadata["has_soft_labels"] = True
    else:
        metadata["has_soft_labels"] = False

    return {
        "conversations": conversations,
        "metadata": metadata,
    }


def compute_kl_divergence(
    draft_logprobs: list[float],
    target_logprobs: list[float],
) -> float:
    """Compute KL divergence between draft and target log-probabilities.

    KL(target || draft) = sum(target_prob * log(target_prob / draft_prob))

    This measures how much the draft distribution diverges from the target.
    Higher values indicate the draft model was more "wrong".

    Args:
        draft_logprobs: Log-probabilities from draft model.
        target_logprobs: Log-probabilities from target model.

    Returns:
        KL divergence (non-negative float).
    """
    import math

    min_len = min(len(draft_logprobs), len(target_logprobs))
    if min_len == 0:
        return 0.0

    kl = 0.0
    for i in range(min_len):
        target_p = math.exp(target_logprobs[i])
        draft_p = math.exp(draft_logprobs[i])
        if target_p > 0 and draft_p > 0:
            kl += target_p * (target_logprobs[i] - draft_logprobs[i])

    return max(0.0, kl)


def load_general_data(general_dir: Path, role: str) -> list[dict]:
    """Load general training data for a role.

    Looks for {role}_train.jsonl or gastown_train.jsonl as fallback.

    Args:
        general_dir: Directory containing general training JSONL.
        role: The role to load data for.

    Returns:
        List of sharegpt-formatted dicts.
    """
    role_file = general_dir / f"{role}_train.jsonl"
    fallback_file = general_dir / "gastown_train.jsonl"

    target_file = role_file if role_file.exists() else fallback_file
    if not target_file.exists():
        logger.warning("No general data found for role=%s in %s", role, general_dir)
        return []

    records = []
    with open(target_file, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    # Filter to matching role if using the combined file.
    if target_file == fallback_file:
        records = [
            r for r in records
            if r.get("metadata", {}).get("role") == role
        ]

    logger.info("Loaded %d general samples for role=%s", len(records), role)
    return records


def mix_datasets(
    rejection_samples: list[dict],
    general_samples: list[dict],
    rejection_ratio: float = REJECTION_RATIO,
    seed: int = 42,
) -> list[dict]:
    """Mix rejection and general data at the specified ratio.

    Target: 90% rejection data, 10% general data.
    If either source is too small, uses whatever is available.

    Args:
        rejection_samples: Samples from rejection data.
        general_samples: Samples from general training data.
        rejection_ratio: Fraction of final dataset from rejection data.
        seed: Random seed for reproducibility.

    Returns:
        Mixed and shuffled list of training samples.
    """
    rng = random.Random(seed)

    if not rejection_samples:
        logger.warning("No rejection samples, using only general data")
        return general_samples

    if not general_samples:
        logger.warning("No general samples, using only rejection data")
        return rejection_samples

    # Calculate target counts based on ratio.
    # rejection_ratio of the final dataset should be rejection data.
    n_rejection = len(rejection_samples)
    n_general_target = int(n_rejection * (1 - rejection_ratio) / rejection_ratio)

    # Sample general data (with replacement if needed).
    if n_general_target <= len(general_samples):
        general_subset = rng.sample(general_samples, n_general_target)
    else:
        general_subset = general_samples[:]
        logger.info(
            "Not enough general data (%d) for target (%d), using all available",
            len(general_samples),
            n_general_target,
        )

    mixed = rejection_samples + general_subset
    rng.shuffle(mixed)

    actual_ratio = len(rejection_samples) / len(mixed)
    logger.info(
        "Mixed dataset: %d rejection + %d general = %d total (%.1f%% rejection)",
        len(rejection_samples),
        len(general_subset),
        len(mixed),
        actual_ratio * 100,
    )
    return mixed


def write_training_jsonl(samples: list[dict], output_path: Path) -> None:
    """Write training samples to JSONL file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    logger.info("Wrote %d samples to %s", len(samples), output_path)


def generate_training_config(
    role: str,
    train_path: Path,
    output_dir: Path,
    has_soft_labels: bool = False,
) -> dict[str, Any]:
    """Generate an Axolotl training config for rejection-based LoRA.

    Args:
        role: Gas Town role name.
        train_path: Path to the training JSONL file.
        output_dir: Directory for model checkpoints.
        has_soft_labels: Whether to configure KL divergence loss.

    Returns:
        Dict that can be written as YAML config.
    """
    config: dict[str, Any] = {
        "base_model": "Qwen/Qwen2.5-7B-Instruct",
        "model_type": "AutoModelForCausalLM",
        "tokenizer_type": "AutoTokenizer",
        "load_in_4bit": True,
        "adapter": "qlora",
        "lora_r": 64,
        "lora_alpha": 128,
        "lora_dropout": 0.05,
        "lora_target_linear": True,
        "datasets": [
            {
                "path": str(train_path),
                "type": "sharegpt",
                "conversation": "chatml",
            }
        ],
        "dataset_prepared_path": str(output_dir / f"prepared_{role}_rejection"),
        "val_set_size": 0.05,
        "output_dir": str(output_dir / f"{role}-rejection-v1"),
        "sequence_len": 4096,
        "sample_packing": True,
        "pad_to_sequence_len": True,
        "gradient_accumulation_steps": 4,
        "micro_batch_size": 2,
        "num_epochs": 3,
        "learning_rate": 2e-4,
        "lr_scheduler": "cosine",
        "warmup_steps": 50,
        "optimizer": "adamw_torch",
        "weight_decay": 0.01,
        "max_grad_norm": 1.0,
        "bf16": "auto",
        "tf32": True,
        "flash_attention": True,
        "wandb_project": "lora-forge",
        "wandb_name": f"{role}-rejection-v1",
        "saves_per_epoch": 2,
        "eval_steps": 50,
        "logging_steps": 10,
    }

    # When soft labels are available, configure KL divergence loss weighting.
    # This is passed through Axolotl's custom trainer config.
    if has_soft_labels:
        config["kl_divergence_weight"] = 0.5  # Balance CE loss + KL loss

    return config


def process_role(
    role: str,
    rejection_dir: Path,
    general_dir: Path,
    output_dir: Path,
    seed: int = 42,
) -> dict[str, Any] | None:
    """Process rejection data for a single role.

    Returns:
        Summary dict with stats, or None if no data.
    """
    logger.info("Processing role: %s", role)

    # Load rejection data for this role.
    rejection_records = load_rejection_parquet(rejection_dir, role=role)
    if not rejection_records:
        logger.info("No rejection data for role=%s, skipping", role)
        return None

    # Convert to sharegpt format.
    rejection_samples = []
    has_soft_labels = False
    for record in rejection_records:
        sample = rejection_to_sharegpt(record)
        if sample["conversations"]:  # Skip empty conversations.
            rejection_samples.append(sample)
            if sample["metadata"].get("has_soft_labels"):
                has_soft_labels = True

    if not rejection_samples:
        logger.info("No valid samples for role=%s after conversion", role)
        return None

    # Load general data for mixing.
    general_samples = load_general_data(general_dir, role)

    # Mix at 90/10 ratio.
    mixed = mix_datasets(rejection_samples, general_samples, seed=seed)

    # Write training data.
    train_path = output_dir / f"{role}_rejection_train.jsonl"
    write_training_jsonl(mixed, train_path)

    # Generate training config.
    config = generate_training_config(
        role=role,
        train_path=train_path,
        output_dir=output_dir / "checkpoints",
        has_soft_labels=has_soft_labels,
    )
    config_path = output_dir / f"{role}_rejection_config.yml"
    _write_yaml(config, config_path)

    return {
        "role": role,
        "rejection_samples": len(rejection_samples),
        "general_samples": len(general_samples),
        "mixed_total": len(mixed),
        "has_soft_labels": has_soft_labels,
        "train_path": str(train_path),
        "config_path": str(config_path),
    }


def _write_yaml(data: dict, path: Path) -> None:
    """Write a dict as YAML. Falls back to JSON if PyYAML unavailable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    except ImportError:
        # Fall back to JSON if yaml not available.
        json_path = path.with_suffix(".json")
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)
        logger.warning("PyYAML not installed, wrote config as JSON: %s", json_path)


def _system_prompt_for_role(role: str) -> str:
    """Get role-specific system prompt for rejection training data.

    Uses the same prompts as the main pipeline's chat_formatter.
    """
    # Import from existing formatter to stay consistent.
    try:
        from data.transform.chat_formatter import ROLE_SYSTEM_PROMPTS, DEFAULT_SYSTEM_PROMPT
        return ROLE_SYSTEM_PROMPTS.get(role, DEFAULT_SYSTEM_PROMPT)
    except ImportError:
        return f"[GAS TOWN ROLE: {role}]\nYou are a Gas Town {role} agent."


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Convert rejection Parquet data to LoRA training format",
    )
    parser.add_argument(
        "--rejection-dir",
        type=Path,
        default=Path("output/rejection_data"),
        help="Directory containing rejection Parquet files",
    )
    parser.add_argument(
        "--general-dir",
        type=Path,
        default=Path("output/datasets"),
        help="Directory containing general training JSONL",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/datasets/rejection_lora"),
        help="Output directory for mixed training data",
    )
    parser.add_argument(
        "--role",
        choices=ROLES,
        help="Process only this role (default: all roles)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible mixing",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    roles = [args.role] if args.role else list(ROLES)
    results = []

    for role in roles:
        result = process_role(
            role=role,
            rejection_dir=args.rejection_dir,
            general_dir=args.general_dir,
            output_dir=args.output_dir,
            seed=args.seed,
        )
        if result:
            results.append(result)

    if not results:
        logger.warning("No rejection data processed for any role")
        sys.exit(0)

    # Print summary.
    print("\n=== Rejection-to-LoRA Summary ===")
    total_samples = 0
    for r in results:
        total_samples += r["mixed_total"]
        soft = " [soft labels]" if r["has_soft_labels"] else ""
        print(
            f"  {r['role']:12s}: {r['rejection_samples']:5d} rejection "
            f"+ {r['general_samples']:5d} general = {r['mixed_total']:5d} mixed{soft}"
        )
    print(f"  {'TOTAL':12s}: {total_samples:5d} samples across {len(results)} roles")
    print(f"\nTraining data written to: {args.output_dir}")


if __name__ == "__main__":
    main()
