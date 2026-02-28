# lora-forge

Per-role LoRA fine-tuning pipeline for Gas Town agents. Each Gas Town role (mayor, deacon, witness, refinery, polecat, crew) gets its own LoRA adapter, trained on role-specific session data and optimized via Optuna hyperparameter search.

## Architecture

```
Session Transcripts → Data Pipeline → Per-Role Datasets → Axolotl Training → Role Adapters → Petals Swarm
     (this machine)     (this repo)     (role-tagged)       (cloud GPU)        (HF Hub)      (distributed)
```

Agents load their role-specific adapter at runtime from the Petals swarm.

## Quick Start

```bash
# Extract and process training data (CPU only)
make -C data all

# View dataset statistics
python -m data.validate.stats

# Training (requires GPU — see infra/ for cloud setup)
axolotl train configs/roles/mayor.yml    # Train a specific role adapter
axolotl train configs/base.yml           # Train the shared base adapter
```

## Structure

- `data/` — Training data extraction and processing pipeline
- `configs/` — Axolotl training configurations (QLoRA base + per-role overrides)
- `eval/` — Role-specific evaluation scenarios and benchmarking
- `sf_workflows/` — StartupFactory formulas for retraining, scoring, and DPO
- `scripts/` — Remote training orchestration scripts
- `infra/` — Cloud GPU setup (RunPod, Docker)

## Training Data Sources

- **Claude session transcripts** — Agent conversations with tool use, tagged by role
- **Claude-mem observations** — Distilled knowledge and decisions
- **Beads database** — Task descriptions and outcomes
- **OTel telemetry** — Session outcome signals from sfgastown metrics
- **Formula run artifacts** — Step-level and run-level outcomes from workflow executions

## Goal

Train a dedicated LoRA adapter per Gas Town role on Qwen 2.5 7B. Each role has distinct behavior patterns — the mayor orchestrates, crew codes, the witness observes, the deacon reviews. Per-role adapters capture these differences rather than averaging them into a single adapter.

The Optuna rig drives hyperparameter optimization (CMA-ES sampler), using role_bench eval scores as the objective to find optimal rank, learning rate, and training config per role.

---

## Methodology

### Core Principle: Production-First Training

Every inference dollar produces real work for real humans. Training signal is a byproduct of production, not a separate cost center. We don't run experiments in a lab and then deploy — the work IS the experiment. Humans are in the loop as collaborators, and every form of human feedback (corrections, overrides, escalations, approvals, rejections) is captured methodically and fed back into the training system at every level.

This means:
- **No wasted compute.** Dual-branch comparisons run on actual beads that need solving. Both branches produce deliverables — we keep the best result and train on the delta.
- **No synthetic-only data.** Synthetic correction and DPO pair generation supplement production data, they don't replace it. The ground truth is always "did this help a human get something done."
- **Feedback capture is systematic, not ad-hoc.** Every human touchpoint has a defined path back into the training pipeline — from explicit corrections to implicit signals like "the human didn't need to intervene at all."
- **The system improves by doing its job.** The more work Gas Town does, the more training data it generates, the better the adapters get, the more work it can do. The flywheel is the product.

### Three Loops

Three feedback loops operate at different timescales. Each loop's output feeds the next loop's input.

```
┌─ Discovery Loop (what to measure) ─────────────────────────────────┐
│  ┌─ Optimization Loop (how to train) ───────────────────────────┐  │
│  │  ┌─ Training Loop (train → eval) ────────────────────────┐   │  │
│  │  │                                                        │   │  │
│  │  │  Sessions → Score → Curate → Train → Eval ──────┐     │   │  │
│  │  │  ^                                               │     │   │  │
│  │  │  └───────────────── retrain ◄────────────────────┘     │   │  │
│  │  └────────────────────────────────────────────────────────┘   │  │
│  │  ^                                                        │   │  │
│  │  └──── CMA-ES adjusts rank, lr, alpha, schedule ◄────────┘   │  │
│  └───────────────────────────────────────────────────────────────┘  │
│  ^                                                            │    │
│  └──── CMA-ES adjusts telemetry recipe weights ◄─────────────┘    │
└────────────────────────────────────────────────────────────────────┘
```

### Training Loop

Timescale: hours. The inner loop that produces adapters.

1. **Extract** — Pull sessions from Claude project dirs, parse turns by requestId
2. **Tag** — Map session directory paths to canonical roles (mayor, deacon, witness, refinery, polecat, crew)
3. **Score** — Rate each session using the outcome scoring algorithm (see below)
4. **Curate** — Apply per-role quality thresholds. Exclusion, downweighting, or agent-assisted review depending on curation policy
5. **Format** — Sharegpt JSONL with role-specific system prompts, secret-scrubbed, chunked, deduped
6. **Train** — Axolotl QLoRA on Qwen 2.5 7B, per-role config overrides in `configs/roles/`
7. **Eval** — role_bench scenarios score the adapter against expected Gas Town behaviors

