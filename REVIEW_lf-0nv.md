# Review: Training Configs and Infrastructure (lf-0nv)

## Files Reviewed
- `configs/base.yml` - Base LoRA training configuration
- `configs/roles/*.yml` - Per-role configs (mayor, deacon, witness, refinery, polecat, crew)
- `infra/Dockerfile.train` - Training container image
- `infra/runpod_setup.sh` - RunPod instance setup
- `scripts/pull_adapter.sh` - Adapter retrieval script
- `scripts/sync_data.sh` - Data synchronization script
- `data/Makefile` - Data pipeline orchestration
- `data/pipeline.py` - Pipeline implementation
- `README.md` - Project documentation
- `pyproject.toml` - Python package manifest

## Findings

### 1. configs/base.yml
✅ **Well-structured** - Complete Axolotl configuration with:
- QLoRA 4-bit quantization (r=64, alpha=128)
- Flash attention enabled
- ShareGPT format with chatml conversation style
- Proper checkpointing and WandB monitoring

### 2. configs/roles/*.yml
⚠️ **Inconsistent target modules** - All role configs use `lora_target_linear: true` without explicit `lora_target_modules` list. Base config has the full explicit list.

✅ **Good separation** - Each role has distinct:
- Dataset paths (`output/datasets/{role}_train.jsonl`)
- Output directories (`output/checkpoints/{role}-v1`)
- WandB names for tracking

⚠️ **Training differences noted**:
- Mayor, Deacon, Witness, Refinery: 3 epochs, warmup_steps=50
- Polecat, Crew: 4 epochs, warmup_steps=30, eval_steps=25 (more intensive training)

### 3. infra/Dockerfile.train
✅ **Good practices**:
- Uses CUDA 12.1 base image
- Installs axolotl with flash-attention
- Sets up Python venv
- Copies configs and datasets

### 4. infra/runpod_setup.sh
✅ **Complete setup** for RunPod A100/L40S instances

### 5. scripts/pull_adapter.sh
⚠️ **Issue**: Default checkpoint name is `gastown-v1` but role configs output to `mayor-v1`, `polecat-v1`, etc.

### 6. scripts/sync_data.sh
🐛 **Bug**: Only syncs `gastown_train.jsonl` and `gastown_val.jsonl`. Role-specific datasets (`mayor_train.jsonl`, `polecat_train.jsonl`, etc.) are NOT synced, making per-role training fail on remote GPU.

### 7. data/Makefile & pipeline.py
✅ **Clean structure** - Extract → Transform → Validate pipeline
✅ **Proper logging** throughout

### 8. pyproject.toml
✅ **Good dependency management** - Separates CPU and GPU dependencies

## Recommendations

1. **Fix scripts/sync_data.sh**: Add wildcard sync for role datasets:
   ```bash
   rsync -avz output/datasets/*_train.jsonl "${REMOTE}:${REMOTE_DIR}/output/datasets/"
   ```

2. **Fix scripts/pull_adapter.sh**: Support pulling all role adapters or update default.

3. **Standardize role configs**: Either all use `lora_target_linear: true` OR all list explicit modules.

4. **Add executable permissions**: `chmod +x scripts/*.sh infra/*.sh`

## Overall Assessment
The infrastructure is well-designed for the Gas Town LoRA training pipeline. The main issue is the sync script not handling role-specific datasets, which would block per-role training workflows.
