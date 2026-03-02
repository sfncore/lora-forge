# Pi-Rust prompt_mode Findings (2026-02-26)

## Discovery

pir (pi-rust 0.1.7) behaves differently from claude/omp with positional args:

| Command | `pir "do something"` | `claude "do something"` | `omp "do something"` |
|---------|---------------------|------------------------|---------------------|
| Behavior | Process & **exit** | Interactive TUI | Interactive TUI |
| prompt_mode | `"none"` | `"arg"` | `"arg"` |
| Delivery | NudgeSession (tmux) | Positional arg | Positional arg |

## Why pir Exits

pir treats positional args as print-mode input. It processes the message,
outputs a response, and exits with code 0. The `-p` flag exists for explicit
print mode, but positional args trigger the same behavior.

This means `prompt_mode: "arg"` causes Gas Town agents to:
1. Start pir with the beacon as positional arg
2. pir processes the beacon, responds once
3. pir exits — session gone, agent dead

## Correct Configuration

```json
{
  "pi-kimi": {
    "command": "pir",
    "prompt_mode": "none",
    "tmux": {
      "ready_delay_ms": 8000
    }
  }
}
```

With `"none"`, gt:
1. Starts pir WITHOUT positional arg — TUI launches and waits
2. Waits `ready_delay_ms` for TUI initialization
3. Calls `NudgeSession()` which sends beacon via tmux `send-keys` + `Enter`
4. pir receives it as user input, processes it, stays in TUI

## Extension Events

pir loads extensions (shown in `resources: N extensions`) but:

| Event | Fires? | Notes |
|-------|--------|-------|
| `startup` | No | Never fires — gastown-hook.js startup handler is a no-op |
| `tool_call` | Yes | Fires during processing (used for git push guards) |
| `agent_end` | Yes | Fires when agent completes a turn (used for cost recording) |

The gastown-hook.js still has value for `tool_call` and `agent_end`, but
context injection happens entirely through NudgeSession.

## Validation

```bash
gt config agent check --verbose   # pir agents should show prompt_mode=none
gt doctor                         # Includes prompt-mode check
```
