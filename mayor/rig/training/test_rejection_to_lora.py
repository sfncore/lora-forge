"""Tests for rejection_to_lora module.

Tests the conversion, mixing, and config generation logic.
Parquet loading is tested separately (requires pyarrow).
"""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

from mayor.rig.training.rejection_to_lora import (
    compute_kl_divergence,
    generate_training_config,
    mix_datasets,
    rejection_to_sharegpt,
    write_training_jsonl,
)


def test_rejection_to_sharegpt_basic():
    """Convert a rejection record to sharegpt format."""
    record = {
        "role": "mayor",
        "session_id": "test-123",
        "prompt": "What is the status of the rig?",
        "target_response": "The rig is operational.",
        "draft_response": "I don't know.",
        "rejection_reason": "Unhelpful response",
        "acceptance_score": 0.2,
    }
    result = rejection_to_sharegpt(record)

    assert "conversations" in result
    assert "metadata" in result
    assert len(result["conversations"]) == 3  # system + human + gpt

    # System prompt.
    assert result["conversations"][0]["from"] == "system"
    assert "mayor" in result["conversations"][0]["value"].lower()

    # User prompt.
    assert result["conversations"][1]["from"] == "human"
    assert result["conversations"][1]["value"] == "What is the status of the rig?"

    # Target response (not draft).
    assert result["conversations"][2]["from"] == "gpt"
    assert result["conversations"][2]["value"] == "The rig is operational."

    # Metadata.
    assert result["metadata"]["role"] == "mayor"
    assert result["metadata"]["source"] == "rejection_data"
    assert result["metadata"]["has_soft_labels"] is False


def test_rejection_to_sharegpt_with_soft_labels():
    """Convert with KL divergence soft labels."""
    record = {
        "role": "polecat",
        "session_id": "test-456",
        "prompt": "Run the tests",
        "target_response": "Running pytest now.",
        "draft_response": "What tests?",
        "draft_logprobs": [-0.5, -1.0, -2.0],
        "target_logprobs": [-0.3, -0.8, -1.5],
        "rejection_reason": "Did not execute",
        "acceptance_score": 0.1,
    }
    result = rejection_to_sharegpt(record)

    assert result["metadata"]["has_soft_labels"] is True
    assert "kl_divergence" in result["metadata"]
    assert result["metadata"]["kl_divergence"] >= 0.0


def test_compute_kl_divergence():
    """KL divergence is non-negative and zero for identical distributions."""
    # Identical distributions -> KL = 0.
    same = [-1.0, -2.0, -0.5]
    assert compute_kl_divergence(same, same) == 0.0

    # Different distributions -> KL > 0.
    draft = [-2.0, -3.0, -1.0]
    target = [-1.0, -2.0, -0.5]
    kl = compute_kl_divergence(draft, target)
    assert kl > 0.0

    # Empty lists -> 0.
    assert compute_kl_divergence([], []) == 0.0


def test_mix_datasets_ratio():
    """Verify 90/10 mixing ratio."""
    rejection = [{"conversations": [{"from": "gpt", "value": f"r{i}"}]} for i in range(100)]
    general = [{"conversations": [{"from": "gpt", "value": f"g{i}"}]} for i in range(50)]

    mixed = mix_datasets(rejection, general, rejection_ratio=0.9, seed=42)

    # Should have 100 rejection + ~11 general (100 * 0.1/0.9 ≈ 11).
    assert len(mixed) > len(rejection)
    assert len(mixed) <= len(rejection) + len(general)


def test_mix_datasets_empty_rejection():
    """If no rejection data, return general data."""
    general = [{"conversations": []}]
    result = mix_datasets([], general)
    assert result == general


def test_mix_datasets_empty_general():
    """If no general data, return rejection data."""
    rejection = [{"conversations": []}]
    result = mix_datasets(rejection, [])
    assert result == rejection


def test_write_training_jsonl(tmp_path):
    """Write and read back JSONL."""
    samples = [
        {"conversations": [{"from": "gpt", "value": "hello"}], "metadata": {"role": "mayor"}},
        {"conversations": [{"from": "gpt", "value": "world"}], "metadata": {"role": "polecat"}},
    ]

    out = tmp_path / "test_train.jsonl"
    write_training_jsonl(samples, out)

    assert out.exists()
    lines = out.read_text().strip().split("\n")
    assert len(lines) == 2

    loaded = [json.loads(line) for line in lines]
    assert loaded[0]["metadata"]["role"] == "mayor"
    assert loaded[1]["metadata"]["role"] == "polecat"


def test_generate_training_config():
    """Config has required Axolotl fields."""
    config = generate_training_config(
        role="mayor",
        train_path=Path("output/mayor_rejection_train.jsonl"),
        output_dir=Path("output/checkpoints"),
        has_soft_labels=False,
    )

    assert config["base_model"] == "Qwen/Qwen2.5-7B-Instruct"
    assert config["adapter"] == "qlora"
    assert config["lora_r"] == 64
    assert len(config["datasets"]) == 1
    assert config["datasets"][0]["type"] == "sharegpt"
    assert "kl_divergence_weight" not in config


def test_generate_training_config_with_soft_labels():
    """Config includes KL weight when soft labels are available."""
    config = generate_training_config(
        role="polecat",
        train_path=Path("output/polecat_rejection_train.jsonl"),
        output_dir=Path("output/checkpoints"),
        has_soft_labels=True,
    )

    assert "kl_divergence_weight" in config
    assert config["kl_divergence_weight"] == 0.5
