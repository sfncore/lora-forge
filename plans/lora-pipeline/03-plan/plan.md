# Plan: LoRA Training Pipeline Rig (`lora-forge`)

## Context

We want to fine-tune a single LLM to excel at Gas Town agent roles (mayor, deacon, witness, refinery, polecat, crew). Architecture: centralized LoRA training on GPU, deploy adapters to Petals inference swarm. This machine (WSL2) has no GPU — the data pipeline runs locally, training runs on cloud GPU.

## Tool Selection

**Training framework: Axolotl** (11.3k stars, Apache 2.0)
- YAML-config driven — agents can modify configs without touching Python
- Built-in support for sharegpt/chatml data formats
- Supports unsloth backend for 2-5x speedup (optional)
- QLoRA on 24GB GPU supported
- Active maintenance (Feb 2026)

**Why not others:**
- unsloth (52.7k stars): Library, not standalone — used as Axolotl backend instead
- LLaMA Factory (67.5k stars): Too heavy, GUI-oriented, Chinese docs
- torchtune (5.7k stars): Imperative Python, less automation-friendly
- TRL (17.4k stars): Library — add later for DPO/GRPO phase

**Supporting tools:**
- HuggingFace `datasets` + `transformers` — data loading, tokenization
- `tiktoken` — token counting for chunking
- `wandb` — training monitoring
- `lm-evaluation-harness` — standard benchmarks (later)

## Rig Structure

**New repo: `sfncore/lora-forge`** (not a fork — keeps codebase focused on Gas Town pipeline, uses Axolotl as pip dependency). Beads prefix: `lf`.

```
sfncore/lora-forge/
├── README.md
├── CLAUDE.md                       # Agent instructions
├── pyproject.toml                  # CPU deps (data pipeline)
├── requirements-gpu.txt            # GPU deps (axolotl, torch, peft)
├── .gitignore
│
├── data/
│   ├── extract/
│   │   ├── sessions.py             # Claude session JSONL → turns
│   │   └── observers.py            # Claude-mem observations → knowledge
│   ├── transform/
│   │   ├── chat_formatter.py       # → sharegpt JSONL (Axolotl input)
│   │   ├── chunker.py              # Sliding window, tool-call boundaries
│   │   ├── role_tagger.py          # Session path → canonical role
│   │   ├── tool_normalizer.py      # tool_use/tool_result → XML format
│   │   ├── quality_filter.py       # Remove boilerplate, low-signal turns
│   │   └── deduplicator.py         # Content-hash dedup
│   ├── validate/
│   │   ├── schema.py               # Validate output format
│   │   └── stats.py                # Dataset statistics
│   ├── pipeline.py                 # Orchestrator: extract → transform → validate
│   └── Makefile                    # make extract, make all, make stats
│
├── configs/
│   ├── base.yml                    # Axolotl config: QLoRA, rank 64, Qwen 2.5 7B
│   └── roles/                      # Per-role overrides (mayor.yml, deacon.yml, etc.)
│
├── eval/
│   ├── role_bench.py               # Gas Town role-specific evaluation
│   ├── tool_use_accuracy.py        # Tool call format + correctness scoring
│   └── prompts/                    # 10-20 scenarios per role (JSONL)
│
├── deploy/
│   ├── upload_hf.py                # Push adapter to HuggingFace Hub
│   └── README.md                   # Deployment runbook
│
├── scripts/
│   ├── sync_data.sh                # rsync datasets to GPU machine
│   ├── run_train.sh                # SSH + launch axolotl train
│   └── pull_adapter.sh             # rsync adapter back
│
├── infra/
│   ├── Dockerfile.train            # Reproducible training container
│   └── runpod_setup.sh             # Cloud GPU instance setup
│
└── output/                         # gitignored
    ├── datasets/                   # Processed training data
    ├── checkpoints/                # Model checkpoints
    └── adapters/                   # Final LoRA adapters
```

## Data Pipeline

### Sources (all on this machine)

| Source | Location | Volume | Value |
|--------|----------|--------|-------|
| Claude sessions | `~/.claude/projects/-home-ubuntu-gt-*/*.jsonl` | ~300 files, ~139MB | HIGH |
| Claude-mem observations | `~/.claude/projects/-home-ubuntu--claude-mem-observer-sessions/` | 1,352 files | MEDIUM |
| Beads | `~/gt/.beads/issues.jsonl` | 246 issues | LOW-MEDIUM |

