# lora-forge — Gas Town LoRA Training Pipeline

## What This Is

A per-role LoRA fine-tuning pipeline for Gas Town agents.
The goal: train a dedicated LoRA adapter per Gas Town role (mayor, deacon, witness, refinery, polecat, crew) on Qwen 2.5 7B, with hyperparameters optimized by the Optuna rig using CMA-ES.

## Key Commands

```bash
# Data pipeline (CPU only, runs locally)
make -C data extract      # Extract from session transcripts
make -C data transform    # Apply transformations (chunk, filter, format)
make -C data validate     # Validate output format
make -C data all          # Full pipeline
make -C data stats        # Print dataset statistics

# Training (requires GPU)
axolotl train configs/roles/mayor.yml   # Train a specific role adapter
axolotl train configs/base.yml          # Train the shared base adapter
```

## Architecture

- Data extraction runs on any machine (CPU only, pure Python)
- Training runs on cloud GPU (RunPod A100 or similar)
- Trained per-role LoRA adapters are uploaded to HuggingFace Hub
- Petals swarm serves the base model, agents load their role-specific adapter client-side
- Optuna rig handles hyperparameter optimization (CMA-ES sampler) using role_bench eval scores

## Data Sources

Training data comes from Gas Town session transcripts stored at:
- `~/.claude/projects/-home-ubuntu-gt-*/*.jsonl` — Claude session files
- `~/.claude/projects/-home-ubuntu--claude-mem-observer-sessions/` — Observations

## Important

- Do NOT commit training data or model weights to this repo
- All generated output goes to `output/` (gitignored)
- The `configs/` directory contains Axolotl YAML — these are the source of truth for training
- Use sharegpt JSONL format for all training data
