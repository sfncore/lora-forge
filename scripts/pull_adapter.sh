#!/bin/bash
# Pull trained LoRA adapter from remote GPU machine.
# Usage: ./scripts/pull_adapter.sh user@gpu-host [checkpoint-name] [role]

set -euo pipefail

REMOTE="${1:?Usage: $0 user@gpu-host [checkpoint-name]}"
CHECKPOINT="${2:-mayor-v1}"
REMOTE_DIR="/workspace/lora-forge/output/checkpoints/${CHECKPOINT}"
LOCAL_DIR="output/adapters/${CHECKPOINT}"
ROLE="${3:-mayor}"

echo "Pulling adapter from ${REMOTE}:${REMOTE_DIR}..."

mkdir -p "$LOCAL_DIR"

# Pull the adapter files (small: adapter_model.safetensors + config)
rsync -avz "${REMOTE}:${REMOTE_DIR}/adapter_model.safetensors" "$LOCAL_DIR/" 2>/dev/null || true
rsync -avz "${REMOTE}:${REMOTE_DIR}/adapter_config.json" "$LOCAL_DIR/" 2>/dev/null || true
rsync -avz "${REMOTE}:${REMOTE_DIR}/tokenizer*" "$LOCAL_DIR/" 2>/dev/null || true
rsync -avz "${REMOTE}:${REMOTE_DIR}/special_tokens_map.json" "$LOCAL_DIR/" 2>/dev/null || true

echo "Adapter saved to: ${LOCAL_DIR}"
ls -lh "$LOCAL_DIR"