### Extraction (`data/extract/sessions.py`)

- Parse each session JSONL line
- Keep `type: "user"` and `type: "assistant"` records only
- For assistant content blocks: extract `text` and `tool_use` blocks, skip `thinking`
- Load tool results from `[sessionId]/tool-results/[toolUseId].txt` or inline `tool_result`

### Transformation Pipeline

1. **Role tagging** — map session directory path to canonical role (mayor/deacon/witness/refinery/polecat/crew)
2. **Tool normalization** — standardize tool_use/tool_result to XML tags: `<tool_call>` / `<tool_result>`
3. **Chunking** — sliding window of 8 turn-pairs (16 turns), 50% overlap, max 4096 tokens. Never split mid tool-call. Always prefix with role system prompt
4. **Quality filtering** — remove startup boilerplate, empty sessions, error-only sequences. Weight multi-step task completions higher
5. **Deduplication** — content-hash on assistant responses (many sessions start identically)
6. **Format** — output sharegpt JSONL for Axolotl:
```json
{"conversations": [
  {"from": "system", "value": "[GAS TOWN ROLE: mayor] ..."},
  {"from": "human", "value": "..."},
  {"from": "gpt", "value": "..."}
], "metadata": {"role": "mayor", "session_id": "...", "quality_score": 0.85}}
```

## Training Configuration

**Base model**: Qwen 2.5 7B Instruct (strong coding/tool-use, fits 24GB GPU with QLoRA)
**Fallback**: Llama 3.1 8B Instruct

**Key LoRA params** (`configs/base.yml`):
- `adapter: qlora`, `load_in_4bit: true`
- `lora_r: 64`, `lora_alpha: 128`, `lora_dropout: 0.05`
- Target all linear layers (q/k/v/o/gate/up/down_proj)
- `sequence_len: 4096`, `sample_packing: true`
- `learning_rate: 2e-4`, `num_epochs: 3`, `micro_batch_size: 2`
- `bf16: auto`, `flash_attention: true`

**Training strategy**:
- Phase 1: Single "all-roles" adapter on full dataset
- Phase 2: Per-role adapters, compare against all-roles
- Phase 3 (future): DPO/GRPO using beads task-completion signals

**Estimated cost**: ~$2-5 on RunPod A100 (1-3 hours for ~1000 samples)

## Implementation Steps

### Step 1: Create repo and rig
- Create `sfncore/lora-forge` on GitHub
- `gt rig add lora-forge` + `bd init` with prefix `lf`
- Set up pyproject.toml, .gitignore, README

### Step 2: Build data extraction (`data/extract/`)
- `sessions.py` — parse Claude session JSONL, extract user/assistant turns
- Test against largest session file (16MB, 8644 lines)

### Step 3: Build transformation pipeline (`data/transform/`)
- `role_tagger.py`, `tool_normalizer.py`, `chunker.py`
- `quality_filter.py`, `deduplicator.py`, `chat_formatter.py`

### Step 4: Build pipeline orchestrator + validation
- `pipeline.py` — wire extract → transform → validate
- `validate/schema.py` — verify Axolotl format compliance
- `validate/stats.py` — print dataset statistics
- `Makefile` for easy invocation

### Step 5: Write training configs
- `configs/base.yml` + per-role overrides
- `infra/Dockerfile.train` + `infra/runpod_setup.sh`
- `scripts/sync_data.sh`, `run_train.sh`, `pull_adapter.sh`

### Step 6: Build evaluation framework
- `eval/prompts/` — 10 scenarios per role
- `eval/role_bench.py` — scenario runner + scoring
- `eval/tool_use_accuracy.py` — tool call format validation

### Step 7: Run training (requires GPU)
- Provision cloud GPU, sync data, launch Axolotl
- Monitor via WandB
- Pull adapter, run evals, upload to HF Hub

## Verification

1. `make all` in `data/` — produces `output/datasets/gastown_train.jsonl`
2. `python -m data.validate.stats` — shows sample counts, role distribution, token stats
3. `axolotl validate configs/base.yml` — config passes validation (CPU-only check)
4. `python -m eval.role_bench --model base` — baseline scores
5. After training: `python -m eval.role_bench --model output/adapters/gastown-v1` — improved scores