The training loop runs as a single formula: `training-retrain-cycle.formula.toml`.

### Outcome Scoring

Scoring is not a single metric. It's a composable algorithm that evaluates at multiple levels of granularity.

**Turn-level signals:**
- Tool call success/failure rate
- Latency (time between prompt and action)
- Error recovery (did the agent self-correct or spiral?)

**Step-level signals (within a formula):**
- Did the step produce its expected artifact?
- How many turns did it take vs baseline?
- Did it require escalation or human intervention?
- Tool call diversity and appropriateness for the step type

**Formula-level signals:**
- All steps completed?
- Total duration vs historical median for this formula
- Quality of final artifact (LLM-judge or downstream acceptance)
- Resource consumption (token spend, API calls, compute)

**Cross-run signals (formula variants):**
- Same formula, different hyperparameters — which produced better outcomes?
- Same goal, tweaked formula — which workflow structure works better?
- Same formula, different model tier — where does the candidate diverge from reference?

The scoring algorithm weights these signals into a composite score per session. CMA-ES in the discovery loop optimizes the weights themselves — it learns which combination of signals at which levels actually predicts "this session produced good training data."

**Priority cascade for data availability:**

```
1. OTel structured metrics  (strongest signal, most reliable)
2. Formula run outcomes      (step-level and run-level)
3. Bead lifecycle            (closed/reopened/superseded)
4. Events trail              (escalation count, rework signals)
5. Heuristic                 (content analysis fallback)
```

### Optimization Loop

Timescale: days. CMA-ES (Covariance Matrix Adaptation Evolution Strategy) searches across training runs to find optimal per-role configurations.

**What CMA-ES optimizes:**
- LoRA rank (r) and alpha — capacity vs overfitting
- Learning rate and schedule — convergence speed vs stability
- Curation threshold — how aggressively to filter low-outcome sessions
- Chunk size and overlap — how much context each training sample carries
- Warmup steps, weight decay, dropout

**Objective function:** role_bench eval scores from the training loop. Each CMA-ES trial is a full training run with different hyperparameters, scored by how well the resulting adapter reproduces correct Gas Town behaviors.

**Why CMA-ES over grid/random search:** The hyperparameters interact. High rank needs lower learning rate. Aggressive curation (small dataset) needs more epochs. CMA-ES learns these covariances — it models the shape of the interaction space rather than sampling blindly.

**Why CMA-ES over Bayesian/TPE:** Our objective is noisy (training variance, eval variance, session quality variance). CMA-ES is robust to noise. It also scales well to the 10-20 continuous variables we're tuning per role. TPE is better for categorical choices (which optimizer, which base model) — Optuna can mix samplers within a single study.

**Per-role optimization:** Each role gets its own CMA-ES study. The mayor's optimal rank may differ from crew's — the mayor orchestrates (needs broader pattern matching), crew codes (needs precise tool call sequences). CMA-ES finds these differences automatically.

### Telemetry Discovery Loop

Timescale: weeks. The most experimental loop. Instead of hand-picking which OTel signals matter, CMA-ES explores the telemetry space to discover which signal combinations predict adapter quality.

**The telemetry recipe:** A weight vector over available OTel signals:

```python
recipe = {
    "exit_type_completed":      0.35,
    "session_duration_ms":     -0.10,
    "sling_dispatch_count":    -0.20,
    "agent_restart_count":     -0.40,
    "mail_operations":         -0.05,
    "bead_close_time_vs_median": -0.15,
    "formula_step_success_rate": 0.30,
    "tool_call_diversity":      0.10,
    ...
}
```

CMA-ES proposes recipe weights. The recipe becomes the scoring function in the training loop. The training loop produces an adapter. The adapter's role_bench score is the discovery loop's objective.

**What this discovers:**
- Which signals actually matter per role (maybe restart_count is critical for polecat but irrelevant for deacon)
- Non-obvious correlations (maybe high mail volume predicts good mayor sessions — active coordination, not overhead)
- What's MISSING — if CMA-ES plateaus and all weight adjustments stop helping, the signal we need isn't in the telemetry yet. That's the cue to instrument something new in sfgastown

**Interface to sfgastown:** When the discovery loop identifies a gap, it produces a recommendation: "add metric X to the OTel instrumentation." The human reviews and adds it. The next discovery cycle picks it up.

### Dual-Branch Model Comparison

Run identical Gas Town workflows through two model tiers on separate Dolt branches. Both branches produce real deliverables — we keep the best result for the human and train on the delta. No compute is wasted on pure experimentation.

- **Branch A (candidate):** Open-source model with current LoRA adapter
- **Branch B (reference):** Frontier model (Opus, Gemini, Codex)

Same formulas, same prompts, same role assignments. The delta between branches produces three types of training signal:

**DPO pairs** — Where the candidate fails but the reference succeeds on the same formula step, that's a natural (preferred, rejected) pair. No synthetic generation needed.

