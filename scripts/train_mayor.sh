#!/bin/bash
# Train mayor LoRA adapter on scored data
# Usage: ./scripts/train_mayor.sh [gpu-host]

set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Usage: $0 [gpu-host]"
    echo "If no host provided, runs locally (requires GPU)"
    exit 1
fi

GPU_HOST="${1:-}"

if [ -n "$GPU_HOST" ]; then
    echo "Syncing data to GPU host: $GPU_HOST"
    ./scripts/sync_data.sh "$GPU_HOST"
    
    echo "Starting remote training..."
    ssh "$GPU_HOST" "cd /workspace/lora-forge && source /workspace/venv/bin/activate && axolotl train configs/roles/mayor.yml"
    
    echo "Training completed. Syncing results back..."
    rsync -avz "$GPU_HOST:/workspace/lora-forge/output/checkpoints/mayor-v1/" "output/adapters/mayor-v1-scored/"
else
    echo "Running training locally..."
    axolotl train configs/roles/mayor.yml
    cp -r output/checkpoints/mayor-v1/* output/adapters/mayor-v1-scored/
fi

echo "Training completed successfully!"
echo "Adapter saved to: output/adapters/mayor-v1-scored/"