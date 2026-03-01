# Multi-Harness Training Data Plan

## Current State

lora_forge has a complete extract → transform → train pipeline, but it only reads
Claude Code transcripts (`~/.claude/projects/`). Three agent runtimes produce
session data in different formats:

| Runtime | Session Location | Format | Sessions | Extracted? |
|---------|-----------------|--------|----------|-----------|
| Claude Code | `~/.claude/projects/` | Claude JSONL | ~100s | Yes (existing) |
| pir (pi-rust) | `~/.pi/agent/sessions/` | Pi JSONL v3 | 726+ | **No** |
| omp | `~/.claude/projects/` (via Claude Code) | Claude JSONL | ~50s | Partial |

## Phase 1: Unlock Existing pir Data (P0)

### 1a. Pi-Rust Session Extractor

**File**: `data/extract/pir_sessions.py`

Parse pir's JSONL v3 format into the same `ExtractedSession` / `Turn` dataclasses
the transform pipeline already expects. See `crew-docs/pir-session-format.md` for
the full format reference.

Key implementation notes:
- Use SQLite index (`session-index.sqlite`) for fast discovery
- Map `role=user` → human, `role=assistant` → gpt, `role=toolResult` → tool_result
- Extract tool calls from `content[].type=toolCall` blocks
- Capture `usage` (input/output tokens) as per-turn metadata
- Role detection from CWD path encoding (`--home-ubuntu-gt-deacon--` → deacon)

### 1b. OMP Session Verification

omp uses Claude Code under the hood — verify its sessions are already captured
by the existing Claude extractor. If not, add omp-specific metadata extraction.

### 1c. Unified Pipeline

Update `data/pipeline.py`:
```python
def run_pipeline(sources=["claude", "pir", "omp"], ...):
    sessions = []
    if "claude" in sources:
        sessions += extract_claude_sessions(claude_dir)
    if "pir" in sources:
        sessions += extract_pir_sessions(pir_dir)
    # ... rest unchanged
```

## Phase 2: Training-Aware Extensions (P1)

pir doesn't fire `startup` but DOES fire `tool_call` and `agent_end` during
processing. Build extensions that capture richer training signals:

### 2a. Training Signal Capture Extension

```javascript
// .pi/extensions/training-capture.js
export default (pi) => {
  const signals = [];

  pi.on("tool_call", async (event) => {
    signals.push({
      ts: Date.now(),
      tool: event.toolName,
      args_keys: Object.keys(event.input || {}),
    });
  });

  pi.on("agent_end", async () => {
    const signalFile = `/tmp/gt-training-signals-${process.pid}.jsonl`;
    for (const s of signals) {
      await pi.exec("bash", ["-c",
        `echo '${JSON.stringify(s)}' >> ${signalFile}`]);
    }
  });
};
```

Captures: tool sequences, error recovery patterns, session duration.

### 2b. Outcome Tagging Extension

Link sessions to bead outcomes:
- On `agent_end`, check if session closed any beads
- Tag session with bead IDs and final status
- Feeds into v1.5 outcome-based quality scoring

## Phase 3: Upstream pir Improvements

File issues on pi_agent_rust for:

1. **`startup` extension event** — fire before first user turn (CRITICAL for clean
   context injection, eliminates NudgeSession/tmux hacks)
2. **Interactive positional args** — `pir "prompt"` should stay in TUI, not exit
3. **`pir session export --format sharegpt`** — built-in clean export
4. **Extension stderr logging** — `console.error` goes nowhere currently
5. **Machine-readable ready signal** — replace dumb `ready_delay_ms: 8000` sleep

## Phase 4: Rich Training Data (P2-3)

### 4a. Bead-Session Linkage

Connect: Session (transcript) ←→ Bead (task outcome) ←→ Git Diff (code change)

Enables outcome-based scoring per `sf_workflows/training-data-improvement.md`:
- v1.5: Score sessions by bead lifecycle (closed on first attempt = high quality)
- v2: Agent-assisted curation (deacon/witness score during patrol)
- v3: DPO preference pairs (good session vs bad for same task type)

### 4b. Synthetic Data Generation

Use pir print mode for controlled training examples:
```bash
pir -p --system-prompt "[GAS TOWN ROLE: witness]..." \
  "Run gt prime --hook and begin patrol" \
  --tools read,bash,edit,write,grep,find,ls
```

Fill gaps in underrepresented roles.

### 4c. Thinking Traces

pir supports `--thinking` levels (off → xhigh). Sessions with thinking enabled
contain chain-of-thought reasoning — high value for training. Quality filter
should boost score for thinking-enabled sessions.

## Phase 5: Evaluation & Feedback Loop (P3-4)

- Extract best patrol cycles and bead closures as `eval/prompts/` scenarios
- A/B test models as agents (pi-kimi vs pi-qwen), compare outcomes
- Winner sessions become DPO preference data
- Recursive loop: train → deploy → capture → score → retrain

## Implementation Priority

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| P0 | pir session extractor | 2-3 days | Unlocks 726+ sessions |
| P0 | Unified pipeline entry | 1 day | Makes pir data trainable |
| P1 | Training capture extension | 1-2 days | Richer signals per session |
| P1 | File upstream issues | 1 day | Unblocks clean integration |
| P2 | Bead-session linkage | 3-5 days | Outcome-based scoring |
| P3 | Synthetic data gen | 2-3 days | Fill role gaps |
| P4 | Eval benchmarks + A/B | 1 week | Measure improvement |