**Distillation targets** — The reference model's reasoning traces (chain-of-thought, tool call sequences) become training targets for the candidate. We capture HOW the better model solved it, not just that it succeeded.

**Failure mode map** — Dolt diff between branches reveals which workflow steps, role types, or formula patterns the candidate struggles with. CMA-ES uses this to focus the optimization loop on the weak spots rather than searching uniformly.

**Formula variant experiments:** The dual-branch setup extends beyond model comparison. Run the same goal through tweaked formula variants:
- Different step ordering
- Different prompt templates
- Different tool constraints
- Different role assignments for the same step

**Judgment role variants on Dolt branches:** The witness and deacon themselves can be branched and tweaked. Run duplicate judgment roles with different configurations across Dolt branches on real work:
- Witness variant A with aggressive escalation thresholds vs variant B with conservative ones
- Deacon variant A with strict patrol rubrics vs variant B with exploratory ones
- Different system prompts, scoring weights, context injection strategies

Both variants judge the same real work. Compare their judgments against each other and against human decisions. The variant whose judgments best predict human agreement wins — and its configuration feeds back into both the role's training data and the formula system's logic.

This means Dolt branches vary three things simultaneously: **models** (LoRA adapters), **formulas** (workflow design), and **judgment** (how quality is assessed). CMA-ES optimizes across all three dimensions — the Optuna rig becomes an optimizer over the full system, not just the model.

**Convergence signal:** Track divergence rate between candidate and reference per role. When divergence drops below a threshold for a role, that adapter is production-ready. For judgment roles, convergence means the role's assessments consistently match human decisions without escalation.

### Worktree Replay and Composite Stitching

Since Gas Town work is worktree-based, convoy legs and formula steps can be replayed in isolation without affecting production. This turns every completed convoy into a replayable experiment:

**Selective replay:** A convoy completed but leg 3 was weak — the polecat struggled, the human had to correct. Replay just leg 3 in a fresh worktree with a different adapter, different formula variant, or different model tier. Keep the original legs 1-2 and 4-5, stitch in the better leg 3.

**Best-of-N stitching:** Run the same convoy leg N times across worktrees with different configurations. Take the best result for each leg and stitch them into a composite convoy that's better than any single run. The composite becomes a high-quality training example — it represents what the system COULD do at its best across the full workflow.

**Replay as controlled experiment:** Hold everything constant except one variable:
- Same leg, different LoRA adapter → measures adapter quality
- Same leg, different formula variant → measures formula design
- Same leg, different role assignment → measures role fit
- Same leg, different context injection → measures what context the model actually needs

Worktrees make this cheap. Each replay runs in its own isolated git worktree — no interference with production, no state bleed between experiments. Dolt captures the results on separate branches for comparison.

**Training corpus composition:** The training corpus is not just "sessions that happened." It's the best version of each step, assembled from multiple runs and stitched together intelligently. This means the model trains on work quality that exceeds what any single run produced — it learns from the system's composite best, not its average.

### Formula Awareness as Training Objective

The models don't just need to execute formula steps — they need deep awareness of the formula system itself. Which formula to invoke for a given situation, when to propose a formula modification, how to compose formula steps to achieve novel outcomes. This is a higher-order capability than instruction following.

**The full spectrum of formula capability:**

- **Selection** — Given a goal and context, the model knows which formula (or combination of formulas) is most likely to achieve it. A mayor with formula awareness doesn't just run the playbook — it picks the right playbook.
- **Execution** — The model follows formula steps correctly, using the right tools and patterns at each stage. This is the baseline capability.
- **Adaptation** — The model recognizes when a formula step is failing and proposes a modification rather than retrying the same approach. It understands formulas as composable and mutable, not as rigid scripts.
- **Composition** — The model can chain formula steps from different formulas to handle novel situations. Spec brainstorm from one formula, planning steps from another, execution from a third.
- **Authoring** — The model writes NEW formulas. Given a novel situation with no existing playbook, it designs a formula from scratch — defining steps, success criteria, telemetry hooks, and rollback strategies. The authored formula is a first-class artifact that can be tested, reviewed, and added to the formula library.
- **Evaluation** — The model assesses formula quality. Given a formula (existing or newly authored), it can predict: will this work for the given context? Where are the weak steps? What's missing? What could go wrong? This is the deacon's core capability applied to formula design.
- **Meta-reasoning** — The model can explain WHY a formula works for a given situation, connecting the formula's structure to the domain's constraints. This closes the loop — evaluation informs authoring, authoring creates new options for selection.

The progression from execution to meta-reasoning is the path from "tool user" to "tool maker." A model that can only execute formulas is a worker. A model that can author and evaluate them is a collaborator that improves the system's capabilities over time.

**Training for formula capability:**

