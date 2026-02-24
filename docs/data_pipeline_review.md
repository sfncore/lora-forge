# Data Pipeline Review (lf-dgd)

**Date:** 2026-02-24
**Reviewer:** lora_forge/refinery
**Status:** Complete

## Executive Summary

The data pipeline implementation is **substantially complete** and aligns well with the architectural plan. All core extraction, transformation, and validation modules are implemented and follow sound design principles. The pipeline successfully processes Claude session transcripts into Axolotl-compatible ShareGPT format.

**Critical gap:** Zero test coverage. This blocks production use and makes refactoring risky.

---

## Implementation Status

### ✅ Complete Modules

| Module | File | Status | Notes |
|--------|------|--------|-------|
| Session Extractor | `data/extract/sessions.py` | ✅ Complete | Handles JSONL parsing, turn extraction, requestId grouping |
| Role Tagger | `data/transform/role_tagger.py` | ✅ Complete | Path-based + content-based fallback |
| Tool Normalizer | `data/transform/tool_normalizer.py` | ✅ Complete | Truncation, cleaning, noise removal |
| Chunker | `data/transform/chunker.py` | ✅ Complete | Sliding window, tool-call boundary awareness |
| Quality Filter | `data/transform/quality_filter.py` | ✅ Complete | Boilerplate detection, quality scoring |
| Deduplicator | `data/transform/deduplicator.py` | ✅ Complete | SHA256 content-hash on assistant responses |
| Secret Scrubber | `data/transform/secret_scrubber.py` | ✅ Complete | 12+ secret patterns (OAuth, API keys, tokens) |
| Chat Formatter | `data/transform/chat_formatter.py` | ✅ Complete | ShareGPT format with 7 role system prompts |
| Schema Validator | `data/validate/schema.py` | ✅ Complete | Format validation, alternation checking |
| Pipeline Orchestrator | `data/pipeline.py` | ✅ Complete | Full pipeline with stats, per-role splits |

### ❌ Missing Modules

| Module | Planned Location | Priority | Impact |
|--------|------------------|----------|--------|
| Dataset Stats | `data/validate/stats.py` | Medium | Cannot analyze output distribution without running full pipeline |
| Makefile | `data/Makefile` | Low | Convenience only, pipeline runnable via `python -m data.pipeline` |
| Observer Extractor | `data/extract/observers.py` | Low | Claude-mem observations marked as secondary source |

---

## Code Quality Assessment

### Strengths

1. **Clean separation of concerns** - Each transform module has a single, well-defined responsibility
2. **Defensive parsing** - Session extractor handles malformed JSON gracefully
3. **Thoughtful chunking** - Tool-call boundary preservation prevents broken tool sequences
4. **Comprehensive secret scrubbing** - Covers GitHub, Google, AWS, Anthropic, OpenAI tokens
5. **Good logging** - Pipeline provides progress updates and statistics

### Concerns

1. **No tests** - Critical gap. Any change risks silent breakage
2. **Character-based token estimation** - Uses `len(content) / 4` approximation instead of `tiktoken`
3. **Hardcoded paths** - `DEFAULT_SESSIONS_DIR = Path.home() / ".claude" / "projects"` limits testability
4. **No schema versioning** - Output format could drift without versioned validation
5. **Silent failures** - `extract_session()` returns `None` without logging why a session was skipped

---

## Plan Deviations

| Planned | Implemented | Deviation | Severity |
|---------|-------------|-----------|----------|
| `tiktoken` for token counting | Character count approximation | Minor | Low |
| `data/Makefile` for easy invocation | Direct Python module calls | Minor | Low |
| `observers.py` for Claude-mem | Not implemented | Omitted intentionally | Low |
| `stats.py` module | Not implemented | Missing | Medium |

---

## Test Coverage Gaps (Critical)

**No tests exist for any module.** Priority test coverage:

### High Priority
1. `data/extract/sessions.py`
   - Session with multi-part assistant responses (shared requestId)
   - Session with tool_use + tool_result pairs
   - Malformed JSONL handling
   - Empty session handling

2. `data/transform/chunker.py`
   - Tool-call boundary preservation (tool_use in chunk N, tool_result not split)
   - Character budget trimming
   - Edge cases: < 2 turns, exactly window_size turns

3. `data/transform/quality_filter.py`
   - Boilerplate pattern matching
   - Quality score thresholds
   - Minimum turn count enforcement

4. `data/validate/schema.py`
   - Valid ShareGPT sample acceptance
   - Invalid format rejection (wrong role order, missing fields)
   - Alternation enforcement

### Medium Priority
5. `data/transform/deduplicator.py`
   - Duplicate detection accuracy
   - Hash collision handling

6. `data/transform/secret_scrubber.py`
   - All 12+ secret patterns
   - False positive rate on normal text

7. `data/transform/role_tagger.py`
   - All 7 role directory patterns
   - Content-based fallback

8. `data/pipeline.py`
   - End-to-end pipeline execution
   - Per-role dataset splitting

---

## Recommendations

### Immediate (Blocker)
1. **Write test suite** - Start with high-priority modules above. Target 80%+ coverage on core transforms.
2. **Add `stats.py` module** - Provide dataset analysis without running full pipeline validation.

### Short-term
3. **Replace character count with tiktoken** - More accurate chunk sizing, especially for code-heavy sessions
4. **Add integration test** - Run pipeline on sample sessions, validate output format
5. **Improve error reporting** - Log reasons for session rejection, not just counts

### Optional
6. **Create `data/Makefile`** - Convenience targets: `make extract`, `make transform`, `make validate`
7. **Add config file** - Make window size, stride, quality thresholds configurable
8. **Version output schema** - Add `schema_version` field to metadata for future compatibility

---

## Verification Commands

```bash
# Run full pipeline (extract + transform)
python -m data.pipeline --verbose

# Validate output format
python -m data.validate.schema output/datasets/gastown_train.jsonl

# Check per-role datasets exist
ls -lh output/datasets/*_train.jsonl
```

---

## Conclusion

The data pipeline is **production-ready in design** but **not in reliability** due to zero test coverage. The implementation faithfully follows the plan with minor, acceptable deviations. 

**Next step:** Write comprehensive test suite (see lf-61m, lf-v4g) before using generated data for training.
