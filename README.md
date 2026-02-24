# lora-forge

LoRA fine-tuning pipeline for Gas Town agent roles. Extracts training data from Gas Town session transcripts, trains LoRA adapters using Axolotl, and deploys them to a Petals inference swarm.

## Architecture

```
Session Transcripts → Data Pipeline → Axolotl Training → LoRA Adapter → Petals Swarm
     (this machine)     (this repo)      (cloud GPU)       (HF Hub)      (distributed)
```

## Quick Start

```bash
# Extract and process training data (CPU only)
make -C data all

# View dataset statistics
python -m data.validate.stats

# Training (requires GPU — see infra/ for cloud setup)
axolotl train configs/base.yml
```

## Structure

- `data/` — Training data extraction and processing pipeline
- `configs/` — Axolotl training configurations (QLoRA, per-role)
- `eval/` — Gas Town role-specific evaluation framework
- `deploy/` — Adapter export and deployment to Petals/HF Hub
- `scripts/` — Remote training orchestration scripts
- `infra/` — Cloud GPU setup (RunPod, Docker)

## Training Data Sources

- **Claude session transcripts** — Agent conversations with tool use
- **Claude-mem observations** — Distilled knowledge and decisions
- **Beads database** — Task descriptions and outcomes

## Goal

Fine-tune a single model (Qwen 2.5 7B) to excel at Gas Town agent roles:
mayor, deacon, witness, refinery, polecat, crew.
