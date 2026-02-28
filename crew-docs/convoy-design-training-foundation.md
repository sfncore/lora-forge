# Convoy Design: Training Foundation Bootstrap

> From: lora_forge/crew/forge
> Date: 2026-02-28
> Status: DRAFT — not staged, needs human review before materialization

## Intent

An explore-by-doing convoy. Polecats go out early, report back, findings shape
next steps. The convoy learns what it's building by building it.

Some outputs are new formulas for composing future convoys. The convoy is
deliberately meta and recursive — it produces the tools to produce the next convoy.

This convoy does NOT try to build the full methodology described in the README.
It establishes the foundation: outcome scoring, OTel wiring, formula patterns,
and the first training run. It leaves breadcrumbs everywhere for deeper work.

## Convoy Structure

```
CONVOY: forge-training-foundation

WAVE 1 — EXPLORE (2 polecats, focused questions)
│
│   Intent: Answer two blocking questions before we build anything.
│   "What scoring data do we actually have?" and "What formula patterns should we follow?"
│
├── 1.1  🐾 Polecat A: Data Availability Probe
│        - Is VictoriaMetrics running? Query it. Sample real data.
│        - Trace 3-5 real sessions end-to-end: session_id → OTel logs → bead_id → bd lifecycle
│        - Sample ~/.gt/.events.jsonl — what event types exist, how many, how recent?
│        - Run `make -C data all` — report dataset stats per role (do we have enough?)
│        - Output: crew-docs/research/data-availability-report.md
│
├── 1.2  🐾 Polecat B: Formula Pattern Study
│        - Read sf_workflows formulas (spec-project-workflow, cross-rig-improvement)
│        - Read .beads/formulas/ (code-review convoy type, mol-deacon-patrol molecule)
│        - How do expansions compose into parent workflows?
│        - What pattern fits training orchestration? (workflow + expansion)
│        - What pattern fits per-role eval? (convoy with parallel legs)
│        - Output: crew-docs/research/formula-patterns-report.md
│
└── ◆ HUMAN GATE: Review both reports, decide build approach
         - If OTel data is sparse → pivot toward "get OTel running" beads
         - If OTel data exists → proceed to Wave 2
         - Formula pattern findings shape how Wave 2 formulas are structured

WAVE 2 — BUILD (sequential epics, polecats within each)
│
│   Intent: Build the scorer, then the formulas. Each epic is self-contained.
│   Polecats within an epic work on independent modules, but the epics are sequential
│   because the formulas depend on the scorer existing.
│
├── EPIC A: Session Scorer (2 polecats, then integrate)
│   │
│   │   Intent: Build session_scorer.py from the data findings in Wave 1.
│   │
│   ├── A.1  🐾 Polecat: Build OTel query layer + session-to-bead linker
│   │        (one module — otel_client.py + session_linker.py)
│   ├── A.2  🐾 Polecat: Build score composer (multi-level signal aggregation)
│   │        (session_scorer.py — consumes A.1's output)
│   ├── A.3  Integrate into pipeline.py, run on real data, validate
│   └── ◆ HUMAN GATE: Review scoring results, spot-check, calibrate weights
│
├── EPIC B: Formula Authoring (sequential — each builds on previous)
│   │
│   │   Intent: Write the missing formulas. Informed by Wave 1 pattern study.
│   │   Sequential because each formula composes the previous one.
│   │
│   ├── B.1  🐾 Write training-score-sessions.formula.toml
│   ├── B.2  🐾 Write training-retrain-cycle.formula.toml (embeds B.1 as expansion)
│   ├── B.3  🐾 Write training-eval-adapter.formula.toml (convoy type — parallel legs)
│   └── ◆ HUMAN GATE: Review formulas with mayor/overseer, dry run
│
└── EPIC C: Judgment Exploration (1 polecat, research only)
    │
    │   Intent: Don't build judgment wiring yet. Just map the territory.
    │   Runs in parallel with Epic B (no dependency).
    │
    ├── C.1  🐾 Polecat: Read witness/deacon patrol transcripts and formulas
    │        Map: which observations → which training quality signals?
    │        Map: which deacon findings → which formula quality signals?
    │        What would minimal viable judgment integration look like?
    └── C.2  Output: design doc + beads for Phase 2 judgment work

WAVE 3 — PROVE + PROPAGATE (sequential, then breadcrumbs)
│
│   Intent: End-to-end proof of life. Then leave breadcrumbs for the next convoy.
│
├── EPIC D: First Training Run
│   ├── D.1  Run scored pipeline end-to-end (make -C data all with scorer)
│   ├── D.2  Train mayor adapter on scored data (GPU — RunPod)
│   ├── D.3  Eval: regex baseline + LLM judge comparison
│   └── ◆ HUMAN GATE: Review adapter quality, decide scope of next convoy
│
├── EPIC E: Meta-Formula
│   │
│   │   Intent: The payoff. A formula that composes future training convoys.
│   │
│   └── E.1  Write convoy-compose-training.formula.toml
│            (given roles + training goal → plan → materialize beads → convoy)
│
└── EPIC F: Breadcrumbs
    │
    │   Intent: This convoy's last act is to create beads for its successor.
    │   Cross-rig beads propagate understanding across Gas Town.
    │
    ├── F.1  Retro doc: what worked, what surprised, what to explore next
    ├── F.2  Beads → Optuna rig: CMA-ES integration, search space definition
    ├── F.3  Beads → sfgastown: OTel enrichment needs, witness/deacon extensions
    ├── F.4  Beads → sf_workflows: new formula patterns discovered during B.1-B.3
    └── F.5  Beads → forge: dual-branch, worktree replay, DPO infrastructure
```

