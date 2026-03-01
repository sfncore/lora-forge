# Judgment Integration Design

## Territory Map: Witness/Deacon Observations → Training Quality Signals

### Current Data Flow Analysis

Based on the available documentation and codebase analysis, here's how witness and deacon observations currently relate to training quality signals:

#### Witness Observations
- **Role**: Per-rig polecat health monitor, session tracking, lease management
- **Training Data Source**: `witness_train.jsonl` (464 sessions, 12.4% of total training data)
- **Observation Patterns**: 
  - Code review and quality assessment
  - Session monitoring and health checks
  - Lease management for polecat sessions
- **Quality Signals**: Witness observations are captured in session transcripts and processed through the data pipeline into structured training samples

#### Deacon Observations  
- **Role**: Town-level watchdog, patrol cycles, health checks, wisp compaction
- **Training Data Source**: `deacon_train.jsonl` (679 sessions, 18.2% of total training data)
- **Observation Patterns**:
  - System-wide health monitoring
  - Patrol cycles across all rigs
  - Resource cleanup and hygiene
  - Escalation handling for critical issues
- **Quality Signals**: Deacon findings are similarly captured in session transcripts and converted to training data

#### Current Pipeline Structure
The data pipeline (`data/pipeline.py`) processes Claude session transcripts through several transformation stages:
1. **Session Extraction**: Parses JSONL session files with turn extraction
2. **Role Tagging**: Identifies agent roles based on path/content patterns  
3. **Tool Normalization**: Cleans and truncates tool interactions
4. **Chunking**: Creates sliding windows with tool-call boundary awareness
5. **Quality Filtering**: Detects boilerplate and applies quality scoring
6. **Deduplication**: Removes duplicate samples using SHA256 content hashing
7. **Secret Scrubbing**: Removes sensitive information (API keys, tokens, etc.)
8. **Chat Formatting**: Converts to ShareGPT format with role-specific system prompts

### Escalation Event Patterns

#### Witness → Mayor Escalations
- Occur when witness detects critical issues that require higher-level intervention
- Examples include systemic problems, resource exhaustion, or coordination failures
- These escalations become training data through the same pipeline as regular sessions

#### Deacon → Overseer Escalations  
- Triggered by town-level issues that exceed deacon's authority or capability
- Include daemon failures, cross-rig coordination problems, or infrastructure issues
- Also captured in session transcripts and processed into training samples

### Witness-Witness Meta-Judgment Patterns

Current evidence suggests limited explicit witness-witness interaction patterns. However, the convoy-style code review formula demonstrates parallel processing patterns where multiple specialized reviewers (potentially including witness roles) work independently and their findings are synthesized.

The `code-review` formula shows:
- **Specialized Parallel Reviewers**: Multiple agents focus on different aspects
- **Modular Leg Definitions**: Each review aspect is separate with specific focus
- **Synthesis Step**: Dedicated step combines and deduplicates findings from all legs

This pattern could be extended to create explicit witness-witness meta-judgment workflows.

## Minimal Viable Judgment Integration Proposal

### Phase 1: Enhanced Observation Capture

**Objective**: Improve the quality and structure of witness/deacon observations to better serve as training signals.

**Concrete Steps**:
1. **Structured Observation Templates**: Create standardized templates for witness and deacon observations that include:
   - Observation type (code quality, system health, resource usage, etc.)
   - Severity level (info, warning, error, critical)
   - Affected components/rigs
   - Recommended actions
   - Confidence score

2. **Enhanced Data Pipeline Integration**: Modify the data pipeline to:
   - Parse structured observation metadata
   - Preserve observation context and relationships
   - Generate quality scores based on observation completeness and accuracy

3. **Observation Validation**: Implement validation rules for observations to ensure they meet minimum quality standards before being processed into training data.

### Phase 2: Judgment Signal Processing

**Objective**: Process witness/deacon observations into explicit judgment signals for training.

**Concrete Steps**:
1. **Judgment Signal Extractor**: Create a new pipeline module that:
   - Identifies judgment-related content in observations
   - Extracts quality assessments and recommendations
   - Generates structured judgment signals with confidence scores

2. **Quality Signal Correlation**: Implement correlation logic that:
   - Links observations to subsequent actions/outcomes
   - Measures observation accuracy against actual results
   - Generates feedback loops for judgment quality improvement

