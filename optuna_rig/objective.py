"""Optuna objective function: train + evaluate a single trial.

Uses subprocess isolation so GPU memory is freed between trials.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from optuna_rig.config_generator import generate_trial_config
from optuna_rig.search_space import suggest_params


def objective(
    trial,
    role: str,
    base_model: str = "Qwen/Qwen2.5-7B-Instruct",
    scenarios_dir: str = "eval/prompts",
) -> float:
    """Run one trial: suggest params → train → evaluate → return score."""
    params = suggest_params(trial, role)
    config_path = generate_trial_config(role, trial.number, params)

    try:
        # Train via subprocess so GPU memory is released on completion
        adapter_dir = f"output/checkpoints/{role}-trial-{trial.number}"
        train_result = subprocess.run(
            [sys.executable, "-m", "axolotl.cli.train", str(config_path)],
            capture_output=True, text=True, timeout=7200,  # 2h max
        )
        if train_result.returncode != 0:
            print(f"  Trial {trial.number} training failed: {train_result.stderr[:200]}")
            return 0.0

        # Evaluate the trained adapter
        results_file = tempfile.NamedTemporaryFile(
            suffix=".json", prefix=f"eval_{role}_t{trial.number}_", delete=False,
        )
        results_file.close()

        eval_result = subprocess.run(
            [
                sys.executable, "-m", "eval.role_bench",
                "--scenarios", scenarios_dir,
                "--role", role,
                "--model", adapter_dir,
                "--base-model", base_model,
                "--output", results_file.name,
            ],
            capture_output=True, text=True, timeout=1800,  # 30min max
        )
        if eval_result.returncode != 0:
            print(f"  Trial {trial.number} eval failed: {eval_result.stderr[:200]}")
            return 0.0

        with open(results_file.name) as f:
            results = json.load(f)
        score = results.get("average_score", 0.0)
        print(f"  Trial {trial.number} score: {score:.3f}")
        return score

    except subprocess.TimeoutExpired:
        print(f"  Trial {trial.number} timed out")
        return 0.0
    except Exception as e:
        print(f"  Trial {trial.number} error: {e}")
        return 0.0
    finally:
        config_path.unlink(missing_ok=True)
