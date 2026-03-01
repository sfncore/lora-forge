# Gas Town Benchmark (GTBench)

## What Makes This Different

Existing benchmarks test "can you code." GTBench tests "can you be an autonomous
agent in a multi-agent system." No benchmark measures this today.

It tests the full stack: role understanding, tool orchestration, protocol adherence,
multi-turn reasoning, cost efficiency, error recovery, and coordination — all in
a real infrastructure, not a sandbox simulation.

## Evaluation Dimensions

### 1. Role Competence
Does the agent understand its role and execute the right workflow?

| Role | Core Task | Pass Criteria |
|------|-----------|--------------|
| Witness | Patrol cycle | Runs prime, checks hook, executes patrol steps, handles wisps |
| Refinery | Code review + merge | Reads MQ, reviews diff, runs tests, merges or rejects |
| Deacon | Orchestration | Heartbeat, spawn witnesses/refineries, manage lifecycle |
| Polecat | Bead execution | Pins wisp, attaches molecule, executes steps, calls done |
| Mayor | Triage + decisions | Reads hook, prioritizes work, delegates to correct role |
| Boot | Startup triage | Scans rigs, spawns deacon, exits cleanly |
| Crew | Directed work | Follows bead instructions, commits, pushes, calls done |

### 2. Tool Orchestration
Does it chain gt/bd commands correctly?

- `gt prime --hook` → read context before acting
- `bd pin` → `bd close` → `gt done` lifecycle
- `gt mail check` → `gt mail send` for coordination
- Git workflow: status → add → commit → push
- Correct tool for the job (grep vs read vs bash)

### 3. Protocol Adherence
Does it follow Gas Town conventions?

- Propulsion Principle: find work → do it (no announcing)
- Check hook before mail
- Commit and push before `gt done`
- Don't modify files outside your rig
- Escalate when stuck, don't loop

### 4. Multi-Turn Reasoning
Can it sustain coherent work across 5-20 tool calls?

- Read error output → diagnose → fix → verify
- Parse bead description → break into steps → execute each
- Handle unexpected state (dirty git, missing files, failed tests)

### 5. Cost Efficiency
How many tokens to complete the task?

- Baseline: best observed session for same scenario
- Score: `baseline_tokens / actual_tokens` (1.0 = optimal, <1.0 = wasteful)
- Penalize: repeated commands, unnecessary reads, verbose output

### 6. Error Recovery
When something goes wrong, does it adapt?

- Tool call returns error → tries different approach (not same command again)
- Git conflict → resolves (not force push)
- Missing file → searches for it (not hallucinate path)
- API timeout → retries with backoff (not crash)

---

## Scenario Format

```json
{
  "id": "gtbench-witness-patrol-001",
  "version": 1,
  "role": "witness",
  "category": "patrol",
  "difficulty": "standard",
  "description": "Standard witness patrol with one stuck bead",

  "setup": {
    "rig": "sandbox",
    "beads": [
      {"id": "sb-001", "title": "Fix README typo", "status": "open",
       "assignee": "crew/mel", "stuck_since": "2h"}
    ],
    "hook": null,
    "mail": [],
    "git_state": "clean",
    "files": {
      "README.md": "# Project\n\nThis is a tset project.\n"
    }
  },

  "beacon": "[GAS TOWN] witness (rig: sandbox) <- deacon • {date} • patrol\nRun `gt prime --hook` and begin patrol.",

  "eval": {
    "required": [
      {"action": "runs_command", "pattern": "gt prime", "description": "Initializes context"},
      {"action": "runs_command", "pattern": "gt hook|bd list", "description": "Checks for work"},
      {"action": "detects_issue", "pattern": "sb-001|stuck|README", "description": "Finds stuck bead"},
      {"action": "runs_command", "pattern": "gt done|gt witness done", "description": "Completes patrol"}
    ],
    "bonus": [
      {"action": "runs_command", "pattern": "gt mail send.*deacon", "description": "Reports stuck bead to deacon"},
      {"action": "runs_command", "pattern": "gt mail check", "description": "Checks mail"}
    ],
    "forbidden": [
      {"action": "runs_command", "pattern": "git push --force", "description": "No force push"},
      {"action": "runs_command", "pattern": "rm -rf", "description": "No destructive operations"},
      {"action": "modifies_file", "pattern": "README.md", "description": "Witness doesn't fix — it reports"}
    ],
    "max_turns": 20,
    "max_tokens": 30000,
    "time_limit_seconds": 120
  },

  "scoring": {
    "required_weight": 0.6,
    "bonus_weight": 0.2,
    "efficiency_weight": 0.1,
    "no_forbidden_weight": 0.1
  },

  "gold_sessions": ["session-id-of-best-real-patrol"],
  "tags": ["patrol", "stuck-bead", "standard"]
}
```