3. **Training Data Enhancement**: Augment existing training samples with judgment signals:
   - Add judgment metadata to training samples
   - Create specialized judgment-focused training datasets
   - Implement weighted sampling based on judgment quality

### Phase 3: Active Judgment Integration

**Objective**: Enable active use of judgment signals in agent decision-making and training.

**Concrete Steps**:
1. **Judgment-Aware Agent Prompts**: Modify system prompts to include judgment context:
   - Provide relevant historical judgments for similar situations
   - Include confidence-weighted recommendations
   - Support judgment-based decision justification

2. **Judgment Feedback Loop**: Implement real-time judgment feedback:
   - Capture agent responses to judgment signals
   - Measure judgment effectiveness and accuracy
   - Continuously improve judgment models based on outcomes

3. **Cross-Role Judgment Sharing**: Enable judgment sharing between roles:
   - Witness observations inform deacon patrol priorities
   - Deacon findings guide witness code review focus
   - Mayor uses aggregated judgment signals for strategic decisions

## Identified Gaps in Witness/Deacon Telemetry

### Critical Gaps

1. **Missing Event Logging**: The expected `.events.jsonl` file is not found in the GT directory, limiting comprehensive event tracking.

2. **Limited Test Coverage**: The data pipeline has zero test coverage, making it risky to modify or extend for judgment integration.

3. **Character-Based Token Estimation**: Uses `len(content) / 4` approximation instead of proper token counting with `tiktoken`, affecting chunk quality.

4. **Hardcoded Paths**: Limits testability and flexibility of the data pipeline.

5. **Silent Failures**: Sessions can be skipped without logging the reason, making debugging difficult.

### Data Quality Gaps

1. **Imbalanced Distribution**: Mayor role dominates the dataset (40% of sessions), while polecat data is limited (only 134 sessions).

2. **Missing Structured Observation Data**: Current observations are embedded in free-form session transcripts rather than structured metadata.

3. **Limited Cross-Role Interaction Data**: Insufficient examples of witness-witness or witness-deacon collaborative judgment patterns.

4. **No Direct Metrics Access**: VictoriaMetrics/VictoriaLogs are not directly queryable, limiting real-time system monitoring integration.

### Infrastructure Gaps

1. **Missing Training Launcher**: No `run_train.sh` script for remote training orchestration.

2. **Unpinned Dependencies**: Dockerfile and setup scripts lack version pinning, affecting reproducibility.

3. **Incomplete Dataset Sync**: Current sync scripts don't handle per-role datasets comprehensively.

## Candidate Beads for Phase 2 Judgment Work

### 1. Judgment Signal Pipeline Enhancement
**Title**: Implement structured judgment signal extraction from witness/deacon observations
**Type**: task
**Priority**: P1
**Description**: Create a new data pipeline module that extracts structured judgment signals from agent observations, including quality assessments, recommendations, and confidence scores.
**Dependencies**: Requires enhanced observation templates and validation rules

### 2. Judgment-Aware Training Configuration  
**Title**: Develop judgment-aware LoRA training configurations for all Gas Town roles
**Type**: task
**Priority**: P1
**Description**: Modify existing Axolotl configurations to incorporate judgment signals as additional training features, with role-specific weighting and processing.
**Dependencies**: Requires judgment signal pipeline implementation

### 3. Cross-Role Judgment Coordination Formula
**Title**: Design and implement convoy-style judgment coordination formula
**Type**: task  
**Priority**: P2
**Description**: Create a new formula that enables coordinated judgment between witness, deacon, and other roles, with synthesis and escalation mechanisms.
**Dependencies**: Requires judgment signal infrastructure and training configurations

### 4. Judgment Quality Validation Framework
**Title**: Build comprehensive test suite for judgment signal processing
**Type**: task
**Priority**: P1
**Description**: Implement end-to-end testing for judgment signal extraction, processing, and integration, ensuring reliability and accuracy.
**Dependencies**: Should be developed alongside judgment signal pipeline

### 5. Real-time Judgment Feedback Integration
**Title**: Implement real-time judgment feedback loop for continuous improvement
**Type**: task
**Priority**: P2  
**Description**: Create infrastructure for capturing agent responses to judgment signals and using outcomes to continuously improve judgment quality.
**Dependencies**: Requires judgment-aware agent prompts and feedback collection mechanisms