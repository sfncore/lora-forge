# Evaluation Framework Review

**Bead:** lf-8gt  
**Date:** 2026-02-24  
**Reviewer:** furiosa

---

## Executive Summary

The evaluation framework provides a foundation for assessing Gas Town agent role performance through scenario-based testing. Currently **partially implemented** with key gaps in tool-use accuracy measurement and scenario coverage.

| Component | Status | Coverage |
|-----------|--------|----------|
| `role_bench.py` | ✅ Implemented | Framework ready, inference pending |
| `tool_use_accuracy.py` | ❌ Missing | Not implemented |
| Scenario files | ⚠️ Partial | 35 total (target: 60-120) |

---

## 1. Role Bench (`eval/role_bench.py`)

### Implementation Status: ✅ Functional

**Strengths:**
- Clean scenario loading (JSONL files or directories)
- Regex-based behavior scoring with pattern mapping
- Per-role aggregation in reports
- Extensible pattern system for Gas Town commands

**Current Pattern Coverage:**
```python
# 9 command patterns mapped:
- gt hook, gt mail inbox/read, gt prime
- bd create, bd close
- git status, git commit, git push
```

**Limitations:**
1. **No model inference** - Only scores pre-generated responses
2. **Simple keyword matching** - No semantic understanding
3. **Limited command coverage** - Missing patterns for `gt done`, `gt rig`, `bd mol`, etc.

**Code Quality:** Good structure, clear separation of concerns, ready for enhancement.

---

## 2. Tool Use Accuracy (`eval/tool_use_accuracy.py`)

### Implementation Status: ❌ Missing

This file was referenced in requirements but does not exist. Needed for:
- Validating XML/JSON tool call format correctness
- Measuring tool call parameter accuracy
- Detecting hallucinated vs. valid tool calls
- Scoring multi-step tool chains

**Recommended Structure:**
```python
# Tool use accuracy components needed:
- ToolCallValidator: Validates XML structure against schema
- ParameterChecker: Verifies required params present and typed
- HallucinationDetector: Flags calls to non-existent tools
- ChainAccuracy: Scores multi-step tool sequences
```

---

## 3. Scenario Coverage (`eval/prompts/`)

### Current State: 35 scenarios across 6 roles

| Role | Current | Target (10-20) | Gap |
|------|---------|----------------|-----|
| mayor | 10 | 10-20 | At minimum |
| polecat | 5 | 10-20 | +5 to +15 |
| crew | 5 | 10-20 | +5 to +15 |
| refinery | 5 | 10-20 | +5 to +15 |
| deacon | 5 | 10-20 | +5 to +15 |
| witness | 5 | 10-20 | +5 to +15 |
| **Total** | **35** | **60-120** | **+25 to +85** |

### Scenario Quality Assessment

**Good practices observed:**
- Consistent JSONL format
- Clear `role`, `scenario`, `system`, `user`, `expected_behaviors` fields
- Behavioral expectations (not exact string matches)

**Coverage Gaps by Role:**

#### Mayor (10 scenarios - best coverage)
- ✅ Hook checking, mail handling
- ✅ PR review, bead creation
- ✅ Git workflow, convoy status
- ⚠️ Missing: Cross-rig coordination, strategic planning, crisis response

#### Polecat (5 scenarios)
- ✅ Basic workflow: hook → work → PR → done
- ⚠️ Missing: Error handling, test failures, molecule workflow steps, quality gates

#### Crew (5 scenarios)
- ✅ Interactive coding, exploration
- ⚠️ Missing: Refactoring, debugging complex issues, documentation

#### Refinery (5 scenarios)
- ✅ Merge queue processing
- ⚠️ Missing: Complex conflict resolution, CI pipeline debugging, multi-PR coordination

#### Deacon (5 scenarios) - Not reviewed in detail
#### Witness (5 scenarios) - Not reviewed in detail

---

## 4. Accuracy Measurement Approach

### Current: Keyword Pattern Matching

**How it works:**
1. Load scenario with expected behaviors
2. Generate/obtain model response
3. For each expected behavior:
   - Map to regex pattern (or use words as loose pattern)
   - Search response for pattern match
4. Score = matched / total behaviors

**Pros:** Simple, fast, interpretable
**Cons:** Brittle, no semantic understanding, misses paraphrasing

### Recommended: Hybrid Scoring

```
Final Score = 0.4 * Keyword_Score + 0.6 * LLM_Judge_Score
```

**LLM Judge Prompt:**
```
Given the scenario context and model response, evaluate:
1. Did the model perform the expected actions? (Yes/Partial/No)
2. Were tool calls syntactically correct? (Yes/No)
3. Were tool calls semantically appropriate? (Yes/No)
4. Rate overall task completion (0-10)
```

