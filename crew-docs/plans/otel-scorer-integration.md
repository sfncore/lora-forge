# Plan: OTel Signal Inventory → Scorer Integration + Lora Forge Dashboard

> Recovered from session 013f5225 (2026-03-01). Partially implemented — see
> uncommitted changes in otel_client.py, session_linker.py, session_scorer.py,
> pipeline.py.

## Context

We partially implemented the OTel pipeline (otel_client, session_linker, pipeline integration) but did it backwards — we picked signals without methodically analyzing what's available and what's actually useful for scoring training data quality. The user wants us to start from the data, reason about what matters, then wire up only what's justified.

Additionally: create a Grafana dashboard for lora_forge.

## Part 1: Complete Signal Inventory

### VictoriaLogs — 22 event types, 547K total events

| _msg | Count | gt.session? | Useful for scoring? |
|------|-------|-------------|-------------------|
| `done` | 30 | YES | **Primary signal** — exit_type + status |
| `session.start` | 316 | YES (as `session_id`) | **Duration calc** — start timestamp |
| `session.stop` | 353 | YES (as `session_id`) | **Duration calc** — stop timestamp |
| `bd.call` | 152K | NO (has gt.rig, gt.role) | Not linkable per-session |
| `claude_code.api_request` | 5K | NO (uses UUID `session.id`) | Not linkable to gt.session |
| `claude_code.tool_decision` | 2.8K | NO (uses UUID `session.id`) | Not linkable to gt.session |
| `claude_code.tool_result` | 2.8K | NO (uses UUID `session.id`) | Not linkable to gt.session |
| `claude_code.user_prompt` | 375 | NO (uses UUID `session.id`) | Not linkable to gt.session |
| `claude_code.api_error` | 35 | NO (uses UUID `session.id`) | Not linkable to gt.session |
| `mail` | 231K | NO | Infrastructure noise |
| `pane.read` | 150K | NO | Infrastructure noise |
| `sling` | 1.1K | NO (has `bead`, `target`) | Dispatch tracking, not quality |
| `prime` | 307 | NO (has `role`) | Context, not quality |
| `prime.context` | 290 | NO | Has formula text — interesting but not a score signal |
| `polecat.spawn` | 28 | NO (has `name`) | Lifecycle, not quality |
| `polecat.remove` | 27 | NO (has `name`) | Lifecycle, not quality |
| `formula.instantiate` | 28 | NO | Lifecycle, not quality |
| `agent.state_change` | 24 | NO | Lifecycle, not quality |
| `daemon.restart` | 159 | NO | Infrastructure |
| `nudge` | 37 | NO | Coordination |
| `prompt.send` | 10 | NO | Coordination |
| `convoy.create` | 5 | NO | Coordination |

### VictoriaMetrics — 30 metric names

| Metric | Labels include gt_session? | Useful for scoring? |
|--------|--------------------------|-------------------|
| `claude_code_active_time_seconds_total` | `session_id` (UUID) | Not directly linkable |
| `claude_code_cost_usage_USD_total` | `session_id` (UUID) | Not directly linkable; also inaccurate |
| `claude_code_token_usage_tokens_total` | `session_id` (UUID) | Not directly linkable |
| `claude_code_lines_of_code_count_total` | `session_id` (UUID) | Not directly linkable |
| `gastown_done_total` | `gt_session` YES | Counter only (no exit_type detail) — logs are richer |
| `gastown_session_starts_total` | `session_id` YES | Counter — logs have timestamps which are more useful |
| `gastown_session_stops_total` | `session_id` YES | Same |
| `gastown_bd_calls_total` | NO gt_session | Not linkable per-session |
| `gastown_bd_duration_ms_*` | NO gt_session | Not linkable per-session |
| `gastown_polecat_spawns_total` | `name` only | Lifecycle |
| Everything else | NO | Infrastructure/ops metrics |

### Critical Finding: Session ID Gap