The training data must include the full lifecycle, not just successful executions:
- Sessions where a role CHOSE a formula (the selection reasoning)
- Sessions where a formula was MODIFIED mid-run (the adaptation reasoning)
- Sessions where multiple formulas were COMPOSED (the composition reasoning)
- Sessions where a role WROTE a new formula (the authoring process — from problem analysis through step design to success criteria)
- Sessions where a formula was REVIEWED and critiqued (the evaluation reasoning — what the deacon/witness flagged, what the human changed)
- Deacon/witness evaluations of formula outcomes (the meta-reasoning)
- The DIFF between formula versions when a formula is revised after a failed run (what was wrong, what was fixed, why)

**Cross-rig context:** Formula awareness requires understanding that spans rigs, plans, specs, beads, commits, and outcomes. A model that only sees its own rig's sessions can't learn formula selection — it needs to see how the same formula performs across different rigs and contexts. The training pipeline enriches sessions with cross-rig context:
- What formula was used on this bead?
- What formulas were considered but not chosen?
- What was the outcome relative to similar beads that used different formulas?
- What telemetry patterns preceded successful vs failed formula applications?

This is where the understanding graph feeds directly into training. Every mapped connection between formula, context, and outcome is a training signal for formula awareness.

### The Formula Lifecycle

Formulas are not static artifacts. They have a lifecycle — ideation, authoring, versioning, execution, evaluation, refinement — and making that lifecycle methodical is what turns formula awareness from an aspiration into a trainable capability.

**Ideation** — A problem surfaces that no existing formula covers. A role (typically mayor or deacon) identifies the gap, characterizes the problem space, defines what a successful outcome looks like, and sketches the approach. The ideation session IS training data — it teaches models how to recognize formula-shaped problems and think about them structurally.

**Authoring** — The formula gets written: steps, success criteria per step, telemetry hooks, rollback strategies, role assignments, context requirements. Authoring happens in a rig, produces a versioned TOML artifact, and gets reviewed by the deacon or a human. The review catches gaps: missing steps, unclear criteria, wrong role assignments. Both the authored formula and the review feedback are training data.

**Versioning** — Formulas live in version control. Every revision has a diff, and every diff has a reason — a failed run exposed a weakness, a deacon review caught a gap, a human override changed the approach. The version history of a formula is a compressed record of what the system learned about solving that class of problem. Version diffs are high-signal training data: the before (what we thought would work) vs the after (what we learned actually works).

**Execution** — The formula runs on real work via convoys. Each execution produces telemetry, session transcripts, and outcomes at every level (turn, step, formula, cross-run). Execution data is the bulk of the training corpus.

**Evaluation** — After execution, the deacon and witness assess: did the formula work? Where did it break down? Was the decomposition right? Were the success criteria useful? This evaluation is itself formulated — there's a pattern for how to evaluate a formula run, and that pattern can be versioned and improved like any other formula.

**Refinement** — Evaluation findings feed back into the formula. A step gets rewritten, a dependency gets added, a success criterion gets tightened. The refined formula gets re-run, re-evaluated. The cycle continues until the formula reliably produces good outcomes — or gets retired in favor of a better approach.

```
Ideation → Authoring → Review → v1
                                 ↓
                             Execution → Evaluation
                                 ↓            ↓
                             v2 (refined) ← Findings
                                 ↓
                             Execution → Evaluation
                                 ↓            ↓
                             v3 (refined) ← Findings
                                 ↓
                              Stable (or retired)
```

**Every stage produces training data:**

| Stage | Training Signal | Trains |
|-------|----------------|--------|
| Ideation | Problem recognition, structural thinking | Mayor, deacon |
| Authoring | Step design, criteria definition, context specification | All roles that author |
| Review | Gap detection, quality assessment | Deacon, witness |
| Version diffs | What failed → what was fixed | All roles (meta-learning) |
| Execution | Tool use, role behavior, formula following | Role-specific adapters |
| Evaluation | Outcome assessment, pattern recognition | Deacon, witness |
| Refinement | Iterative improvement reasoning | Mayor, deacon |

**CMA-ES optimizes the lifecycle itself:** The Optuna rig can tune not just model hyperparameters but lifecycle parameters — how many review rounds before execution? How many execution runs before refinement? What evaluation criteria matter most for which formula types? The lifecycle is itself a formula that can be optimized.

### Beyond Tools: Formulas as the Primary Abstraction

Current frontier models reach for tools — grep, write, bash. That's single-turn thinking. The real unlock is models that reach for formulas — multi-step workflows that unfold over time, across sessions, with built-in review points and course correction.

**The shift:**

| Current Models | Formula-Native Models |
|----------------|----------------------|
| "I need to call grep to find X" | "I need to invoke the investigation formula because this has unknowns" |
| "Let me write the code now" | "Let me formulate beads, dispatch a convoy, and review results before committing to an approach" |
| "I'll retry this failed step" | "This step failed — let me evaluate the formula and propose a redesign" |
| "Here's my answer" | "Here's what I know, what I don't know, and a formula to close the gaps" |

