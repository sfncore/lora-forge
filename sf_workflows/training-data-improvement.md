# Training Data Improvement Strategy

## The Problem

The LoRA training pipeline extracts session transcripts from Claude (Opus/Sonnet) and fine-tunes a smaller model (Qwen 2.5 7B) to reproduce Gas Town agent behaviors. But Claude's session transcripts contain both good and bad decisions — the current pipeline treats them equally.

A mayor session where it efficiently resolved a stuck bead in 3 commands gets the same training weight as one where it flailed for 20 minutes before escalating. We're training on the average, not the best.

## The Insight: Distillation, Not Imitation

We're not training the model to be as smart as Claude. We're distilling Claude's behavioral patterns into a smaller model that knows Gas Town's vocabulary — the right `gt` commands, mail patterns, bead workflows, convoy dispatch sequences.

Claude is the teacher. The 7B model is the student. The student doesn't need to reason at Claude's level — it needs to reliably reproduce the workflows Claude already figured out.

This means:
- **Procedural patterns** (patrol cycles, merge queue processing, health checks) — high signal, easy to learn
- **Strategic decisions** (when to escalate, which approach for a tricky bead) — lower signal, harder to learn
- **Mistakes in transcripts** — actively harmful, teaches bad habits

The training data improvement strategy focuses on separating these signals.

## Data Sources for Scoring

Gas Town already captures the audit trail needed to score sessions:

### Beads (bd / Dolt database)

Every bead has a lifecycle: created → assigned → in_progress → closed/reopened/superseded.

| Signal | Meaning | Query |
|--------|---------|-------|
| Closed on first attempt | Clean execution | `bd query "state=closed AND reopened=0"` |
| Reopened 1+ times | Something went wrong | `bd query "reopened>0"` |
| Superseded | Approach was wrong | `bd query "state=superseded"` |
| Abnormally long | Agent struggled | Compare duration to role median |
| Escalated to mayor | Polecat/deacon couldn't handle it | Check mail trail for escalation |

### Events (`~/gt/.events.jsonl`)

Every `gt` command, mail sent, convoy dispatch. Trace a failed bead back to the exact session where the wrong decision was made.

### Dolt History

`bd history <bead-id>` shows every state change with timestamps. Diff between "what the agent did" and "what actually worked" when someone fixed it later.

### Session Metadata

Each training sample already carries `session_id`, `role`, and `quality_score`. Link session_id back to beads and events to enrich with outcome data.

## Improvement Approaches

### 1. Outcome-Based Scoring

Add a `data/transform/session_scorer.py` that enriches each training sample with outcome signals:

- Look up the bead associated with each session (session metadata → bead ID via events)
- Check bead outcome: closed successfully? reopened? superseded?
- Check rework signals: how many sessions touched this bead before close?
- Check escalation count: did it get escalated? how many times?
- Compute an outcome score (0.0 = failed, 1.0 = clean first-attempt close)

The outcome score feeds into quality_filter — samples from successful completions get weighted up, samples from messy rework cycles get weighted down or excluded.

### 2. Exclude Bad Sessions

Simplest approach. Identify sessions associated with:
- Beads that were reopened or superseded
- Sessions where the agent got stuck (no progress for extended periods)
- Sessions with error loops (same command retried 3+ times)

Remove these from the training set entirely. Reduces dataset size but increases quality.

### 3. Downweight Bad Sessions

Instead of excluding, reduce the quality_score for problematic sessions. The model still sees the patterns but they contribute less to the loss function. Good for cases where a session has some useful tool usage patterns but a bad strategic decision.

### 4. DPO Preference Pairs (Phase 3)

The most powerful approach. Requires pairs of (preferred, rejected) responses for the same prompt.

Where do the pairs come from?

| Preferred | Rejected | Source |
|-----------|----------|--------|
| Session that closed bead on first try | Session that required rework | Same bead, different attempts |
| Mayor's decision that resolved an issue | Earlier failed approach | Session before vs after fix |
| Polecat that completed clean PR | Polecat whose PR was rejected | Same bead, different assignees |
| Deacon patrol that caught a problem early | Patrol that missed it | Compare patrol effectiveness |

This requires a `data/transform/preference_formatter.py` that:
1. Groups sessions by bead ID
2. Identifies success/failure pairs
3. Aligns prompts (same or similar user input)
4. Outputs DPO-format JSONL for Axolotl or TRL

