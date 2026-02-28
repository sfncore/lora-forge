# Formula Patterns Analysis Report

## Introduction

This report analyzes the patterns and structures of four key formulas in the Gas Town ecosystem to provide recommendations for training formula development. The analyzed formulas are:

1. **spec-project-workflow** - Complete project-level pipeline from idea to ready-to-build beads
2. **cross-rig-improvement** - Standalone workflow for cross-rig improvements with quality gates
3. **code-review** - Convoy-style formula for comprehensive code review via parallel specialized reviewers
4. **mol-deacon-patrol** - Mayor's daemon patrol loop for system health monitoring

## Pattern Analysis

### 1. spec-project-workflow Formula Patterns

The `spec-project-workflow` formula follows a comprehensive **expansion/workflow pattern** with these key characteristics:

- **Multi-phase Pipeline Structure**: Organized into distinct phases (Setup, Discovery, Design, Implementation, Execution) with clear handoffs
- **Cross-Rig Coordination**: Explicitly handles multiple target rigs with crew discovery and integration validation
- **Context Enrichment**: Uses DeepWiki context injection for token-efficient cross-rig awareness
- **Human-in-the-Loop Gates**: Strategic human approval points at critical decision boundaries
- **Quality Assurance**: Built-in quality gates including bv robot triage and outcomes verification
- **Incremental Rig Addition**: Supports dynamic addition of new rigs during discovery phase
- **Discord Integration**: Creates project threads for team communication and visibility

Key structural elements:
- Step-by-step sequential execution with dependency chains (`needs` field)
- Comprehensive variable definitions with validation
- Detailed step descriptions with process instructions and outputs
- Composition of expansion formulas for modularity

### 2. cross-rig-improvement Formula Patterns

The `cross-rig-improvement` formula demonstrates a **focused workflow pattern** optimized for cross-rig improvements:

- **Token Efficiency**: Heavy emphasis on DeepWiki context condensation (95%+ token reduction)
- **Quality-Gated Execution**: Every bead undergoes quality audit via bv robot before execution
- **Outcomes Contract**: Explicit outcomes definition creates verifiable success criteria
- **Label-Based Filtering**: Uses `sfgastown` label for filtering in shared-prefix databases
- **Resource-Aware Execution**: Includes resource budgeting and staggered polecat dispatch
- **Verification Loop**: Final quality scores compared against baseline for process improvement

Key structural elements:
- Concise 7-step pipeline focused on core value delivery
- Strong emphasis on quality gates and verification
- Clear separation of concerns between steps
- Integration with external tools (bv, DeepWiki)

### 3. code-review Formula Patterns

The `code-review` formula implements a **convoy/parallel processing pattern**:

- **Specialized Parallel Reviewers**: Multiple polecats work in parallel, each focusing on different aspects
- **Modular Leg Definitions**: Each review aspect is defined as a separate "leg" with specific focus
- **Configurable Presets**: Different review intensities (gate, full, custom) for different scenarios
- **Structured Output Requirements**: Standardized output format across all reviewers
- **Synthesis Step**: Dedicated step to combine and deduplicate findings from all legs
- **Comprehensive Coverage**: 10 distinct review categories covering technical and process aspects

Key structural elements:
- Input flexibility (PR, files, or branch)
- Base prompt template with leg-specific injection
- Output directory structure with leg-specific files
- Synthesis step that depends on all leg completions

### 4. mol-deacon-patrol Formula Patterns

The `mol-deacon-patrol` formula follows a **daemon/polling pattern**:

- **Event-Driven Processing**: Handles callbacks from agents before performing proactive checks
- **Idle Town Principle**: Minimizes activity when the system is healthy and idle
- **Defense-in-Depth**: Multiple layers of health checking and cleanup
- **Detection vs. Execution Separation**: Detects issues but dispatches to dogs for execution
- **State Tracking**: Maintains state across cycles for intelligent decision making
- **Lifecycle Management**: Handles its own context limits and requests clean handoffs

Key structural elements:
- Sequential step execution with clear dependencies
- Comprehensive error handling and safety checks
- Resource cleanup and hygiene practices
- Context-aware decision making based on system state

## Pattern Recommendations for Training Formulas

Based on the analysis above, training formulas should incorporate the following patterns:

### 1. Core Structural Patterns

- **Step-by-Step Sequential Flow**: Use clear, numbered steps with explicit dependencies
- **Input/Output Specification**: Define inputs clearly and specify expected outputs for each step
- **Variable Validation**: Include comprehensive variable definitions with required fields and descriptions
- **Error Handling**: Provide clear guidance for handling failures and edge cases

### 2. Quality Assurance Patterns

- **Quality Gates**: Implement quality checks at critical points in the workflow
- **Verification Steps**: Include explicit verification against success criteria
- **Baseline Comparison**: Compare final results against initial baselines for improvement tracking
- **Automated Testing**: Integrate automated quality checks where possible

### 3. Collaboration Patterns

- **Human-in-the-Loop Gates**: Place strategic human approval points at critical decision boundaries
- **Communication Integration**: Integrate with team communication channels (Discord, mail)
- **Context Sharing**: Ensure relevant context is available to all participants
- **Clear Handoffs**: Define clear handoff points between automated and manual steps

### 4. Efficiency Patterns

- **Token Efficiency**: Use context condensation techniques to minimize token usage
- **Parallel Processing**: Where possible, break work into parallelizable units
- **Resource Awareness**: Consider resource constraints and implement appropriate throttling
- **Incremental Processing**: Support incremental updates rather than complete reprocessing

### 5. Maintainability Patterns

- **Modular Design**: Break complex workflows into composable expansion formulas
- **Clear Documentation**: Provide detailed step descriptions with examples
- **Version Tracking**: Include version information and change logs
- **State Management**: Track state across executions for intelligent decision making

### 6. Safety Patterns

- **Safety Checks**: Include validation steps to prevent destructive operations
- **Dry Run Support**: Where applicable, support preview/dry-run modes
- **Recovery Mechanisms**: Provide clear recovery paths for failed operations
- **Permission Boundaries**: Respect system permissions and avoid unauthorized operations

## Conclusion

The analyzed formulas demonstrate several consistent patterns that contribute to their effectiveness:

1. **Clear structure and flow** with well-defined steps and dependencies
2. **Quality assurance** through gates, verification, and baseline comparison
3. **Efficiency optimization** through token reduction, parallelization, and resource awareness
4. **Collaboration support** through communication integration and human-in-the-loop gates
5. **Safety and maintainability** through modular design, safety checks, and state management

Training formulas should adopt these patterns while tailoring them to their specific use cases. The most successful formulas balance automation with human oversight, efficiency with thoroughness, and flexibility with structure.