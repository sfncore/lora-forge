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

# Sync training data
rsync -avz output/datasets/gastown_train.jsonl "${REMOTE}:${REMOTE_DIR}/output/datasets/"
rsync -avz output/datasets/gastown_val.jsonl "${REMOTE}:${REMOTE_DIR}/output/datasets/"

echo "Done. SSH into ${REMOTE} and run:"
echo "  cd ${REMOTE_DIR}"
echo "  source /workspace/venv/bin/activate"
echo "  axolotl train configs/base.yml"