---

## Scenario Categories

### Witness Scenarios
| ID | Scenario | Difficulty |
|----|----------|-----------|
| W-001 | Clean patrol (no issues) | Easy |
| W-002 | Patrol with stuck bead | Standard |
| W-003 | Patrol with mail to process | Standard |
| W-004 | Patrol with orphaned session | Hard |
| W-005 | Patrol with git divergence across rigs | Hard |

### Refinery Scenarios
| ID | Scenario | Difficulty |
|----|----------|-----------|
| R-001 | Clean merge (tests pass) | Easy |
| R-002 | Merge with test failures | Standard |
| R-003 | Merge with conflicts | Hard |
| R-004 | Merge with security issue in diff | Hard |
| R-005 | Reject bad PR with constructive feedback | Standard |

### Polecat Scenarios
| ID | Scenario | Difficulty |
|----|----------|-----------|
| P-001 | Simple bead (fix typo) | Easy |
| P-002 | Multi-step bead (add feature) | Standard |
| P-003 | Bead with failing tests | Standard |
| P-004 | Bead that requires investigation first | Hard |
| P-005 | Bead that should be escalated | Hard |

### Deacon Scenarios
| ID | Scenario | Difficulty |
|----|----------|-----------|
| D-001 | Normal patrol (heartbeat + spawn) | Standard |
| D-002 | Recover from crashed witness | Hard |
| D-003 | Handle orphan sessions | Standard |
| D-004 | Spawn polecats from MQ | Standard |
| D-005 | Coordinate convoy across rigs | Hard |

### Mayor Scenarios
| ID | Scenario | Difficulty |
|----|----------|-----------|
| M-001 | Triage incoming bead | Standard |
| M-002 | Design decision with trade-offs | Hard |
| M-003 | Escalation from polecat | Standard |
| M-004 | Cross-rig coordination | Hard |
| M-005 | Cost optimization (choose cheaper model for task) | Hard |

### Cross-Role Scenarios
| ID | Scenario | Difficulty |
|----|----------|-----------|
| X-001 | Full boot → deacon → witness cascade | Hard |
| X-002 | Polecat escalates → mayor decides → crew executes | Hard |
| X-003 | Witness detects → refinery merges → witness verifies | Hard |

---

## Execution Modes

### Mode 1: Offline Evaluation (fast, cheap)
- Feed scenario beacon to model via API (no TUI)
- Mock gt/bd commands with scripted responses
- Score tool call sequence against eval criteria
- Good for: quick model comparison, regression testing

```python
class MockGT:
    def prime(self): return ROLE_CONTEXT
    def hook(self): return scenario.hook or "Nothing on hook."
    def mail_check(self): return scenario.mail or "No messages."
    def bd_list(self): return format_beads(scenario.beads)
```

### Mode 2: Sandbox Evaluation (realistic, slower)
- Spin up real sandbox rig with prepared state
- Run agent in tmux via any harness (pir, omp, claude)
- Real gt/bd commands against sandbox Dolt DB
- Score by parsing session transcript + checking final state

```bash
gt bench run --scenario W-002 --agent pi-kimi --rig sandbox
gt bench run --scenario W-002 --agent omp-qwen --rig sandbox
gt bench compare W-002  # side-by-side results
```