**Collaboration over time**

A formula-native model understands that some problems can't be solved in a single session. It knows when to:
- **Research first** — "I don't fully understand this problem. Let me formulate an investigation with explicit unknowns to resolve before proposing a solution."
- **Decompose into beads** — "This is too complex for one pass. Let me create beads that track each sub-problem through the system."
- **Dispatch and wait** — "These beads need work from different roles/rigs. Let me convoy them out and review results when they come back."
- **Re-evaluate with deeper understanding** — "The convoy results changed my understanding. Let me reformulate next steps with the new context propagated across the system."
- **Escalate honestly** — "I've hit the limits of what I can determine here. Let me escalate with a clear description of what's known, unknown, and what I've tried."

This is time awareness — the model treats time as a resource, not a constraint. It doesn't rush to produce output. It invests time strategically: research now, formulate next steps, track through the system, review, re-evaluate.

**Training for temporal reasoning**

The training data for this capability comes from sessions where agents demonstrated time-aware behavior:
- Sessions where an agent CHOSE to research before acting (and the outcome was better than sessions where an agent rushed)
- Sessions where beads were created to track unknowns (and the unknowns were actually resolved through the convoy process)
- Sessions where a re-evaluation after convoy results led to a fundamentally different (and better) approach
- Sessions where an agent escalated with a clear knowns/unknowns map vs sessions where it escalated with "I'm stuck"
- The full lifecycle of a multi-session problem: initial assessment → formulation → dispatch → results → re-evaluation → next iteration

**The training signal is in the contrast:** A model that rushed and failed on a bead vs a model that researched, formulated, and succeeded on the same bead. DPO pairs from worktree replays make this concrete — replay the same bead with a "rush" strategy and a "formulate" strategy, compare outcomes.

**Propagating understanding across the system**

When a convoy completes and results are reviewed, the understanding gained doesn't stay in one session. It propagates:
- Updated context in beads (what we now know)
- Refined formulas (what we learned about the approach)
- New telemetry signals (what we should have been measuring)
- Training data for other roles (what the mayor learned helps train the deacon)
- Understanding graph edges (new connections between concepts, rigs, outcomes)

The model that re-evaluates after a convoy isn't just making a local decision — it's contributing to the system's collective understanding. Training on these re-evaluation sessions teaches models to think in terms of system-wide knowledge flow, not just their own context window.

### Cross-Role Diagnostic Training

The witness and deacon see failure patterns that the failing roles can't see about themselves. Their transcripts are diagnostic training data for the roles they observe.

**Why polecats struggle — it's usually not the polecat**

Polecats are ephemeral workers designed to have exactly the context they need to solve a problem. When they struggle, the root cause is usually upstream:

- **Stale context** — The bead description reflected reality when it was written, but the codebase, dependencies, or requirements evolved. The polecat is working against a snapshot that no longer matches.
- **Incomplete context** — The bead was missing critical information that the mayor or crew had but didn't include. The polecat is forced to discover things it should have been told.
- **Context drift during execution** — Another polecat in the same convoy changed something that invalidates this polecat's assumptions. No one updated the bead or nudged the polecat.
- **No intervention from support roles** — The witness sees the polecat struggling but doesn't step in. The mayor doesn't update the bead. The crew doesn't share relevant context from their own work. The deacon doesn't flag the pattern.

The polecat's failure is a symptom. The training signal is in the ABSENCE of action from the roles that should have helped:
- Witness transcripts where the witness observed struggle but didn't escalate or nudge → negative training data for the witness
- Mayor sessions where context changed but the bead wasn't updated → negative training data for the mayor
- Crew sessions where relevant information was discovered but not shared → negative training data for the crew
- Deacon patrols that missed a systemic pattern of context staleness → negative training data for the deacon

**The intervention training signal:**

The most valuable training data for the support roles isn't "here's how to do your job." It's "here's where you SHOULD have acted and didn't." Worktree replays make this concrete:

1. Original run: polecat struggles, no one intervenes, bead fails
2. Replay A: same setup, but the witness nudges the polecat with updated context mid-run → bead succeeds
3. Replay B: same setup, but the mayor updates the bead before the polecat starts → polecat succeeds first try
4. Replay C: same setup, but the crew shares a relevant finding via mail → polecat adjusts approach early

Each replay variant shows what a different role COULD have done. The original is the rejected sample. The replay is the preferred sample. But the DPO pair trains the SUPPORT role, not the polecat.

This flips the usual framing: we're not training polecats to be smarter. We're training the system to keep polecats supplied with the context they need. The polecat stays ephemeral and focused. The intelligence lives in the roles that feed it.

**Why convoys fail — the deacon knows**

Deacon patrol transcripts reveal systemic convoy quality issues:
- Bad decomposition — beads too large, too vague, or overlapping
- Missing dependencies — leg 3 blocked on unresolved output from leg 1
- Unclear success criteria — bead says "implement X" with no definition of done
- Redundant work — multiple legs solve the same sub-problem independently
- Wrong role assignment — a bead assigned to crew that needed mayor-level judgment

