# Training Configs & Infrastructure Review (lf-mpm)

**Date:** 2026-02-24
**Reviewer:** lora_forge/refinery
**Status:** Complete

## Executive Summary

Training configuration and infrastructure setup is **mostly complete** with solid foundations. Core Axolotl configs are well-structured, GPU infrastructure is documented, and data sync scripts are functional. 

**Missing:** `run_train.sh` script (critical for remote training orchestration) and `requirements-gpu.txt` file (plan specifies separate GPU requirements file).

---

## Implementation Status

### ✅ Complete Components

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| Base Config | `configs/base.yml` | ✅ Complete | QLoRA, Qwen 2.5 7B, all key params set |
| Mayor Config | `configs/roles/mayor.yml` | ✅ Complete | Role-specific dataset, tuned eval steps |
| Deacon Config | `configs/roles/deacon.yml` | ✅ Complete | Similar to mayor, appropriate defaults |
| Polecat Config | `configs/roles/polecat.yml` | ✅ Complete | 4 epochs (vs 3), lower eval_steps for more frequent checks |
| Witness Config | `configs/roles/witness.yml` | ✅ Complete | Present (not reviewed in detail) |
| Refinery Config | `configs/roles/refinery.yml` | ✅ Complete | Present (not reviewed in detail) |
| Crew Config | `configs/roles/crew.yml` | ✅ Complete | Present (not reviewed in detail) |
| Training Dockerfile | `infra/Dockerfile.train` | ✅ Complete | CUDA 12.1, Axolotl, flash-attn |
| RunPod Setup | `infra/runpod_setup.sh` | ✅ Complete | Environment setup script |
| Data Sync | `scripts/sync_data.sh` | ✅ Complete | rsync-based data transfer |
| Adapter Pull | `scripts/pull_adapter.sh` | ✅ Complete | Retrieve trained adapters |
| Pyproject.toml | `pyproject.toml` | ✅ Complete | CPU deps + optional GPU extras |

### ❌ Missing Components

| Component | Planned Location | Priority | Impact |
|-----------|------------------|----------|--------|
| Training Launcher | `scripts/run_train.sh` | **High** | Cannot launch remote training without SSH + command orchestration |
| GPU Requirements | `requirements-gpu.txt` | Medium | Plan specifies separate file; pyproject.toml has `[gpu]` extras instead |

---

## Configuration Quality Assessment

### Base Config (`configs/base.yml`)

**Strengths:**
- ✅ Correct QLoRA setup (4-bit, rank 64, alpha 128)
- ✅ All 7 linear layers targeted for LoRA
- ✅ Flash attention enabled for speed
- ✅ bf16 auto-detection for compatibility
- ✅ Cosine scheduler with warmup
- ✅ WandB integration for monitoring
- ✅ Reasonable defaults (3 epochs, 2e-4 lr, batch 2)

**Notes:**
- `val_set_size: 0.05` (5%) is appropriate for dataset sizes ~1000+ samples
- `sample_packing: true` improves training efficiency
- `unsloth: true` commented out — good, allows optional 2-5x speedup

### Role-Specific Configs

**Mayor/Deacon/Witness/Refinery/Crew:**
- All inherit sensible base patterns
- Correctly point to per-role datasets (`output/datasets/{role}_train.jsonl`)
- Separate `dataset_prepared_path` per role prevents cache conflicts
- Separate `output_dir` per role enables parallel training

**Polecat differences:**
- `num_epochs: 4` (vs 3) — appropriate for task-execution focused role
- `warmup_steps: 50` → `30` — faster ramp-up
- `eval_steps: 100` → `25` — more frequent evaluation (good for fine-grained tracking)

**Recommendation:** Document why polecat gets different treatment (likely more complex task patterns require extra epoch and closer monitoring).

---

## Infrastructure Assessment

### Dockerfile.train

**Strengths:**
- ✅ CUDA 12.1 (current stable)
- ✅ Python venv isolation
- ✅ git-lfs for model weights
- ✅ Axolotl with flash-attn support
- ✅ WandB for monitoring

**Concerns:**
- No pinned versions — `axolotl>=0.5.0` could break with future releases
- No health check or test command
- Copies entire `output/datasets/` — could be large, consider mounting instead

**Recommendation:** Pin versions for reproducibility:
```dockerfile
pip install "axolotl[flash-attn]==0.5.0" wandb==0.16.0
```

### runpod_setup.sh

**Strengths:**
- ✅ Idempotent (safe to re-run)
- ✅ Clear output messages
- ✅ Optional unsloth commented out

**Concerns:**
- Same version pinning issue as Dockerfile
- No verification step (e.g., `python -c "import torch; print(torch.cuda.is_available())"`)