### 5. Synthetic Correction

Have Claude re-do a failed session with hindsight knowledge of what went wrong. Use the corrected version as the "preferred" response in a DPO pair.

Workflow:
1. Identify a failed session (bead reopened, agent got stuck)
2. Extract the user prompts from that session
3. Add context: "The previous attempt failed because X. Here's what actually worked: Y"
4. Run Claude on the same prompts with that context
5. Pair: corrected response (preferred) vs original response (rejected)

This is more expensive (requires Claude API calls) but produces high-quality correction signal.

## Deacon and Witness as Data Curators

### The Recursive Loop

Deacon and witness already evaluate agent health as their core job. Training them to be better at it, then using that capability to improve everyone's training data, closes a natural loop:

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│  1. Train v1 adapters on raw data (current)         │
│     ↓                                               │
│  2. Deploy deacon-v1, witness-v1                    │
│     ↓                                               │
│  3. They score mayor/polecat sessions more          │
│     accurately (they understand Gas Town now)       │
│     ↓                                               │
│  4. Use their scores to curate v2 dataset           │
│     ↓                                               │
│  5. Train v2 adapters on curated data               │
│     ↓                                               │
│  6. Better deacon-v2/witness-v2 score even          │
│     more accurately                                 │
│     ↓                                               │
│  7. Repeat                                          │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Witness as Polecat Scorer

The witness already monitors polecat sessions. Extend its patrol to score completed sessions:

- Did the polecat complete the bead? → positive signal
- Did it create a clean PR that merged without rework? → strong positive
- Did it get stuck and need rescue? → negative signal
- How many tool calls did it take relative to task complexity? → efficiency signal

The witness writes scores to the beads database (a new field or label). The training pipeline reads these scores during extraction.

### Deacon as Pattern Scorer

The deacon sees patrol-level patterns across the whole town:

- "Mayor sent 5 mails about the same stuck bead before resolving it" → low-quality decision chain
- "Polecat completed 3 beads in one session without escalation" → high-quality execution
- "Convoy completed all legs with no rework" → strong positive for all involved sessions

The deacon generates scoring reports during its patrol cycle. These feed back into the training pipeline.

### Human as Ground Truth Calibrator

The human stays in the loop as the calibrator:

- Spot-check deacon/witness scoring to ensure they're not reinforcing each other's blind spots
- Override scores when agents miss context (e.g., a "failed" bead that was actually superseded by a better approach)
- Set policy: "for v2 training, exclude all sessions with outcome_score < 0.3"

## Integration Points

### During Formula Runs

The gt-toolkit formulas (spec → plan → beads → execution) generate high-value training data at every stage:

- **Spec brainstorm sessions** — examples of creative problem-solving
- **Plan writing sessions** — examples of structured analysis
- **Beads creation sessions** — examples of work decomposition
- **Convoy execution sessions** — examples of coordinated multi-agent work

Each formula run should tag its sessions with the formula name and step. This creates labeled training data that maps to specific competencies.

### During Patrol Cycles

Deacon and witness patrols generate training data AND scoring data simultaneously:

- The patrol session itself → training data for deacon/witness roles
- The patrol findings → scores for other agents' sessions
- Two outputs from one operation

### Post-Convoy Scoring

After a convoy completes, run a scoring pass:

1. Pull all session IDs from the convoy legs
2. Check bead outcomes for each leg
3. Score each session based on its contribution to convoy success/failure
4. Update the training dataset with enriched scores
5. If scores shifted significantly, flag for retraining

## Implementation Phases

### Current (v1): Surface Quality Filtering
- Quality score based on content density, tool usage, conversation depth
- No outcome awareness
- Status: **implemented**

### Next (v1.5): Outcome-Based Scoring
- Link sessions to beads via events
- Score based on bead lifecycle outcomes
- Exclude or downweight failed sessions
- Status: **needs `session_scorer.py`**

### Future (v2): Agent-Assisted Curation
- Deploy trained deacon/witness adapters
- They score sessions during patrol cycles
- Human calibrates and sets policy
- Retrain with curated data
- Status: **requires v1 adapters deployed first**

### Future (v3): DPO Preference Training
- Generate preference pairs from bead success/failure
- Optional: synthetic correction via Claude
- Train with DPO loss (Axolotl or TRL)
- Status: **requires sufficient bead outcome data**