Two ID systems exist with **no bridge**:
- **Gastown events**: `gt.session` = "lf-furiosa", "hq-mayor", etc.
- **Claude Code events**: `session.id` = UUID like "ad02c8e8-..."

This means **all claude_code.* log events and claude_code_* metrics are unlinkable** to the GT session scorer pipeline without building a separate mapping layer. That's a separate project.

### What IS Reliably Linkable Per-Session

Only three event types carry `gt.session` or equivalent `session_id` in GT format:

1. **`done`** events → `gt.session`, `exit_type`, `status`, `error`, `gt.topic`, `gt.role`
2. **`session.start`** events → `session_id`, `role`, `_time`
3. **`session.stop`** events → `session_id`, `_time`

## Part 2: What Matters for Training Data Quality

The scorer answers: "Is this session good training data for the LoRA adapter?"

### Dimension 1: Outcome (strongest signal)
**Source**: `done` events
**Fields**: `exit_type` + `status`

| exit_type | status | Meaning | Score impact |
|-----------|--------|---------|-------------|
| COMPLETED | ok | Task finished cleanly | Best outcome (1.0) |
| COMPLETED | error | Tried to finish but failed (e.g., uncommitted changes) | Partial — the work was done but the cleanup failed (0.7) |
| DEFERRED | error | Gave up / couldn't finish | Poor outcome (0.3) |
| (missing) | — | No done event for this session | Fall back to heuristic |

**Current code bug**: The scorer treats any `exit_type=COMPLETED` as 1.0 regardless of `status`. A COMPLETED+error (like "cannot complete: uncommitted changes") should score lower.

### Dimension 2: Duration Efficiency
**Source**: `session.start` + `session.stop` timestamps
**Calculation**: `stop._time - start._time` → `duration_ms`

Already implemented. This is reliable — both events use `session_id` in GT format.

**Fallback**: `active_time_seconds` from VictoriaMetrics — but uses UUID session_id, NOT gt.session. **Remove this fallback** since it can't actually link.

### Dimension 3: Work Context
**Source**: `done` events → `gt.topic`
**Values observed**: "assigned", "patrol", "start", "cold-start"

This tells us what KIND of work the session did. "assigned" = working a bead task, "patrol" = monitoring duty. Different work types have different quality baselines. Not a direct score input, but useful as metadata for the scorer's role medians.

### What NOT to Use (and why)

- **cost_usd / token_count**: Inaccurate (user confirmed), wrong session ID system, and cost ≠ quality
- **bd.call counts**: Can't link to gt.session, and call count ≠ quality
- **claude_code.tool_decision**: Wrong session ID system
- **active_time_seconds**: Wrong session ID system (UUID, not gt.session)

## Part 3: Changes to Code

### 3.1 Fix `otel_client.py` (DONE — uncommitted)

**Keep**: `get_done_events()`, `get_session_lifecycle()`
**Remove**: `get_active_time()` — uses wrong session ID system, can't actually link
**No other methods needed** — the two linkable signal sources are covered

### 3.2 Fix `session_linker.py` (DONE — uncommitted)

**Keep**: exit_type extraction from done events, duration_ms from lifecycle
**Add**: `status` extraction from done events (COMPLETED+error ≠ COMPLETED+ok)
**Add**: `gt.topic` extraction from done events (metadata for context)
**Remove**: active_time_seconds query (unlinkable)
**Remove**: cost/token queries (unlinkable + inaccurate)

Final `otel_signals` dict shape:
```python
{
    "exit_type": "COMPLETED",      # from done event
    "status": "ok",                # from done event
    "topic": "assigned",           # from done event
    "duration_ms": 300000,         # from start/stop timestamps
}
```

### 3.3 Fix `session_scorer.py` (DONE — uncommitted)

**Fix**: `compute_step_level_score()` — check `status` alongside `exit_type`:
- COMPLETED + ok → 1.0
- COMPLETED + error → 0.7
- DEFERRED + any → 0.3
- missing → heuristic fallback

**Fix**: `compute_formula_level_score()` — remove `active_time_seconds` fallback (unlinkable). If `duration_ms` is missing, fall back to heuristic.