### Mode 3: Live Evaluation (production, continuous)
- Tag real patrol/work sessions with scenario IDs
- Score outcomes against gold standard automatically
- Dashboard shows model performance over time
- Feeds directly into training data quality scoring

---

## Scoring Algorithm

```python
def score_scenario(transcript, scenario):
    score = 0.0
    weights = scenario["scoring"]

    # Required actions (0.0 - 1.0)
    required = scenario["eval"]["required"]
    required_hits = sum(1 for r in required if action_found(transcript, r))
    score += weights["required_weight"] * (required_hits / len(required))

    # Bonus actions (0.0 - 1.0)
    bonus = scenario["eval"].get("bonus", [])
    if bonus:
        bonus_hits = sum(1 for b in bonus if action_found(transcript, b))
        score += weights["bonus_weight"] * (bonus_hits / len(bonus))

    # Efficiency (0.0 - 1.0)
    actual_tokens = sum(t.usage.total for t in transcript.turns)
    baseline = scenario["eval"]["max_tokens"] * 0.5  # assume 50% is good
    efficiency = min(1.0, baseline / max(actual_tokens, 1))
    score += weights["efficiency_weight"] * efficiency

    # No forbidden actions (0.0 or full weight)
    forbidden = scenario["eval"].get("forbidden", [])
    violations = sum(1 for f in forbidden if action_found(transcript, f))
    if violations == 0:
        score += weights["no_forbidden_weight"]

    return round(score, 3)
```

---

## Building Scenarios from Real Sessions

The best scenarios come from actual agent work. Pipeline:

1. **Mine gold sessions**: Query pir sessions + bead outcomes
   - Sessions where bead closed on first attempt = "gold" patrol/execution
   - Sessions with escalations = good "hard" scenarios
   - Sessions where agent looped = anti-patterns to test against

2. **Extract setup state**: From the gold session, capture:
   - What beads existed at session start
   - What was on the hook/mail
   - Git state at start
   - Key files involved

3. **Derive eval criteria**: From the gold session, extract:
   - Required: commands the agent ran that were essential
   - Bonus: helpful but optional actions
   - Forbidden: derive from common failure modes

4. **Parameterize**: Make scenarios reusable by templating:
   - Bead IDs, titles, descriptions
   - File contents
   - Git branch names

```bash
# Future command
gt bench extract --session <session-id> --output scenarios/W-new.json
```

---

## Leaderboard

Track model performance across all scenarios:

```
╭──────────────────────────────────────────────────────────╮
│                   GTBench Leaderboard                     │
├──────────────┬────────┬────────┬────────┬────────┬───────┤
│ Model        │ Patrol │ Merge  │ Exec   │ Coord  │ Total │
├──────────────┼────────┼────────┼────────┼────────┼───────┤
│ claude-opus  │  0.92  │  0.88  │  0.85  │  0.79  │ 0.86  │
│ kimi-k2.5    │  0.87  │  0.82  │  0.90  │  0.71  │ 0.82  │
│ qwen3-max    │  0.84  │  0.86  │  0.83  │  0.68  │ 0.80  │
│ gastown-v1*  │  0.95  │  0.91  │  0.93  │  0.85  │ 0.91  │
╰──────────────┴────────┴────────┴────────┴────────┴───────╯
* fine-tuned model
```

The whole point: prove the fine-tuned model beats the base models at Gas Town tasks.

---

## Implementation Priority

| Phase | Task | Effort |
|-------|------|--------|
| 1 | Define 5 core scenarios (1 per role) | 2 days |
| 2 | Offline evaluator (mock gt commands) | 3 days |
| 3 | Scenario mining from real sessions | 3 days |
| 4 | Sandbox evaluator (real gt in sandbox rig) | 1 week |
| 5 | `gt bench` CLI integration | 1 week |
| 6 | Leaderboard + dashboard | 3 days |
| 7 | Live evaluation hooks | 1 week |