## Wave & Epic Details

---

### WAVE 1 — EXPLORE

**Intent:** Answer two blocking questions before building anything.
**Parallelism:** 2 polecats dispatched simultaneously. Each has a clear,
independent question. No shared state between them.

---

#### Polecat A: Data Availability Probe

**Assigned to:** forge crew (polecat)
**Cross-rig reads:** sfgastown/gastown-otel/, ~/.gt/.events.jsonl
**Duration:** Single session, report-back-and-done

This polecat answers: *"What scoring data do we actually have?"*

Steps:
1. Check if VictoriaMetrics is running (curl :8428/api/v1/status/tsdb)
2. Check if VictoriaLogs is running (curl :9428/select/logsql/query)
3. Query for gt.session-tagged logs — how many sessions have OTel data?
4. Sample 3-5 real sessions end-to-end: session_id → OTel logs → bead_id → bd lifecycle
5. Inspect ~/.gt/.events.jsonl — event types, volume, recency
6. Run `make -C data all` — report dataset stats per role (sample counts)
7. Write findings to `crew-docs/research/data-availability-report.md`

**Key questions the report must answer:**
- Do we have enough OTel data to build a scorer, or do we pivot to instrumentation?
- Which roles have enough training samples? Which are starved?
- Is the session → bead join path viable, or do we need a different linker?

**If OTel is down or empty:** The polecat notes this clearly. The human gate
decides whether to pivot the convoy toward "get OTel accumulating" or proceed
with heuristic-only scoring.

---

#### Polecat B: Formula Pattern Study

**Assigned to:** forge crew (polecat)
**Cross-rig reads:** sf_workflows/mayor/rig/, .beads/formulas/
**Duration:** Single session, report-back-and-done

This polecat answers: *"What formula patterns should training formulas follow?"*

Steps:
1. Read sf_workflows formulas — especially spec-project-workflow (10-step workflow),
   cross-rig-improvement (cross-rig pattern)
2. Read .beads/formulas/ — especially code-review (convoy with parallel legs),
   mol-deacon-patrol (molecule/daemon pattern)
3. Map: which formula type fits training orchestration? (workflow + expansion)
4. Map: which formula type fits per-role eval? (convoy with parallel legs)
5. Map: how do expansions embed into parent workflows? What's the composition syntax?
6. Map: what pattern fits a formula that PRODUCES other formulas? (meta-formula)
7. Write findings to `crew-docs/research/formula-patterns-report.md`

