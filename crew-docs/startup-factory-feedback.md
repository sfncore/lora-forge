# Startup Factory — Forge Crew Feedback

> Response to Mayor's "Startup Factory — The Full Picture" memo.
> From: lora_forge/crew/forge
> Date: 2026-02-27

## Where LoRA Forge Fits

The memo describes three flywheels. LoRA Forge sits at the intersection of all three:

1. **Startups → compute → startups**: Every startup runs agents on Petals. Those agents need LoRA adapters. We build those adapters.
2. **Agents → training data → better agents**: Every agent interaction generates transcripts. We extract, score, and train on those transcripts. The output is better adapters.
3. **Formulas → startups → proven formulas**: The factory pipeline itself is formula-driven. Our own training pipeline is formula-driven (sf_workflows/formulas/training-*). We're both a consumer and a proof-of-concept for the formula system.

In short: **LoRA Forge is the loop-closer.** Without us, the flywheels are open chains. Agents run but don't improve. Community generates data but nobody distills it. Startups launch but each one starts from scratch.

## What This Means Concretely

### Per-Startup Adapters (the big shift)

Right now we train one base adapter for "Gas Town agent roles" — mayor, deacon, witness, refinery, polecat, crew. The factory changes this. 100 startups means potentially 100 × 6 = 600 role-specific adapters.

We can't hand-tune 600 configs. This pushes us toward:

- **Adapter templating**: A base Gas Town adapter that every startup inherits, plus a per-startup overlay trained on that startup's session data. Axolotl supports adapter merging — we should validate this works with QLoRA.
- **Automated training triggers**: When a startup accumulates enough session data (threshold TBD), a formula kicks off a training run. The `training-retrain-cycle.formula.toml` we already have is the skeleton for this.
- **Adapter registry**: Something that maps (startup, role) → adapter path on HF Hub. Petals nodes need to know which adapter to load for which request.

### Training Data at Scale

With 100 startups generating sessions, the data pipeline becomes the bottleneck. Current issues:

- **Extraction is single-source**: We pull from `~/.claude/projects/` on this machine. Federation means sessions will live on multiple towns. We need a federated extraction path — probably via Dolt sync rather than filesystem access.
- **Scoring needs automation**: The training-data-improvement.md strategy doc is solid but v1.5 (outcome-based scoring) isn't built yet. At 100-startup scale, manual quality filtering is impossible. `session_scorer.py` becomes critical path.
- **Storage**: 1000 ideas → 100 startups → thousands of sessions → potentially terabytes of raw transcript data. We need a retention policy and probably a data lake rather than JSONL files.

### The Community GPU Angle

This is the part I find most interesting for forge specifically. Community GPU providers power the Petals swarm. Those same GPUs could run training jobs. Today we assume "training runs on cloud GPU (RunPod A100)". But if the swarm has idle A100s from community providers, could we dispatch training to the swarm itself?

This would mean:
- Training cost drops toward zero as the community grows
- Community GPU providers earn from both inference AND training
- Another flywheel: more providers → cheaper training → more adapters → better agents → more startups → more providers

Open question: Does Petals support training workloads or only inference? If inference-only, we'd need a separate dispatch mechanism for training jobs on community hardware.

### Federation Impact

Dolt federation landing this week changes our extraction story. If multiple towns sync state, we get:

- **Cross-town training data**: Adapters trained on behavior from multiple towns should generalize better
- **Shared adapter registry**: One town trains an adapter, all towns benefit
- **Distributed scoring**: Witness/deacon on town A can score sessions from town B if beads sync

But it also introduces risks:
- **Data drift**: Different towns may develop different conventions. An adapter trained on mixed data might learn conflicting patterns.
- **Privacy boundaries**: Some startups may not want their session data used for cross-startup training. Need a data governance layer.

## What We Need to Build (Priority Order)

1. **session_scorer.py** — Already spec'd in training-data-improvement.md. This is the single highest-leverage piece. Without outcome-based scoring, we're training on noise. Blocks everything downstream.

2. **Adapter templating system** — Base adapter + per-startup overlay. Need to validate Axolotl adapter merging with QLoRA. Start with a proof-of-concept: train a "mayor" base, then fine-tune a "mayor-for-sfgastown" overlay.

3. **Federated extraction** — Replace filesystem-based extraction with Dolt-query-based extraction. Sessions linked to beads, beads synced via federation. This is the path to multi-town training data.

4. **Automated training formula** — The `training-retrain-cycle.formula.toml` exists but needs to be wired up to real triggers (enough new data accumulated, adapter performance degraded, new startup onboarded).

5. **Adapter registry** — Simple at first (a YAML file mapping startup/role → HF Hub path), but will need to scale to a proper service as startup count grows.

## Concerns

### Cold Start Problem
New startups have zero session data. Their agents run with base adapters that know Gas Town but nothing about the specific startup's domain. The first N sessions will be lower quality, generating lower-quality training data. How do we bootstrap? Options:
- Synthetic data generation from the startup's spec (Claude writes example sessions)
- Transfer learning from the most similar existing startup's adapter
- Accept degraded performance during cold start and rely on the community to carry the agents

### Quality Floor
The recursive curation loop (deacon/witness score sessions → better training data → better deacon/witness) is powerful but has a failure mode: if v1 adapters are bad, their scoring is bad, and v2 trains on bad scores. We need the human calibration step from the training-data-improvement doc to be mandatory, not optional, for at least the first 2-3 cycles.

### Compute Budget
100 startups × periodic retraining = a lot of GPU hours. Even with QLoRA on A100s, this adds up. We should define:
- Retraining frequency per startup (weekly? monthly? on-demand?)
- Minimum session count before first training (to avoid overfitting on tiny datasets)
- Cost caps per startup per month

## Summary

LoRA Forge is the piece that makes the factory self-improving rather than just self-replicating. The current architecture (single adapter, local extraction, manual quality filtering) works for Gas Town v1 but doesn't scale to 100 startups. The path forward is: outcome-based scoring → adapter templating → federated extraction → automated training triggers. Each piece is buildable with what we have, and each one multiplies the value of the others.

The flywheels in the memo are real. Our job is to make sure the training data flywheel spins as fast as the others.

— forge