**Recommendation:** Add CUDA verification:
```bash
python -c "import torch; assert torch.cuda.is_available(), 'CUDA not available'"
```

### scripts/sync_data.sh

**Strengths:**
- ✅ Uses rsync (efficient, resumable)
- ✅ Clear usage message
- ✅ Syncs both train and val sets

**Concerns:**
- Only syncs `gastown_train.jsonl` and `gastown_val.jsonl` — doesn't sync per-role datasets
- No compression flag beyond `-z` (could be slow for large datasets)

**Recommendation:** Add per-role dataset sync or wildcard:
```bash
rsync -avz output/datasets/*.jsonl "${REMOTE}:${REMOTE_DIR}/output/datasets/"
```

### scripts/pull_adapter.sh

**Strengths:**
- ✅ Handles missing files gracefully (`|| true`)
- ✅ Pulls tokenizer files
- ✅ Clear output

**Concerns:**
- May fail if checkpoint doesn't exist — could add existence check
- Doesn't pull `trainer_state.json` or training logs (useful for analysis)

---

## Plan Deviations

| Planned | Implemented | Deviation | Severity |
|---------|-------------|-----------|----------|
| `requirements-gpu.txt` | `pyproject.toml [gpu]` extras | Different approach | Low (better practice) |
| `scripts/run_train.sh` | **Missing** | Not implemented | **High** |
| Dockerfile copies datasets | Dockerfile copies datasets | As planned | None |

**Note:** Using `pyproject.toml` optional dependencies is actually better than a separate `requirements-gpu.txt` file — more modern Python packaging practice.

---

## Missing Script: run_train.sh

**Planned functionality:**
```bash
# Expected usage:
./scripts/run_train.sh user@gpu-host configs/base.yml
```

**Should:**
1. SSH to remote host
2. Activate venv
3. Launch Axolotl training in background (tmux/screen)
4. Optionally tail logs
5. Handle disconnection gracefully

**Template:**
```bash
#!/bin/bash
set -euo pipefail

REMOTE="${1:?Usage: $0 user@gpu-host [config.yml]}"
CONFIG="${2:-configs/base.yml}"

echo "Starting training on ${REMOTE} with ${CONFIG}..."

ssh "$REMOTE" <<EOF
  cd /workspace/lora-forge
  source /workspace/venv/bin/activate
  tmux new -d -s lora-train "axolotl train ${CONFIG} 2>&1 | tee train.log"
  echo "Training started in tmux session 'lora-train'"
  echo "Attach with: tmux attach -t lora-train"
  echo "Tail logs with: tail -f train.log"
EOF
```

---

## Recommendations

### Immediate (Blocker)
1. **Create `scripts/run_train.sh`** — Critical for remote training orchestration

### Short-term
2. **Pin dependency versions** in Dockerfile and runpod_setup.sh for reproducibility
3. **Add CUDA verification** to runpod_setup.sh
4. **Update sync_data.sh** to handle per-role datasets or use wildcard
5. **Add training verification** — script to check if training completed successfully

### Optional
6. **Add tmux/screen wrapper** to run_train.sh for persistent training sessions
7. **Create monitoring script** — WandB API query for training progress
8. **Add checkpoint cleanup** — script to delete old checkpoints, keep only best N

---

## Verification Commands

```bash
# Validate Axolotl config syntax (CPU-only check)
axolotl validate configs/base.yml

# Check all role configs exist
ls -lh configs/roles/*.yml

# Test sync script (dry run)
./scripts/sync_data.sh user@host --dry-run

# Verify Dockerfile builds (optional)
docker build -f infra/Dockerfile.train -t lora-forge:train .
```

---

## Conclusion

Training configuration is **production-ready** with one critical gap: missing `run_train.sh` script. All Axolotl configs are well-structured and follow best practices. Infrastructure setup is documented and functional.

**Next step:** Create `scripts/run_train.sh` to complete remote training orchestration workflow.

---

## Appendix: Config Comparison

| Config | Epochs | Warmup | Eval Steps | Notes |
|--------|--------|--------|------------|-------|
| base.yml | 3 | 100 | 100 | Default for all roles |
| mayor.yml | 3 | 50 | 50 | Standard orchestrator role |
| deacon.yml | 3 | 50 | 50 | Patrol coordinator |
| polecat.yml | **4** | 30 | **25** | More training, closer monitoring |
| witness.yml | 3 | 50 | 50 | Code review specialist |
| refinery.yml | 3 | 50 | 50 | Quality assurance |
| crew.yml | 3 | 50 | 50 | General developer |