**Key questions the report must answer:**
- Concrete pattern recommendations for each training formula (B.1-B.3)
- How does expansion composition work syntactically in .formula.toml?
- Any formula patterns that don't exist yet but would be useful? (bead opportunity)

---

#### HUMAN GATE: Review Exploration Reports

**Assigned to:** human (mayor escalation)
**Blocks:** All of Wave 2

The human reviews both reports and decides:
- **If OTel data exists:** proceed to Wave 2 as designed
- **If OTel data is sparse:** pivot — create beads for instrumentation work,
  proceed with heuristic-only scoring in the scorer
- **Formula pattern findings** shape the structure of Epic B formulas

**Cross-rig:** Mayor sends mail to forge crew with go/no-go and any scope adjustments.

---

### WAVE 2 — BUILD

**Intent:** Build the scorer, then the formulas. Epics are sequential because
formulas depend on the scorer. Within each epic, polecats work on independent
modules.

**Exception:** Epic C (judgment exploration) runs in parallel with Epic B
because it has no dependency on the scorer or formulas — it's pure research.

---

#### EPIC A: Session Scorer

**Type:** workflow (2 polecats on independent modules, then integration)
**Rig:** lora_forge/crew/forge
**Depends on:** Wave 1 human gate passed
**Parallelism intent:** A.1 and A.2 are independent modules. A.1 builds the
query/link layer, A.2 builds the scoring logic that consumes it. They can work
simultaneously because the interface contract is simple (session_id → signals dict).

##### A.1 — Build OTel Query Layer + Session Linker

**Assigned to:** forge crew (polecat)

Two modules in one bead:

`data/transform/otel_client.py`:
- Query VictoriaMetrics via PromQL HTTP API (requests, no special client)
- Query VictoriaLogs via LogsQL HTTP API
- Return structured results, not raw JSON
- Handle connection failures gracefully (OTel is opt-in enrichment)
- Cache results per session to avoid hammering VM/VL during batch scoring

`data/transform/session_linker.py`:
- Takes session_id from extracted training data
- Queries OTel logs for matching gt.session resource attribute
- Extracts gt.issue (bead ID) from session's resource attributes
- Falls back to ~/.gt/.events.jsonl if OTel unavailable
- Returns: session_id → {bead_id, otel_signals} mapping

##### A.2 — Build Score Composer

**Assigned to:** forge crew (polecat)

