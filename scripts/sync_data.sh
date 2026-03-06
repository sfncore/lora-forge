#!/bin/bash
# Sync training data to a remote GPU machine.
# Usage: ./scripts/sync_data.sh user@gpu-host

set -euo pipefail

REMOTE="${1:?Usage: $0 user@gpu-host}"
REMOTE_DIR="/workspace/lora-forge"

echo "Syncing training data to ${REMOTE}:${REMOTE_DIR}..."

# Create remote directory structure
ssh "$REMOTE" "mkdir -p ${REMOTE_DIR}/output/datasets ${REMOTE_DIR}/configs/roles"

# Sync configs
rsync -avz configs/ "${REMOTE}:${REMOTE_DIR}/configs/"

# Sync all datasets (per-role + combined), excluding Axolotl cache
rsync -avz --exclude='prepared*' output/datasets/ "${REMOTE}:${REMOTE_DIR}/output/datasets/"

# Sync eval framework and optuna rig
rsync -avz eval/ "${REMOTE}:${REMOTE_DIR}/eval/"
rsync -avz pyproject.toml "${REMOTE}:${REMOTE_DIR}/"
[ -d optuna_rig ] && rsync -avz optuna_rig/ "${REMOTE}:${REMOTE_DIR}/optuna_rig/"

echo "Done. SSH into ${REMOTE} and run:"
echo "  cd ${REMOTE_DIR}"
echo "  source /workspace/venv/bin/activate"
echo "  axolotl train configs/roles/<role>.yml  # e.g. mayor, deacon, witness"
