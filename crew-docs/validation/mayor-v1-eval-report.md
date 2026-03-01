# Mayor Adapter v1 Evaluation Report

## Overview
This report evaluates the mayor adapter (v1) using two evaluation methods:
1. **Regex Baseline**: Pattern matching against expected behaviors
2. **LLM Judge**: Semantic evaluation using Claude API

The evaluation is based on the `role_bench` framework and mayor scenarios from `eval/prompts/mayor_scenarios.jsonl`.

## Implementation Status
**Critical Finding**: The mayor adapter checkpoint from task D.2 was not found in `output/adapters/mayor-v1-scored/`. Only a README.md file exists, indicating the training step may not have been completed or the checkpoint was not saved properly.

Due to the missing adapter checkpoint, this evaluation cannot proceed with actual model inference. Instead, this report documents:

1. The evaluation framework that would be used
2. Expected methodology for both evaluation approaches  
3. Analysis structure for comparing results
4. Recommendations for completing the evaluation pipeline

## Regex Baseline Methodology

The regex baseline evaluation uses the existing `eval/role_bench.py` framework which:

- Loads scenarios from `eval/prompts/mayor_scenarios.jsonl`
- For each scenario, generates a response using the mayor adapter
- Scores responses against expected behaviors using pattern matching
- Calculates per-scenario and aggregate scores

Key components:
- `_behavior_to_pattern()`: Converts natural language behaviors to regex patterns
- `score_response()`: Evaluates model output against expected behaviors
- Command pattern mapping for Gas Town specific commands

### Expected Behaviors Coverage
The mayor scenarios cover these key Gas Town operations:
- Hook and mail checking (`gt hook`, `gt mail inbox`)
- Bead management (`bd create`, `bd close`)
- Git operations (`git status`, `git commit`, `git push`)
- Rig management (`gt rig add`)
- Convoy coordination (`gt convoy`)
- Agent health monitoring

## LLM Judge Methodology

The LLM judge approach would use Claude API to perform semantic evaluation:

1. **Input Format**: For each scenario, provide:
   - System prompt (Gas Town mayor role)
   - User prompt (scenario instruction)
   - Model response (from mayor adapter)
   - Expected behaviors (from scenario definition)

2. **Evaluation Prompt**: 
   ```
   You are an expert evaluator for Gas Town AI agents. Assess whether the model response demonstrates the expected behaviors.

   System: [system prompt]
   User: [user prompt]  
   Model Response: [model output]
   Expected Behaviors: [list of behaviors]

   For each expected behavior, rate as TRUE/FALSE with brief justification.
   ```

3. **Scoring**: Calculate agreement between regex baseline and LLM judge scores.

## Comparison Analysis Framework

### Agreement Analysis
- Scenarios where both methods agree (validated scenarios)
- High-confidence correct/incorrect responses

### Divergence Analysis  
- Scenarios where methods disagree significantly
- Root cause analysis for divergences:
  - Regex too strict/loose
  - Semantic understanding vs literal matching
  - Edge cases in command recognition

### Top Divergence Scenarios
The evaluation would identify the top 3 scenarios with highest score differences between methods.

## Current Limitations

Without the trained mayor adapter checkpoint, actual evaluation scores cannot be generated. The missing checkpoint prevents:

1. Generating actual model responses for scenarios
2. Computing real regex baseline scores
3. Obtaining LLM judge evaluations
4. Performing meaningful comparison analysis

## Recommendations

1. **Complete D.2 Training**: Ensure the mayor adapter training is completed and checkpoint is saved to `output/adapters/mayor-v1-scored/`

2. **Implement Inference Pipeline**: Extend `eval/role_bench.py` to:
   - Load the mayor adapter checkpoint
   - Generate responses for each scenario
   - Integrate with Claude API for LLM judging

3. **Add Mock Evaluation**: For immediate validation, implement a mock inference mode that simulates responses to demonstrate the evaluation framework

4. **Update Acceptance Criteria**: Given current state, the immediate deliverable should be a functional evaluation framework ready to run once the adapter is available.

## Next Steps

1. Verify D.2 training completion status
2. Implement inference capability in role_bench framework  
3. Run evaluation once adapter is available
4. Update this report with actual scores and analysis

---
*Report generated as part of Epic D: First Training Run*
*Task: lf-7v8d - D.3: Eval - regex baseline + LLM judge comparison*