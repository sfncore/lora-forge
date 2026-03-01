"""Generate trial-specific Axolotl config from role template + suggested params."""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs" / "roles"


def load_role_template(role: str) -> dict:
    """Load the base Axolotl config for a role."""
    path = CONFIGS_DIR / f"{role}.yml"
    with open(path) as f:
        return yaml.safe_load(f)


def generate_trial_config(role: str, trial_number: int, params: dict) -> Path:
    """Override hyperparams in role template and write a trial-specific YAML.

    Returns the path to the temporary config file.
    """
    config = load_role_template(role)

    # LoRA architecture
    config["lora_r"] = params["lora_r"]
    config["lora_alpha"] = params["lora_alpha"]
    config["lora_dropout"] = params["lora_dropout"]

    # Training dynamics
    config["learning_rate"] = params["learning_rate"]
    config["warmup_steps"] = params["warmup_steps"]
    config["num_epochs"] = params["num_epochs"]
    config["weight_decay"] = params["weight_decay"]
    config["micro_batch_size"] = params["micro_batch_size"]
    config["gradient_accumulation_steps"] = params["gradient_accumulation_steps"]

    # Trial-specific output and tracking
    config["output_dir"] = f"output/checkpoints/{role}-trial-{trial_number}"
    if "wandb_name" in config or "wandb_project" in config:
        config["wandb_name"] = f"{role}-trial-{trial_number}"

    # Write to a temp file that persists until the caller cleans up
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yml", prefix=f"{role}_trial{trial_number}_",
        delete=False,
    )
    yaml.dump(config, tmp, default_flow_style=False)
    tmp.close()
    return Path(tmp.name)
