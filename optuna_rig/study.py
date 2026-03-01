"""Optuna study management with CMA-ES sampler."""

from __future__ import annotations

import argparse
from functools import partial

import optuna
from optuna.samplers import CmaEsSampler

from optuna_rig.objective import objective

ROLES = ["mayor", "deacon", "witness", "refinery", "polecat", "crew"]


def create_or_load_study(
    role: str,
    storage: str = "sqlite:///optuna_studies.db",
) -> optuna.Study:
    """Create or resume a CMA-ES study for a role."""
    sampler = CmaEsSampler(seed=42, n_startup_trials=5)
    return optuna.create_study(
        study_name=f"{role}-v1",
        sampler=sampler,
        direction="maximize",
        storage=storage,
        load_if_exists=True,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Optuna CMA-ES hyperparameter optimization for LoRA training"
    )
    parser.add_argument("--role", type=str, required=True, choices=ROLES,
                        help="Role to optimize")
    parser.add_argument("--n-trials", type=int, default=20,
                        help="Number of optimization trials")
    parser.add_argument("--storage", type=str,
                        default="sqlite:///optuna_studies.db",
                        help="Optuna storage URL")
    parser.add_argument("--base-model", type=str,
                        default="Qwen/Qwen2.5-7B-Instruct",
                        help="Base model for evaluation")
    parser.add_argument("--scenarios", type=str, default="eval/prompts",
                        help="Scenarios directory")
    parser.add_argument("--best", action="store_true",
                        help="Show best trial params and exit")
    parser.add_argument("--trials", action="store_true",
                        help="List all trials and exit")
    args = parser.parse_args()

    study = create_or_load_study(args.role, args.storage)

    if args.best:
        if len(study.trials) == 0:
            print(f"No trials yet for {args.role}")
            return
        print(f"Best trial for {args.role}:")
        print(f"  Score: {study.best_value:.3f}")
        print(f"  Params:")
        for k, v in study.best_params.items():
            print(f"    {k}: {v}")
        return

    if args.trials:
        if len(study.trials) == 0:
            print(f"No trials yet for {args.role}")
            return
        print(f"Trials for {args.role}:")
        for t in study.trials:
            status = t.state.name
            value = f"{t.value:.3f}" if t.value is not None else "N/A"
            print(f"  #{t.number}: {status} score={value}")
        return

    print(f"Optimizing {args.role} with {args.n_trials} trials (CMA-ES)")
    obj_fn = partial(
        objective,
        role=args.role,
        base_model=args.base_model,
        scenarios_dir=args.scenarios,
    )
    study.optimize(obj_fn, n_trials=args.n_trials)

    print(f"\nBest trial: #{study.best_trial.number}")
    print(f"  Score: {study.best_value:.3f}")
    for k, v in study.best_params.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
