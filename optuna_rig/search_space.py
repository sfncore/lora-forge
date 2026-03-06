"""Hyperparameter search space for CMA-ES optimization."""

from __future__ import annotations

DEFAULT_SPACE = {
    "lora_r": {"type": "int", "low": 16, "high": 256, "step": 16},
    "lora_alpha_ratio": {"type": "float", "low": 1.0, "high": 4.0},
    "lora_dropout": {"type": "float", "low": 0.0, "high": 0.2},
    "learning_rate": {"type": "float", "low": 1e-5, "high": 5e-3, "log": True},
    "warmup_steps": {"type": "int", "low": 10, "high": 200},
    "num_epochs": {"type": "int", "low": 1, "high": 6},
    "weight_decay": {"type": "float", "low": 0.0, "high": 0.1},
    "micro_batch_size": {"type": "categorical", "choices": [1, 2, 4]},
    "gradient_accumulation_steps": {"type": "categorical", "choices": [2, 4, 8, 16]},
}


def get_search_space(role: str) -> dict:
    """Return search space for a role. Currently identical across roles."""
    return DEFAULT_SPACE.copy()


def suggest_params(trial, role: str) -> dict:
    """Sample hyperparameters from the search space using an Optuna trial."""
    space = get_search_space(role)
    params = {}

    for name, spec in space.items():
        if spec["type"] == "int":
            params[name] = trial.suggest_int(
                name, spec["low"], spec["high"], step=spec.get("step", 1)
            )
        elif spec["type"] == "float":
            params[name] = trial.suggest_float(
                name, spec["low"], spec["high"], log=spec.get("log", False)
            )
        elif spec["type"] == "categorical":
            params[name] = trial.suggest_categorical(name, spec["choices"])

    # Derive lora_alpha from ratio to maintain r-alpha correlation
    params["lora_alpha"] = int(params["lora_r"] * params.pop("lora_alpha_ratio"))

    return params
