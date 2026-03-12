# LoRA Training: Lessons & Gotchas

Practical notes from training Gas Town patrol agents on Qwen3.5-2B.

## Base Model

- **Qwen3.5-2B is a VLM** (vision-language model), not text-only. It has a vision encoder.
- This matters for serving: vLLM < 0.17.0 doesn't support Qwen3.5 at all. OOM on startup was a version issue, not a model size issue.
- vLLM 0.17.1 loads Qwen3.5-2B fine (4.25 GiB, serves on 12GB GPU).

## LoRA Target Modules

- `lora_target_linear: true` targets ALL linear layers — **including the vision encoder**.
- This creates LoRA weights for `visual.blocks.*` which are useless for text-only tasks and causes vLLM LoRA loading to crash (`IndexError: list index out of range`).
- **Fix**: Use explicit `lora_target_modules` listing only text layers:
  ```yaml
  lora_target_modules:
    - q_proj
    - k_proj
    - v_proj
    - o_proj
    - gate_proj
    - up_proj
    - down_proj
  ```
- v3 (all linear): 23M trainable params. v4 (text-only): 10.9M trainable params.

## System Prompt in Training Data

- v3 used a compact ~400 token system prompt. At inference, the model sees the full gt prime (~3700 tokens). This train/inference mismatch is a problem.
- **Fix**: Include the real gt prime in training data. But 750 examples × 3700 tokens = 4096 sequence_len needed.
- **VRAM constraint**: 4096 seq_len on Qwen3.5-2B QLoRA needs ~13.75 GiB — exceeds 12GB GPU, spills to system RAM, 5x slower.
- **Compromise**: Mix — 30% of examples get full gt prime, 70% keep compact prompt. Model learns both contexts.

## Sequence Length vs VRAM (RTX 3060 12GB)

| seq_len | Approx VRAM | Fits 12GB? |
|---------|-------------|------------|
| 2048    | ~8 GiB      | Yes        |
| 4096    | ~13.75 GiB  | No (swaps) |

With sample_packing, peak VRAM depends on the longest sequences in a batch, not the average.

## Dataset Building

- Training data is JSONL with `conversations` field (chatml format: system/human/gpt).
- `build_v3_dataset.py` generates synthetic scenarios via `synthetic_scenarios.py`.
- Easiest way to swap system prompts: simple Python script to replace the `system` message value in each example. No need to regenerate scenarios.
- Axolotl caches prepared datasets in `output/datasets/prepared_<name>/<hash>/`. **You must delete this dir** when changing training data, or axolotl reuses the old tokenized data.

## Serving Options

| Backend | Format | LoRA Support | Notes |
|---------|--------|--------------|-------|
| vLLM | safetensors | Native (`--enable-lora`) | Needs 0.17.0+ for Qwen3.5. LoRA on VLM crashes in 0.17.1. |
| Ollama | GGUF | ADAPTER directive | Needs LoRA converted to GGUF. Base model GGUF has mmproj issues with Qwen3.5. |
| transformers (Python) | safetensors | PEFT `from_pretrained` | Works but loads model per-process. |

## Ollama Gotchas

- Ollama 0.15.4 didn't support Qwen3.5 architecture. Updated to 0.17.7.
- "No Qwen3.5 GGUF works in Ollama due to separate mmproj vision files" — manually converted GGUFs may not load correctly.
- `ollama pull qwen3.5:2b` uses Ollama's own build, which handles mmproj correctly.
- When model responds with Minecraft advice instead of JSON tool calls, the system prompt from the Modelfile isn't being applied.

## Resource Management

- Kill Dolt (`gt dolt stop`) before training to free ~1.4GB RAM.
- Kill vLLM/Ollama before training to free GPU.
- `nvidia-smi --query-compute-apps=pid,name,used_memory --format=csv,noheader` to check what's on GPU.
- Watch for `memory/max_allocated` in training logs — if it exceeds physical VRAM, training spills to system RAM and slows 5x+.
