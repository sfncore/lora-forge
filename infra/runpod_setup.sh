#!/bin/bash
# Setup script for RunPod GPU instance (A100 40GB or L40S 48GB)
# Run this once after SSH'ing into the instance.

set -euo pipefail

echo "=== Setting up lora-forge training environment ==="

# System packages
apt-get update && apt-get install -y git-lfs

# Python environment
python3 -m venv /workspace/venv
source /workspace/venv/bin/activate

# Core ML packages
pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install "axolotl[flash-attn]>=0.5.0"
pip install wandb

# Optional: unsloth for 2-5x speedup
# pip install unsloth

echo "=== Environment ready ==="
echo "Activate with: source /workspace/venv/bin/activate"
echo "Train with: cd /workspace/lora-forge && axolotl train configs/base.yml"