These are mayor training signals. The deacon's critique of a convoy, paired with the mayor session that created it, teaches the mayor to formulate better. When the deacon says "three legs duplicated work" — that's a rejected sample. A replay where the mayor decomposes correctly is the preferred sample.

**The diagnostic training pipeline:**

```
Witness observes polecat ──→ Witness transcript (the diagnosis)
                              + Polecat transcript (the failure)
                              + Worktree replay (the correction)
                              = DPO pair for polecat training

Deacon reviews convoy ──────→ Deacon transcript (the diagnosis)
                              + Mayor transcript (the bad convoy)
                              + Worktree replay (the good convoy)
                              = DPO pair for mayor training
```

Each role's failures, as diagnosed by the roles that observe them, become targeted training data. The observer roles get better at diagnosing (their transcripts become training data for themselves). The observed roles get better at the specific things they were failing at. The system improves at every level simultaneously.

**Convoy quality as a first-class metric:**

Convoy quality deserves its own scoring dimension in the outcome scoring algorithm:
- **Decomposition quality** — Did the beads cover the goal without gaps or overlaps?
- **Dependency correctness** — Were inter-leg dependencies explicit and satisfiable?
- **Completion criteria clarity** — Could a polecat determine "done" from the bead description alone?
- **Role-task fit** — Was each bead assigned to the right role?
- **Convoy completion rate** — What fraction of legs completed without rework?
- **Convoy coherence** — Did the legs produce a coherent result when stitched together?

CMA-ES in the optimization loop can weight these convoy-level signals alongside turn-level and formula-level signals. If convoy quality is the bottleneck (and the deacon transcripts suggest it is), the optimization loop will surface that — the system learns where its biggest improvement opportunity is.

### Continuous Training from Production

Every Gas Town turn in production generates training signal. The system accumulates and scores continuously rather than waiting for batch retraining.

**The accumulation cycle:**

1. Agent completes a turn in production — session logged + OTel emitted
2. Telemetry recipe scores the session in near-real-time
3. High-scoring sessions enter a staging dataset
4. When staging reaches threshold (N new high-quality samples per role), trigger retrain
5. Role_bench eval gates promotion — new adapter only deploys if it beats the incumbent

### Human Feedback Capture

Humans are collaborators, not labelers. The system captures their feedback methodically at every level — from explicit corrections to implicit signals — and routes each type back into the appropriate training loop.

**Explicit feedback (strongest signal):**
- **Corrections** — Human edits agent output. Pre-correction = rejected, post-correction = preferred. Direct DPO pair.
- **Overrides** — Human takes over a step the agent was handling. The human's approach becomes a distillation target.
- **Rejections** — Human rejects a PR, reopens a bead, or escalates. Negative outcome signal propagates to all sessions involved.
- **Approvals** — Human merges, closes, ships. Positive outcome signal for the full session chain.

**Implicit feedback (weaker but high-volume):**
- **No intervention** — The agent completed work and the human didn't touch it. Silence is approval. These sessions get scored by the telemetry recipe and accumulate as baseline training data.
- **Time-to-review** — How long did the human take to review? Fast review of a clean result = high confidence signal. Long review followed by changes = the work was close but not right.
- **Re-engagement patterns** — Did the human come back to this bead later? Revisits suggest the "completed" work had issues that surfaced downstream.

**Structural feedback (shapes the system itself):**
- **Formula tweaks** — When a human modifies a formula before re-running it, the diff between old and new formula is a signal about workflow design. CMA-ES in the optimization loop can learn from these human-initiated changes.
- **Telemetry requests** — When a human asks "why did this score high/low?" and the system can't explain it, that's a gap signal for the discovery loop.
- **Policy changes** — When a human adjusts curation thresholds or scoring weights manually, those decisions calibrate all three loops.

Every feedback type has a defined capture path. Nothing is lost because the system didn't know how to record it.

**Deacon/witness feedback cycle:** Trained deacon and witness adapters score other roles' sessions during patrol. Their scores feed back into the training loop for those roles. As deacon/witness adapters improve, their scoring accuracy improves, which improves the training data for everyone else. Self-reinforcing quality spiral with human calibration as the ground truth anchor.

### Judgment as Work, Not Evaluation

LLM-as-judge is not a separate evaluation layer. It's woven into the roles themselves. The witness and deacon already monitor, review, and escalate as their core job — that job IS judging. The training signal is a byproduct, same as the core principle: every inference dollar produces real work.

**The witness judges by observing**

The witness monitors polecat sessions in real time. When it flags a problem, escalates to the deacon, or notes a clean completion, those are judgments made in the course of real work:
- "This polecat is stuck in an error loop" — negative signal for the session, escalation to deacon
- "Clean PR merged on first attempt" — positive signal, no intervention needed
- "Tool call pattern looks unusual but the outcome was good" — ambiguous, flag for human review