`data/transform/session_scorer.py`:
- Takes a session with linked bead_id and OTel signals (from A.1's output)
- Computes scores at each level:
  - **Turn-level:** tool success rate, error recovery patterns
  - **Step-level:** artifact production, escalation count
  - **Formula-level:** completion rate, duration vs role median
- Composes into single quality_score via configurable weights
- Weights are the "telemetry recipe" — the vector CMA-ES will later optimize
- Priority cascade: OTel signals → bead lifecycle → events trail → heuristic

##### A.3 — Integrate + Validate

**Assigned to:** forge crew (sequential after A.1 + A.2)
**Depends on:** A.1, A.2

Wire into pipeline.py:
- Scoring runs after extraction, before formatting
- Enriches each sample's metadata with outcome_score
- quality_filter.py uses outcome_score when available, heuristic fallback
- Makefile gets a `score` target
- Run on real data. Report: coverage (% sessions scored), distribution, spot-checks.

**Output:** `crew-docs/validation/scoring-validation-report.md`

##### HUMAN GATE: Review Scoring Results

**Assigned to:** human
**Blocks:** Epic B

Spot-check the scoring:
- Do high-scoring sessions look good? Do low ones look bad?
- Is the score distribution reasonable (not all 1.0 or all 0.0)?
- Are the weights sensible? Any obvious miscalibrations?
- Ready to train on scored data?

---

#### EPIC B: Formula Authoring

**Type:** workflow (sequential — each formula composes the previous)
**Rig:** lora_forge/crew/forge
**Depends on:** Epic A human gate passed (scorer exists and is validated)
**Parallelism:** None between B.1-B.3 — each builds on the last.

##### B.1 — Write training-score-sessions.formula.toml

**Assigned to:** forge crew (polecat)
**Formula type:** workflow

Steps the formula orchestrates:
1. Discover sessions to score (scope: all / recent / unscored)
2. Run session_scorer.py on each
3. Generate scoring report (distribution, coverage, outliers)
4. Output: enriched training dataset with outcome scores

**Pattern:** Follow spec-project-workflow for step-based structure.
Use Wave 1 Polecat B's pattern report for syntax guidance.

##### B.2 — Write training-retrain-cycle.formula.toml

**Assigned to:** forge crew (polecat)
**Formula type:** workflow with embedded expansion
**Depends on:** B.1 exists

The main training orchestration formula:
1. Extract sessions (make -C data extract)
2. Score sessions (invoke training-score-sessions as expansion ← B.1)
3. Apply curation policy (threshold, exclude, downweight)
4. Format for Axolotl (make -C data transform)
5. Validate (make -C data validate)
6. Train per-role adapter (axolotl train configs/roles/{role}.yml)
7. Eval against baseline (role_bench)
8. Report results

**Composition:** Embeds B.1 as an expansion at step 2.

##### B.3 — Write training-eval-adapter.formula.toml

**Assigned to:** forge crew (polecat)
**Formula type:** convoy (parallel legs per role)
**Depends on:** B.2 exists (eval is the tail end of a retrain cycle)

Parallel legs evaluate an adapter:
- One leg per role: run role_bench scenarios against the adapter
- Each leg produces a per-role score
- Synthesis step: aggregate scores, compare to baseline, produce report
- Optional leg: LLM judge (frontier model semantic eval)

**Pattern:** Follow code-review.formula.toml for parallel-legs-then-synthesis.

##### HUMAN GATE: Review Formulas

**Assigned to:** human (mayor + overseer)
**Cross-rig:** Overseer validates composition patterns match sfgastown conventions

Dry-run the formulas without actual GPU training:
- Do the steps make sense?
- Are the compositions valid?
- Do the expansion embeddings resolve correctly?

---

#### EPIC C: Judgment Exploration (research only)

**Type:** research (1 polecat, no code output)
**Rig:** lora_forge/crew/forge
**Cross-rig reads:** sfgastown witness/deacon patrol transcripts and formulas
**Depends on:** Wave 1 human gate (runs in parallel with Epic B)
**Parallelism intent:** This is pure research with no dependency on the scorer
or formulas. It runs alongside Epic B to save time. Only 1 polecat — no risk
of overloading.

##### C.1 — Map Judgment → Training Signal Territory

**Assigned to:** forge crew (polecat)

Read witness and deacon patrol transcripts. Map the territory:
- Which witness observations correlate with training quality signals?
- Which deacon findings correlate with formula/convoy quality signals?
- How do escalation events (witness → mayor, deacon → overseer) become data?
- What does the witness-witness pattern look like? (same-role meta-judgment)
- What would minimal viable judgment integration look like?

##### C.2 — Output Design + Beads

Write `crew-docs/designs/judgment-integration-design.md`:
- Territory map from C.1
- Proposed minimal integration for Phase 2
- Identified gaps in witness/deacon telemetry

Create beads for Phase 2 judgment work (these go into Epic F breadcrumbs).

---

### WAVE 3 — PROVE + PROPAGATE

**Intent:** End-to-end proof of life, then leave breadcrumbs for the next convoy.
Everything is sequential — each epic depends on the previous.

---

#### EPIC D: First Training Run

**Type:** workflow (sequential, GPU required for D.2)
**Rig:** lora_forge/crew/forge (data), RunPod (training)
**Depends on:** Epic A complete (scored data), Epic B.1-B.2 (formulas exist)

Proof of life. Does the scored pipeline produce a working adapter?

##### D.1 — Run Scored Pipeline End-to-End

**Assigned to:** forge crew (polecat)

`make -C data all` with session_scorer active.
Output: per-role datasets in output/ with outcome scores in metadata.
Check: which roles have enough volume? Mayor likely has most data.

##### D.2 — Train Mayor Adapter

**Assigned to:** forge crew (polecat)
**Infra:** RunPod A100 or L40S via scripts/sync_data.sh

Mayor first — most session data, most observable behavior patterns
(orchestration, mail, convoy creation, formula invocation).

Use configs/roles/mayor.yml with current static hyperparameters.
Save checkpoint to output/adapters/mayor-v1-scored/.

##### D.3 — Eval: Regex Baseline + LLM Judge Comparison

**Assigned to:** forge crew (polecat)

Run role_bench with regex evaluator — record as baseline.
Run same scenarios through LLM judge (frontier model via API).
Compare: where do regex and semantic scores agree? Where do they diverge?
The divergence is signal about where role_bench needs improvement.

**Output:** `crew-docs/validation/mayor-v1-eval-report.md`

##### HUMAN GATE: Review Adapter Quality

**Assigned to:** human

Chat with the adapter. Does it feel like a mayor?
Does it use gt commands correctly? Does it formulate well?
Decide: train more roles next, or iterate on scoring first?

---

#### EPIC E: Meta-Formula

**Type:** workflow (single formula authoring task)
**Rig:** lora_forge/crew/forge
**Depends on:** Epic D human gate passed (we know the pipeline works)

**Intent:** The payoff. A formula that composes future training convoys.

##### E.1 — Write convoy-compose-training.formula.toml

**Assigned to:** forge crew (polecat)
**Formula type:** workflow

Given a set of roles and a training goal, this formula:
1. Assess: which roles need retraining? (data volume, adapter age, eval scores)
2. Plan: per-role training config (score threshold, dataset size, GPU budget)
3. Materialize: create beads for each role's training run
4. Convoy: track all training beads in a single convoy
5. Gate: human reviews the plan before dispatch

**This is the payoff.** Future training cycles don't need hand-designed convoys.
This formula composes them from the building blocks in B.1-B.3.

---

#### EPIC F: Breadcrumbs

**Type:** parallel bead creation (no dependencies between beads)
**Rig:** lora_forge/crew/forge + cross-rig beads
**Depends on:** Epic D complete (all findings available)

**Intent:** This convoy's last act is to create beads for its successor.
Cross-rig beads propagate understanding across Gas Town.

##### F.1 — Retrospective

Write `crew-docs/retrospectives/training-foundation-retro.md`:
- What worked, what surprised, what the data showed
- Which formula patterns felt natural vs forced
- Scoring calibration observations
- Recommendations for next convoy scope

##### F.2 — Beads → Optuna Rig

Beads for Phase 3 CMA-ES integration:
- Wire CMA-ES sampler to training-retrain-cycle formula
- Define per-role hyperparameter search spaces
- Build objective function from role_bench + LLM judge scores
- Connect Optuna study storage (Dolt or SQLite)

##### F.3 — Beads → sfgastown

Beads for OTel enrichment and judgment wiring:
- Missing metrics identified during Polecat A exploration
- Formula-level telemetry (step outcomes, not just formula.instantiate)
- Witness/deacon observation event structure for training pipeline consumption
- Retention policy changes if needed

##### F.4 — Beads → sf_workflows

Beads for formula pattern contributions:
- New patterns discovered during B.1-B.3 authoring
- Expansion types useful beyond training (e.g., score-and-gate expansion)
- Meta-formula patterns from E.1

##### F.5 — Beads → forge (future phases)

Beads for deeper forge work:
- Dual-branch model comparison on Dolt (Phase 4)
- DPO pair generation from production turns (Phase 4)
- Worktree replay infrastructure (Phase 4)
- Formula authoring by models (Phase 5)

---

## Cross-Rig Communication Map

```
lora_forge/crew/forge (primary)
    │
    │ READS (exploration, no write access)
    ├──reads──→ sfgastown/gastown-otel/     (OTel setup, recorder.go — Polecat A)
    ├──reads──→ sfgastown/mayor/rig/        (convoy/formula patterns — Polecat B)
    ├──reads──→ sf_workflows/mayor/rig/     (spec-project-workflow — Polecat B)
    ├──reads──→ ~/.gt/.events.jsonl         (events trail — Polecat A, Epic A)
    ├──reads──→ .beads/formulas/            (HQ formula library — Polecat B)
    │
    │ GATES (human review, scope decisions)
    ├──mail───→ mayor/                      (3 human gates: Wave 1, Epic A, Epic D)
    ├──mail───→ overseer/                   (Epic B formula review)
    │
    │ BREADCRUMBS (Epic F outputs)
    ├──beads──→ optuna rig                  (F.2 — CMA-ES integration)
    ├──beads──→ sfgastown/.beads/           (F.3 — OTel enrichment, judgment wiring)
    ├──beads──→ sf_workflows/.beads/        (F.4 — formula pattern contributions)
    │
    └──convoy─→ hq-cv-*                     (convoy tracked at HQ level)
```

## Cross-Rig Epics

Beads in Epic F may warrant cross-rig epics if the scope is large enough:

**sfgastown epic: "Training Telemetry Enrichment"** (from F.3)
- New OTel instrumentation identified during Polecat A exploration
- Formula-level telemetry: step outcomes, not just formula.instantiate
- Witness/deacon observation event structure for training pipeline consumption
- Owned by sfgastown, created by forge based on exploration findings

**sf_workflows epic: "Training Formula Patterns"** (from F.4)
- Formula composition patterns that should be standardized
- New expansion types useful beyond training (score-and-gate, meta-formula)
- Owned by sf_workflows, created by forge based on authoring experience

## Formula Types Used

| Formula | Type | Why This Type | Epic |
|---------|------|---------------|------|
| training-score-sessions | workflow | Sequential steps, single output | B.1 |
| training-retrain-cycle | workflow + expansion | Sequential, embeds scoring as expansion | B.2 |
| training-eval-adapter | convoy | Parallel per-role legs, synthesis | B.3 |
| convoy-compose-training | workflow | Sequential planning, produces beads | E.1 |

## What This Convoy Does NOT Do

Explicitly deferred to keep scope manageable:

- No Optuna/CMA-ES integration (Phase 3 — beads created in F.2)
- No dual-branch model comparison (Phase 4 — beads created in F.5)
- No witness/deacon judgment wiring (Phase 2+ — designed in C.2, beads in F.3)
- No worktree replay infrastructure (Phase 4 — beads created in F.5)
- No DPO pair generation from production (Phase 4)
- No formula authoring by models (Phase 5)
- No self-hosted judgment (Phase 5)

## Estimated Shape

- **3 waves, 6 epics, ~20 beads**
- **4 human gates** (Wave 1 review, scorer review, formula review, adapter review)
- **2 cross-rig epics** created as outputs (sfgastown, sf_workflows)
- **4 new formulas** authored as deliverables (B.1-B.3, E.1)
- **1 meta-formula** that composes future training convoys (E.1)
- **~10 breadcrumb beads** across 4 targets (F.2-F.5)
- **Max parallel polecats at any point:** 2 (Wave 1), never more

## Notes for Future Self

- **Data availability is the pivot point.** Polecat A's report (Wave 1) determines
  whether this convoy builds a real scorer or pivots to "get OTel accumulating."
  Be ready to adapt — don't over-invest in scorer design before knowing what data exists.

- **The formulas are the most valuable output.** session_scorer.py is conventional
  Python. The formulas (B.1-B.3, E.1) are what make the system self-sustaining.
  Pay extra attention to composition patterns — they're the reusable building blocks.

- **Watch for formula friction.** Which composition patterns felt natural? Which
  felt forced? That's signal about Gas Town's formula system — document it in
  the retro (F.1) and feed back to sf_workflows (F.4).

- **The first adapter will probably be mediocre.** That's fine. The point of
  Epic D is to prove the pipeline works end-to-end, not to ship a production
  adapter. The Optuna rig (Phase 3, beads in F.2) is what makes adapters good.

- **Cross-rig beads are institutional memory.** F.2-F.5 are how this convoy
  propagates understanding to the rest of Gas Town. Don't skip them — they're
  the difference between isolated work and system-wide learning.

- **Parallelism is intentional, not maximal.** This convoy never runs more than
  2 polecats simultaneously. Each parallel dispatch has a stated intent explaining
  why these specific tasks can run independently. Resist the urge to parallelize
  more — clarity of findings matters more than speed.