### 3.4 Pipeline integration (DONE — uncommitted)

No changes needed — the linker call in `pipeline.py` is already correct.

## Part 4: Grafana Dashboard for lora_forge (NOT STARTED)

Create a new provisioned dashboard: `lora-forge-sessions.json`

Datasources: VictoriaMetrics (uid: `victoriametrics`), VictoriaLogs (uid: `victorialogs`), Dolt (uid: `dolt-beads`)

### Panels

**Row 1: Session Overview**
- **Stat: Active lf-* Sessions** — `sum(gastown_session_starts_total{gt_rig="lora_forge"}) - sum(gastown_session_stops_total{gt_rig="lora_forge"})`
- **Stat: Total Done Events** — `sum(gastown_done_total{gt_rig="lora_forge"})`
- **Stat: Polecat Spawns** — `sum(gastown_polecat_spawns_total{gt_rig="lora_forge"})`

**Row 2: Session Outcomes (VictoriaLogs)**
- **Table: Recent Done Events** — LogsQL: `_msg:"done" AND gt.rig:"lora_forge"` showing gt.session, exit_type, status, _time
- **Pie: Exit Type Distribution** — LogsQL stats: `_msg:"done" AND gt.rig:"lora_forge" | stats by (exit_type, status) count() hits`

**Row 3: Session Lifecycle**
- **Timeseries: Session Start/Stop Rate** — `increase(gastown_session_starts_total{gt_rig="lora_forge"}[5m])` + stops overlay
- **Table: Session Durations** — LogsQL: join start/stop by session_id, compute duration

**Row 4: Polecat Activity**
- **Timeseries: Polecat Spawns/Removes** — `increase(gastown_polecat_spawns_total{gt_rig="lora_forge"}[5m])` + removes
- **Timeseries: bd Call Rate** — `rate(gastown_bd_calls_total{gt_rig="lora_forge"}[5m])`

**Row 5: Convoy Progress (Dolt)**
- **Table: lora_forge Convoy Beads** — SQL query on hq.issues filtered to lf-* beads

### Dashboard file location
`/home/ubuntu/gt/sfgastown/mayor/rig/opentelemetry/grafana/provisioning/dashboards/lora-forge-sessions.json`

Then restart Grafana to pick it up: `docker restart gt-grafana`

## Verification

1. `python3 -c "from data.transform.otel_client import OTelClient; c = OTelClient(); e = c.get_done_events('lf-furiosa'); print([(x.get('exit_type'), x.get('status')) for x in e])"` → `[('COMPLETED', 'ok'), ...]`
2. `python3 -c "from data.transform.session_linker import SessionLinker; l = SessionLinker(); r = l.link_session('lf-furiosa'); print(r['otel_signals'])"` → `{'exit_type': 'COMPLETED', 'status': 'ok', 'duration_ms': ..., 'topic': 'assigned'}`
3. Check Grafana dashboard loads: `curl -s -u admin:admin http://localhost:9429/api/dashboards/uid/lora-forge-sessions | python3 -c "import sys,json; print(json.load(sys.stdin)['dashboard']['title'])"`

## Progress Tracking

- [x] Part 1: Signal inventory (research complete)
- [x] Part 3.1: otel_client.py rewrite (uncommitted)
- [x] Part 3.2: session_linker.py rewrite (uncommitted)
- [x] Part 3.3: session_scorer.py fixes (uncommitted)
- [x] Part 3.4: pipeline.py integration (uncommitted)
- [x] Verification: tested against live VictoriaLogs (2026-03-01)
  - get_done_events: 34 events across 10 GT sessions, exit_type+status correct
  - SessionLinker: populates exit_type, status, topic, duration_ms
  - Scorer: COMPLETED+ok=1.0, COMPLETED+error=0.7, DEFERRED=0.3
  - Pipeline: 0/290 linked (expected — UUID != GT session name, bridge needed)
- [ ] Part 4: Grafana dashboard (bead lf-5fbh)