The witness doesn't score sessions on a rubric after the fact. It reacts to live work, and its reactions are the scores. Every escalation, every "all clear," every flag is a labeled data point.

**The deacon judges by reviewing**

The deacon sees patterns across the whole town during patrol. It reviews the witness's flags, evaluates formula step outcomes, and makes systemic calls:
- "Three polecats failed on the same formula step this week" — the step needs redesign, not just better models
- "Mayor's bead triage has improved since the last adapter update" — positive signal for the training pipeline
- "This convoy completed but the witness missed a regression in step 3" — calibration signal for the witness

The deacon's patrol findings improve the system at multiple levels simultaneously: the models (training data quality), the formulas (workflow design), and the tooling (what needs to be built next).

**Escalation to humans is the calibration mechanism**

Both roles escalate to humans — not as a fallback, but as a systematic calibration loop on real work:

1. Witness flags something ambiguous during live work → human reviews
2. Human's decision (agree/disagree/override) is captured against the witness's judgment
3. Disagreement patterns reveal where the witness's understanding is weak
4. Those patterns feed back into the witness's training data AND into formula refinements
5. The deacon tracks disagreement rates across roles and surfaces systemic blind spots

Humans aren't reviewing synthetic benchmarks. They're reviewing real escalations on real beads. The calibration happens on production work, so the signal is always grounded in actual outcomes.

**Building the understanding graph**

The deeper goal is not just better scores — it's filling knowledge and logic gaps across the entire system. Every judgment, escalation, and human correction identifies a piece of missing context:

- A witness escalation reveals the system doesn't understand a particular integration pattern → **knowledge gap**, add to training data
- A deacon patrol finds a formula step that consistently produces low-quality sessions → **logic gap**, redesign the formula
- A human override on a bead triage reveals the mayor doesn't understand priority signals from a specific rig → **context gap**, improve the rig's telemetry
- A pattern of failures across a formula variant reveals a missing connection between spec and plan → **understanding gap**, strengthen the formula's context injection

**Meta-judgment: the witness-witness**

Roles can observe other instances of the same role. A witness-witness monitors the primary witness's judgment quality — did it escalate appropriately? Did it miss something the human later caught? Did its scoring predictions match actual outcomes?

This isn't a special architecture. It's just another Gas Town role on a Dolt branch doing real work. The witness-witness's observations become training data for the witness role, and the witness-witness itself gets trained on the human calibration signal. Recursive self-improvement through the same production-first loop.

The deacon already plays this role structurally (reviewing witness findings during patrol), but making it explicit enables CMA-ES to optimize the meta-judgment layer independently — how much monitoring of monitors is actually useful before it's diminishing returns.

**The understanding graph**

These gaps span rigs, plans, specs, beads, code commits, formulas, telemetry, and outcomes. The judgment system maps them:

| Gap Type | Detected By | Resolved By | Improves |
|----------|-------------|-------------|----------|
| Knowledge gap | Witness flags unfamiliar pattern | Add to training data, retrain | Models |
| Logic gap | Deacon finds formula step fails repeatedly | Redesign formula step | Formulas |
| Context gap | Human overrides a role's decision | Improve telemetry or context injection | Tooling |
| Understanding gap | Cross-rig pattern analysis | Connect context across rigs in specs/plans | System graph |

The understanding graph is the map of what the system knows, what it doesn't, and where the gaps are. Every judgment interaction — witness observation, deacon review, human escalation — either confirms an edge in the graph or reveals a missing one.

**Formulation over codification**

The system doesn't try to codify difficult logic into rigid rules. It formulates — expressing complex judgment as composable formulas that can be tested, tweaked, and improved through the same feedback loops:

- A scoring heuristic that works today becomes a formula step that can be A/B tested tomorrow
- A human's repeated correction pattern becomes a candidate formula refinement, not a hardcoded rule
- The deacon can propose formula modifications based on patrol findings, which get tested in the dual-branch setup

This keeps the system adaptive. Codified rules become stale. Formulated logic evolves with the data.

**Cost trajectory**

Early: frontier models (Opus, Gemini) power the witness and deacon roles. Expensive but accurate.

Mid: LoRA adapters for witness and deacon handle routine judgments. Frontier models reserved for ambiguous cases and human-escalation calibration.

Late: self-hosted judgment for most work. Frontier spend concentrated on novel situations the understanding graph hasn't mapped yet. The system knows what it doesn't know and spends accordingly.

### Implementation Phases

The methodology describes the end state. The path there must be disciplined — each layer solid before the next one goes on top. Add recursion before the foundation works and the whole thing collapses into noise.

Each phase has explicit readiness gates. You don't move to the next phase because it's exciting — you move because the current phase is producing reliable results and you can prove it.

**Phase 1 (current): Foundation**

