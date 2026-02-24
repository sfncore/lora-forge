# lora-forge — Gas Town LoRA Training Pipeline

## What This Is

A training data pipeline and LoRA fine-tuning configuration for Gas Town agent roles.
The goal: fine-tune a model that excels at being a Gas Town agent (mayor, deacon, witness, refinery, polecat, crew).

## Key Commands

```bash
# Data pipeline (CPU only, runs locally)
make -C data extract      # Extract from session transcripts
make -C data transform    # Apply transformations (chunk, filter, format)
make -C data validate     # Validate output format
make -C data all          # Full pipeline
make -C data stats        # Print dataset statistics

# Training (requires GPU)
axolotl train configs/base.yml
```

## Architecture

- Data extraction runs on any machine (CPU only, pure Python)
- Training runs on cloud GPU (RunPod A100 or similar)
- Trained LoRA adapters are uploaded to HuggingFace Hub
- Petals swarm serves the base model, agents load adapters client-side

## Data Sources

Training data comes from Gas Town session transcripts stored at:
- `~/.claude/projects/-home-ubuntu-gt-*/*.jsonl` — Claude session files
- `~/.claude/projects/-home-ubuntu--claude-mem-observer-sessions/` — Observations

## Important

- Do NOT commit training data or model weights to this repo
- All generated output goes to `output/` (gitignored)
- The `configs/` directory contains Axolotl YAML — these are the source of truth for training
- Use sharegpt JSONL format for all training data