### Tool Call Accuracy Metrics

When `tool_use_accuracy.py` is implemented:

| Metric | Definition |
|--------|------------|
| Format Accuracy | % of tool calls with valid XML/JSON structure |
| Param Accuracy | % of required parameters present and correctly typed |
| Tool Validity | % of tool calls to existing tools (no hallucination) |
| Execution Rate | % of tool calls that would succeed if executed |
| Chain Accuracy | % correct in multi-step tool sequences |

---

## 5. Benchmark Plan

### Phase 1: Complete Framework (Priority 1)

**Tool Use Accuracy Module** (`eval/tool_use_accuracy.py`)
- [ ] Implement ToolCallParser (extract XML/JSON tool calls)
- [ ] Implement SchemaValidator (validate against tool schemas)
- [ ] Implement HallucinationDetector (check tool existence)
- [ ] Implement ParameterValidator (check required params)
- [ ] Add 20+ unit tests for validator components

**Role Bench Enhancement**
- [ ] Add model inference integration (vLLM/Transformers)
- [ ] Expand pattern library (add gt done, bd mol, gt rig patterns)
- [ ] Add LLM judge option for semantic scoring
- [ ] Support batch evaluation

### Phase 2: Scenario Expansion (Priority 2)

Add scenarios to reach 15 per role (90 total):

**Mayor** (+5):
- Cross-rig resource coordination
- Strategic planning session
- Crisis response (agent down)
- Town-wide configuration update
- Emergency mail broadcast

**Polecat** (+10):
- Pre-flight failure investigation
- Test debugging cycle
- Complex molecule workflow
- Dependency resolution
- Handoff mid-implementation
- Quality gate failure recovery

**Crew** (+10):
- Complex refactoring task
- Performance optimization
- Documentation writing
- Bug root cause analysis
- Feature specification review

**Refinery** (+10):
- Complex merge conflict resolution
- CI pipeline failure diagnosis
- Multi-PR batch merge
- Rollback handling
- Queue priority adjustment

**Deacon** (+10):
- Agent health monitoring
- Resource allocation
- Dependency graph management
- Zombie process cleanup
- Recovery coordination

**Witness** (+10):
- Health check reporting
- Agent nudge escalation
- Session recovery handling
- Audit trail review
- Capacity planning

### Phase 3: Full Integration (Priority 3)

- [ ] CI/CD integration for automated evaluation
- [ ] Regression tracking across model versions
- [ ] Human evaluation correlation study
- [ ] Benchmark dashboard/visualization

---

## 6. Recommendations

### Immediate Actions

1. **Create `eval/tool_use_accuracy.py`** - Currently the biggest gap
2. **Expand polecat scenarios** - Most active role, needs better coverage
3. **Add LLM judge option** - Current keyword matching is too brittle

### Architecture Improvements

1. **Separate concerns:**
   - `role_bench.py` → Scenario management & reporting
   - `tool_use_accuracy.py` → Tool call validation
   - `inference.py` → Model inference wrapper
   - `scoring.py` → Pluggable scoring (keyword, LLM judge, hybrid)

2. **Configuration-driven:**
   ```yaml
   # eval/config.yaml
   scoring:
     methods: [keyword, llm_judge]
     weights: [0.4, 0.6]
   model:
     backend: vllm
     temperature: 0.0
   ```

3. **Standardized tool schemas:**
   ```json
   {
     "tool": "gt_hook",
     "required_params": [],
     "optional_params": ["--all"],
     "returns": "hook_status"
   }
   ```

---

## 7. Summary

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| P1 | Create tool_use_accuracy.py | Medium | High |
| P1 | Add model inference to role_bench | Medium | High |
| P2 | Expand scenarios (90 total) | Large | Medium |
| P2 | Add LLM judge scoring | Small | Medium |
| P3 | CI/CD integration | Medium | Low |

**Current Grade: C+**
- Framework exists and is functional
- Missing critical tool-use validation
- Scenario coverage below target
- Ready for iterative improvement

---

## Appendix: File Inventory

```
eval/
├── __init__.py              # Empty
├── role_bench.py            # ✅ 128 lines, functional
├── tool_use_accuracy.py     # ❌ Missing
└── prompts/
    ├── crew_scenarios.jsonl      # 5 scenarios
    ├── deacon_scenarios.jsonl    # 5 scenarios
    ├── mayor_scenarios.jsonl     # 10 scenarios
    ├── polecat_scenarios.jsonl   # 5 scenarios
    ├── refinery_scenarios.jsonl  # 5 scenarios
    └── witness_scenarios.jsonl   # 5 scenarios
```

**Total lines of eval code:** ~128 (role_bench only)  
**Total scenarios:** 35  
**Estimated completion:** 40%