What it does:
- Extract sessions, tag by role, filter by surface quality (content density, tool usage, depth)
- Static hyperparameters in Axolotl YAML configs
- Regex-based role_bench eval
- Per-role dataset splits exist but no per-role optimization

Readiness gate for Phase 2:
- [ ] Data pipeline runs end-to-end without manual intervention
- [ ] Per-role datasets have sufficient volume (minimum N samples per role)
- [ ] role_bench produces stable, repeatable scores across runs
- [ ] At least one training run completed successfully per role

**Phase 2: Outcome Scoring + Judgment on Real Work**

What it does:
- Link sessions to beads and formula runs for outcome-based scoring
- Witness and deacon perform judgment as part of their real work (frontier models initially)
- Human escalation loop for calibration — humans review real escalations, not synthetic benchmarks
- Multi-level scoring algorithm (turn, step, formula, cross-run)
- Session scorer replaces surface quality with outcome quality

What it does NOT do yet:
- No CMA-ES optimization (hyperparameters still manual)
- No Dolt branching or dual-branch comparison
- No formula lifecycle management
- No worktree replay

Readiness gate for Phase 3:
- [ ] Session scorer produces outcome scores that correlate with human judgment
- [ ] Witness escalations are meaningful (human agrees with escalation >X% of the time)
- [ ] Deacon patrol findings lead to actionable improvements (not just noise)
- [ ] Human calibration loop is running — disagreement patterns are logged and used
- [ ] Training on outcome-scored data produces measurably better adapters than surface-scored data

**Phase 3: Optuna Optimization + Worktree Replay**

What it does:
- Optuna rig with CMA-ES sampler per role
- Judgment role scores (from Phase 2) as the CMA-ES objective function
- Worktree replay of failed convoy legs with different configurations
- Best-of-N stitching for composite training corpus
- Formula lifecycle begins: ideation, authoring, versioning, execution, evaluation

What it does NOT do yet:
- No telemetry discovery (recipe weights still manual)
- No dual-branch model comparison
- No role variants on Dolt
- No self-hosted judgment (still frontier models)

Readiness gate for Phase 4:
- [ ] CMA-ES finds per-role hyperparameters that beat hand-tuned configs
- [ ] Worktree replays produce measurably better training data than single-run data
- [ ] Formula lifecycle is producing versioned, reviewed formulas (not just ad-hoc workflows)
- [ ] The system can explain WHY a particular config won (not just that it scored higher)

**Phase 4: Dual-Branch + Role Variants + Telemetry Discovery**

What it does:
- Dual-branch comparison on Dolt — candidate (LoRA) vs reference (frontier) on real work
- DPO pairs, distillation targets, and failure mode maps from branch deltas
- Role variants on Dolt branches (witness/deacon with different configurations)
- CMA-ES explores telemetry recipe space — discovers which signals predict training quality
- Cross-role diagnostic training (witness observations train polecats, deacon findings train mayor)
- Convoy quality as a scored dimension

What it does NOT do yet:
- No self-hosted judgment (still frontier for witness/deacon)
- No formula authoring by models (humans still write formulas)
- No recursive self-improvement layers

Readiness gate for Phase 5:
- [ ] Dual-branch comparison produces DPO pairs that measurably improve adapters
- [ ] Telemetry discovery identifies signals that humans hadn't considered
- [ ] Role variants on Dolt converge — best variant configurations are clear
- [ ] Cross-role diagnostic training reduces polecat failure rate and improves convoy quality
- [ ] Candidate-reference divergence is trending down per role

**Phase 5: Self-Improving System**

What it does:
- Witness/deacon LoRA adapters replace frontier models for routine judgment
- Models author, evaluate, and refine formulas (not just execute them)
- Continuous training from production — accumulate, score, retrain, promote
- Human correction as DPO signal at every touchpoint
- Understanding graph tracks knowledge, logic, context, and understanding gaps
- System identifies its own gaps and recommends improvements
- Formula-native reasoning — models reach for formulas, collaborate over time, escalate honestly

What it does NOT do yet:
- Meta-judgment layers (witness-witness) — add only when base judgment is reliable
- CMA-ES optimization of the lifecycle itself — add only when the lifecycle is stable
- Cross-rig context enrichment — add only when single-rig training is working well

Readiness gate (ongoing):
- [ ] Self-hosted judgment quality matches frontier on routine tasks
- [ ] Model-authored formulas pass deacon review at acceptable rate
- [ ] Adapter promotion is automated and gated — no manual intervention needed
- [ ] System correctly identifies its own gaps (validated by human spot-checks)
- [ ] Frontier spend is decreasing while system quality is increasing

**Discipline principle:** Every recursive layer (judgment roles judging each other, models writing formulas that optimize formula writing, the system improving its own improvement process) gets added ONLY when the layer below it is producing reliable, measurable results. The readiness gates are not suggestions — they're hard requirements. If a gate isn't met, the answer is "improve the current phase" not "add the next layer and hope it helps."
