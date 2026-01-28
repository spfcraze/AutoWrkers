# Multi-LLM Workflow Pipeline - Implementation Plan

## Overview

Transform Autowrkers from a single-LLM issue resolver into a multi-LLM collaborative pipeline where different AI models play specialized roles (analysis, planning, implementation, review) in an iterative loop.

**Key Features:**
- Multiple LLM providers per workflow (Gemini, Claude, GPT-4/Codex, Ollama)
- Three trigger modes: GitHub Issue, Manual Task, Directory Scan
- Customizable workflow phases with skip/add capabilities
- Iterative execution with configurable retry behavior
- Parallel review phases
- Budget tracking and limits
- CLI and Web UI support
- Artifact storage and editing

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Autowrkers                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  GitHub     │  │  Manual     │  │  Directory  │  │  Existing   │        │
│  │  Issue Mode │  │  Task Mode  │  │  Scan Mode  │  │  Basic Mode │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                │                │                │               │
│         └────────────────┴────────────────┴────────────────┘               │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      WorkflowOrchestrator                            │   │
│  │  - Template loading        - Phase transitions                       │   │
│  │  - Artifact management     - Iteration control                       │   │
│  │  - Budget tracking         - Parallel execution                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                   │                                         │
│         ┌─────────────────────────┼─────────────────────────┐              │
│         ▼                         ▼                         ▼              │
│  ┌─────────────┐          ┌─────────────┐          ┌─────────────┐        │
│  │   Gemini    │          │   Claude    │          │  GPT-4/     │        │
│  │  Provider   │          │   Code      │          │  Ollama     │        │
│  │ (SDK/Router)│          │  Provider   │          │  Provider   │        │
│  └─────────────┘          └─────────────┘          └─────────────┘        │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  Storage Layer                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │   SQLite     │  │  Artifacts   │  │  Templates   │  │  Encrypted   │   │
│  │   Database   │  │  (Files)     │  │  (Global)    │  │  Keys Config │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Data Models

### 2.1 New Enums

```python
# src/workflow_models.py

class TriggerMode(Enum):
    GITHUB_ISSUE = "github_issue"
    MANUAL_TASK = "manual_task"
    DIRECTORY_SCAN = "directory_scan"

class PhaseRole(Enum):
    ANALYZER = "analyzer"           # Analyze codebase, create task list
    PLANNER = "planner"             # Create implementation plan, docs
    IMPLEMENTER = "implementer"     # Write code
    REVIEWER_FUNC = "reviewer_functional"    # Test functionality
    REVIEWER_STYLE = "reviewer_style"        # Code style, patterns
    REVIEWER_SECURITY = "reviewer_security"  # Security review
    REVIEWER_CUSTOM = "reviewer_custom"      # User-defined review
    VERIFIER = "verifier"           # Run automated checks

class PhaseStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

class WorkflowStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BUDGET_EXCEEDED = "budget_exceeded"

class ArtifactType(Enum):
    TASK_LIST = "task_list"
    CODEBASE_DOCS = "codebase_docs"
    IMPLEMENTATION_PLAN = "implementation_plan"
    CODE_DIFF = "code_diff"
    REVIEW_REPORT = "review_report"
    VERIFICATION_REPORT = "verification_report"
    CUSTOM = "custom"

class IterationBehavior(Enum):
    AUTO_ITERATE = "auto_iterate"
    PAUSE_FOR_APPROVAL = "pause_for_approval"
    CONFIGURABLE = "configurable"

class FailureBehavior(Enum):
    PAUSE_NOTIFY = "pause_notify"
    FALLBACK_PROVIDER = "fallback_provider"
    SKIP_PHASE = "skip_phase"
```

### 2.2 Core Data Classes

```python
@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider"""
    provider_type: str  # gemini_sdk, gemini_openrouter, openai, openrouter, ollama, lm_studio, claude_code
    model_name: str
    api_url: Optional[str] = None
    temperature: float = 0.1
    context_length: int = 8192
    extra_params: Dict[str, Any] = field(default_factory=dict)
    # Fallback configuration
    fallback_provider: Optional['ProviderConfig'] = None

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> 'ProviderConfig': ...


@dataclass
class WorkflowPhase:
    """Definition of a single workflow phase"""
    id: str  # UUID
    name: str
    role: PhaseRole
    provider_config: ProviderConfig
    prompt_template: str  # Template name or inline prompt
    output_artifact_type: ArtifactType
    success_pattern: str = "/complete"  # Pattern to detect completion
    can_skip: bool = True
    can_iterate: bool = False
    max_retries: int = 2
    timeout_seconds: int = 3600  # 1 hour default
    parallel_with: Optional[str] = None  # Phase ID to run in parallel
    order: int = 0

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> 'WorkflowPhase': ...


@dataclass
class WorkflowTemplate:
    """Reusable workflow template"""
    id: str  # UUID
    name: str
    description: str = ""
    phases: List[WorkflowPhase] = field(default_factory=list)
    max_iterations: int = 3
    iteration_behavior: IterationBehavior = IterationBehavior.CONFIGURABLE
    failure_behavior: FailureBehavior = FailureBehavior.PAUSE_NOTIFY
    # Budget settings
    budget_limit: Optional[float] = None  # In USD
    budget_scope: str = "execution"  # execution, project, global
    # Metadata
    is_default: bool = False
    is_global: bool = True  # Global or project-specific
    project_id: Optional[int] = None  # If project-specific
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> 'WorkflowTemplate': ...


@dataclass
class Artifact:
    """Output artifact from a phase"""
    id: str  # UUID
    workflow_execution_id: str
    phase_execution_id: str
    artifact_type: ArtifactType
    name: str
    content: str  # JSON or markdown
    file_path: str  # Path in project directory
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_edited: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> 'Artifact': ...


@dataclass
class PhaseExecution:
    """Execution record for a single phase"""
    id: str  # UUID
    workflow_execution_id: str
    phase_id: str
    phase_name: str
    phase_role: PhaseRole
    session_id: Optional[int] = None  # Link to SessionManager session
    provider_used: str = ""
    model_used: str = ""
    status: PhaseStatus = PhaseStatus.PENDING
    iteration: int = 1
    input_artifact_ids: List[str] = field(default_factory=list)
    output_artifact_id: Optional[str] = None
    # Metrics
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: str = ""

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> 'PhaseExecution': ...


@dataclass
class WorkflowExecution:
    """A running or completed workflow instance"""
    id: str  # UUID
    template_id: str
    template_name: str
    # Trigger info
    trigger_mode: TriggerMode
    project_id: Optional[int] = None
    project_path: str = ""
    issue_session_id: Optional[int] = None
    task_description: str = ""
    # State
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_phase_id: Optional[str] = None
    iteration: int = 1
    # Phases and artifacts
    phase_executions: List[PhaseExecution] = field(default_factory=list)
    artifact_ids: List[str] = field(default_factory=list)
    # Budget tracking
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_cost_usd: float = 0.0
    budget_limit: Optional[float] = None
    # Settings
    iteration_behavior: IterationBehavior = IterationBehavior.AUTO_ITERATE
    interactive_mode: bool = False
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> 'WorkflowExecution': ...


@dataclass
class BudgetTracker:
    """Track spending across executions, projects, and globally"""
    id: str
    scope: str  # execution_id, project_id, or "global"
    scope_id: str
    period_start: str  # ISO date for monthly tracking
    budget_limit: Optional[float] = None
    total_spent: float = 0.0
    token_count_input: int = 0
    token_count_output: int = 0

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> 'BudgetTracker': ...
```

### 2.3 Provider Keys Configuration

```python
@dataclass
class ProviderKeys:
    """Encrypted storage for all provider API keys"""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    # Local providers don't need keys but may have URLs
    ollama_url: str = "http://localhost:11434"
    lm_studio_url: str = "http://localhost:1234/v1"

    @classmethod
    def load(cls) -> 'ProviderKeys': ...
    def save(self): ...
    def get_key(self, provider: str) -> str: ...
    def set_key(self, provider: str, key: str): ...
    def has_key(self, provider: str) -> bool: ...
```

---

## 3. File Structure

```
src/
├── workflow/
│   ├── __init__.py
│   ├── models.py              # Data classes above
│   ├── engine.py              # WorkflowOrchestrator
│   ├── phase_runner.py        # Phase execution logic
│   ├── artifact_manager.py    # Artifact storage/retrieval
│   ├── template_manager.py    # Template CRUD
│   ├── budget_tracker.py      # Cost tracking
│   └── providers/
│       ├── __init__.py
│       ├── base.py            # Enhanced LLMProvider base
│       ├── gemini.py          # Gemini SDK + OpenRouter
│       ├── openai.py          # OpenAI direct API
│       ├── ollama.py          # Enhanced Ollama with auto-detect
│       ├── lm_studio.py       # LM Studio with auto-detect
│       └── model_registry.py  # Available models cache
├── cli/
│   ├── __init__.py
│   ├── main.py                # CLI entry point
│   ├── workflow_commands.py   # workflow subcommands
│   ├── template_commands.py   # template subcommands
│   ├── output_formatter.py    # Terminal UI formatting
│   └── interactive.py         # Interactive mode handlers
web/
├── static/
│   ├── css/
│   │   └── workflow.css       # Workflow visualization styles
│   └── js/
│       └── workflow.js        # Workflow UI logic
├── templates/
│   └── workflow.html          # Workflow management page

~/.autowrkers/
├── workflow_templates/        # Global templates (YAML)
│   ├── default_pipeline.yaml
│   └── custom_*.yaml
├── provider_keys.enc          # Encrypted API keys
└── budgets.json               # Budget tracking data

<project>/.autowrkers/
├── artifacts/                 # Workflow artifacts
│   ├── <execution_id>/
│   │   ├── task_list.json
│   │   ├── codebase_docs.md
│   │   ├── review_report.json
│   │   └── ...
└── workflow_history.json      # Execution history for this project
```

---

## 4. Database Schema Updates

```sql
-- Workflow Templates (global and project-specific)
CREATE TABLE workflow_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    phases_json TEXT NOT NULL,  -- JSON array of WorkflowPhase
    max_iterations INTEGER DEFAULT 3,
    iteration_behavior TEXT DEFAULT 'configurable',
    failure_behavior TEXT DEFAULT 'pause_notify',
    budget_limit REAL,
    budget_scope TEXT DEFAULT 'execution',
    is_default INTEGER DEFAULT 0,
    is_global INTEGER DEFAULT 1,
    project_id INTEGER REFERENCES projects(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Workflow Executions
CREATE TABLE workflow_executions (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL REFERENCES workflow_templates(id),
    template_name TEXT NOT NULL,
    trigger_mode TEXT NOT NULL,
    project_id INTEGER REFERENCES projects(id),
    project_path TEXT,
    issue_session_id INTEGER REFERENCES issue_sessions(id),
    task_description TEXT,
    status TEXT DEFAULT 'pending',
    current_phase_id TEXT,
    iteration INTEGER DEFAULT 1,
    total_tokens_input INTEGER DEFAULT 0,
    total_tokens_output INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0.0,
    budget_limit REAL,
    iteration_behavior TEXT DEFAULT 'auto_iterate',
    interactive_mode INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

-- Phase Executions
CREATE TABLE phase_executions (
    id TEXT PRIMARY KEY,
    workflow_execution_id TEXT NOT NULL REFERENCES workflow_executions(id),
    phase_id TEXT NOT NULL,
    phase_name TEXT NOT NULL,
    phase_role TEXT NOT NULL,
    session_id INTEGER,
    provider_used TEXT,
    model_used TEXT,
    status TEXT DEFAULT 'pending',
    iteration INTEGER DEFAULT 1,
    input_artifact_ids_json TEXT,  -- JSON array
    output_artifact_id TEXT,
    tokens_input INTEGER DEFAULT 0,
    tokens_output INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT
);

-- Artifacts
CREATE TABLE artifacts (
    id TEXT PRIMARY KEY,
    workflow_execution_id TEXT NOT NULL REFERENCES workflow_executions(id),
    phase_execution_id TEXT NOT NULL REFERENCES phase_executions(id),
    artifact_type TEXT NOT NULL,
    name TEXT NOT NULL,
    content TEXT,
    file_path TEXT NOT NULL,
    metadata_json TEXT,
    is_edited INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Budget Tracking
CREATE TABLE budget_tracking (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,  -- 'execution', 'project', 'global'
    scope_id TEXT NOT NULL,
    period_start TEXT NOT NULL,
    budget_limit REAL,
    total_spent REAL DEFAULT 0.0,
    token_count_input INTEGER DEFAULT 0,
    token_count_output INTEGER DEFAULT 0,
    UNIQUE(scope, scope_id, period_start)
);

-- Provider Keys (encrypted, single row)
CREATE TABLE provider_keys (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    keys_encrypted TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Available Models Cache
CREATE TABLE model_registry (
    provider TEXT NOT NULL,
    model_id TEXT NOT NULL,
    model_name TEXT,
    context_length INTEGER,
    cost_per_1k_input REAL,
    cost_per_1k_output REAL,
    capabilities_json TEXT,  -- JSON array of capabilities
    last_updated TEXT NOT NULL,
    PRIMARY KEY (provider, model_id)
);
```

---

## 5. API Endpoints

### 5.1 Workflow Templates

```
GET    /api/workflow/templates                    # List all templates
GET    /api/workflow/templates/{id}               # Get template details
POST   /api/workflow/templates                    # Create template
PUT    /api/workflow/templates/{id}               # Update template
DELETE /api/workflow/templates/{id}               # Delete template
POST   /api/workflow/templates/{id}/duplicate     # Duplicate template
POST   /api/workflow/templates/import             # Import from YAML
GET    /api/workflow/templates/{id}/export        # Export to YAML
```

### 5.2 Workflow Executions

```
GET    /api/workflow/executions                   # List executions (with filters)
GET    /api/workflow/executions/{id}              # Get execution details
POST   /api/workflow/executions                   # Start new execution
POST   /api/workflow/executions/{id}/pause        # Pause execution
POST   /api/workflow/executions/{id}/resume       # Resume execution
POST   /api/workflow/executions/{id}/cancel       # Cancel execution
POST   /api/workflow/executions/{id}/skip-phase   # Skip current phase
POST   /api/workflow/executions/{id}/approve      # Approve iteration
DELETE /api/workflow/executions/{id}              # Delete execution record
```

### 5.3 Artifacts

```
GET    /api/workflow/executions/{id}/artifacts    # List artifacts for execution
GET    /api/workflow/artifacts/{id}               # Get artifact content
PUT    /api/workflow/artifacts/{id}               # Update artifact (edit)
GET    /api/workflow/artifacts/{id}/download      # Download artifact file
```

### 5.4 Providers & Models

```
GET    /api/workflow/providers                    # List configured providers
GET    /api/workflow/providers/{provider}/models  # List available models
POST   /api/workflow/providers/{provider}/detect  # Auto-detect models
POST   /api/workflow/providers/keys               # Update provider keys
GET    /api/workflow/providers/keys/status        # Check which keys are configured
```

### 5.5 Budget

```
GET    /api/workflow/budget                       # Get budget status (all scopes)
GET    /api/workflow/budget/{scope}/{id}          # Get specific budget
PUT    /api/workflow/budget/{scope}/{id}          # Set budget limit
GET    /api/workflow/cost-estimate                # Estimate cost for workflow
```

### 5.6 WebSocket Events

```
workflow:started        # Workflow execution started
workflow:phase_started  # Phase started
workflow:phase_progress # Phase progress update (streaming output)
workflow:phase_completed # Phase completed
workflow:artifact_created # New artifact available
workflow:iteration      # New iteration started
workflow:approval_needed # Waiting for user approval
workflow:budget_warning # Approaching budget limit
workflow:completed      # Workflow completed
workflow:failed         # Workflow failed
workflow:cancelled      # Workflow cancelled
```

---

## 6. CLI Commands

### 6.1 Command Structure

```bash
autowrkers workflow <subcommand>  # Full command
autowrkers wf <subcommand>        # Alias
autowrkers run <args>             # Quick alias for 'workflow start'

# Quick start aliases
uc run --path . --task "Fix bug"   # Shortest form (if 'uc' alias configured)
```

### 6.2 Workflow Commands

```bash
# Start workflow
autowrkers workflow start \
  --path /path/to/project \
  --task "Add user authentication" \
  [--template "Gemini-Claude-Codex"] \
  [--interactive] \
  [--budget 5.00] \
  [--no-realtime]

autowrkers workflow start \
  --path /path/to/project \
  --analyze \
  [--template ...] \
  [--interactive]

autowrkers workflow start \
  --project myproject \
  --issue 42 \
  [--template ...]

# Control
autowrkers workflow status [execution-id]
autowrkers workflow list [--status running|completed|failed]
autowrkers workflow pause <execution-id>
autowrkers workflow resume <execution-id>
autowrkers workflow cancel <execution-id>
autowrkers workflow skip-phase <execution-id>
autowrkers workflow approve <execution-id>
autowrkers workflow logs <execution-id> [--phase <phase-name>]

# Artifacts
autowrkers workflow artifacts <execution-id>
autowrkers workflow artifact view <artifact-id>
autowrkers workflow artifact edit <artifact-id>
autowrkers workflow artifact export <artifact-id> [--output file.json]
```

### 6.3 Template Commands

```bash
autowrkers template list [--global] [--project <id>]
autowrkers template show <template-id>
autowrkers template create --name "My Pipeline" [--from default]
autowrkers template edit <template-id>
autowrkers template delete <template-id>
autowrkers template export <template-id> [--output pipeline.yaml]
autowrkers template import <file.yaml> [--global|--project <id>]
autowrkers template set-default <template-id>
```

### 6.4 Provider Commands

```bash
autowrkers provider list
autowrkers provider models <provider>  # List available models
autowrkers provider detect <provider>  # Auto-detect models
autowrkers provider setup              # Interactive key setup
autowrkers provider setup <provider>   # Setup specific provider
autowrkers provider test <provider>    # Test provider connectivity
```

### 6.5 Budget Commands

```bash
autowrkers budget status
autowrkers budget set --scope global --limit 50.00
autowrkers budget set --scope project --id 1 --limit 20.00
autowrkers budget reset --scope project --id 1
autowrkers budget history [--days 30]
```

---

## 7. Terminal Output Format

### 7.1 Workflow Status Display

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  🔄 WORKFLOW: Add user authentication                                        ║
║  📁 Path: /home/user/myproject                                               ║
║  📋 Template: Gemini-Claude-Codex Pipeline                                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ✅ Phase 1/5: Analysis          [Gemini]        47s    $0.02   ████████████ ║
║  ✅ Phase 2/5: Documentation     [Gemini]        32s    $0.01   ████████████ ║
║  🔄 Phase 3/5: Implementation    [Claude Code]   2m14s  $0.00   ██████░░░░░░ ║
║  ⏸️  Phase 4/5: Functional Review [GPT-4]         -      -       ░░░░░░░░░░░░ ║
║  ⏸️  Phase 5/5: Style Review      [Gemini]        -      -       ░░░░░░░░░░░░ ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  📊 Iteration: 1/3  │  💰 Cost: $0.03/$5.00  │  ⏱️  Elapsed: 3m 33s          ║
╚══════════════════════════════════════════════════════════════════════════════╝

─── Phase 3: Implementation [Claude Code] ─────────────────────────────────────
│ Implementing task 2/3: Add JWT middleware...
│ > Reading src/middleware/auth.py
│ > Creating src/middleware/jwt.py
│ > Updating src/app.py
│ > Running tests...
└──────────────────────────────────────────────────────────────────────────────

[Press 'q' to detach, 'p' to pause, 's' to skip phase, 'e' to expand/collapse]
```

### 7.2 Color Coding

```python
COLORS = {
    'completed': 'green',      # ✅
    'running': 'yellow',       # 🔄
    'pending': 'dim',          # ⏸️
    'failed': 'red',           # ❌
    'skipped': 'cyan',         # ⏭️
    'paused': 'magenta',       # ⏯️
    'budget_warning': 'orange', # ⚠️
}
```

### 7.3 Collapsible Output

```
─── Phase 3: Implementation [Claude Code] ─────────────────────────── [+] ────
│ ... 47 lines hidden. Press 'e' to expand.
│ 
│ [Last 5 lines]
│ > Creating src/middleware/jwt.py
│ > Updating src/app.py
│ > Running tests...
│ > All tests passed
│ > Committing changes...
└──────────────────────────────────────────────────────────────────────────────
```

---

## 8. Default Workflow Template

```yaml
# ~/.autowrkers/workflow_templates/default_pipeline.yaml
name: "Gemini-Claude-Codex Pipeline"
description: "Default multi-LLM pipeline: Gemini analyzes, Claude implements, GPT-4 reviews"
max_iterations: 3
iteration_behavior: configurable
failure_behavior: pause_notify
budget_limit: null
budget_scope: execution
is_default: true

phases:
  - id: "phase-analysis"
    name: "Analysis"
    role: analyzer
    provider_config:
      provider_type: gemini_sdk
      model_name: gemini-1.5-pro
      temperature: 0.2
    prompt_template: "analyzer_prompt"
    output_artifact_type: task_list
    success_pattern: "/analysis-complete"
    can_skip: true
    can_iterate: false
    order: 1

  - id: "phase-docs"
    name: "Documentation"
    role: planner
    provider_config:
      provider_type: gemini_sdk
      model_name: gemini-1.5-pro
      temperature: 0.3
    prompt_template: "planner_prompt"
    output_artifact_type: codebase_docs
    success_pattern: "/docs-complete"
    can_skip: true
    can_iterate: false
    order: 2

  - id: "phase-implement"
    name: "Implementation"
    role: implementer
    provider_config:
      provider_type: claude_code
      model_name: ""  # Uses default Claude
    prompt_template: "implementer_prompt"
    output_artifact_type: code_diff
    success_pattern: "/complete"
    can_skip: false
    can_iterate: true
    max_retries: 2
    order: 3

  - id: "phase-review-func"
    name: "Functional Review"
    role: reviewer_functional
    provider_config:
      provider_type: openrouter
      model_name: openai/gpt-4-turbo
      temperature: 0.1
      fallback_provider:
        provider_type: ollama
        model_name: codellama:latest
    prompt_template: "reviewer_functional_prompt"
    output_artifact_type: review_report
    success_pattern: "/review-complete"
    can_skip: true
    can_iterate: false
    order: 4

  - id: "phase-review-style"
    name: "Style Review"
    role: reviewer_style
    provider_config:
      provider_type: gemini_sdk
      model_name: gemini-1.5-flash
      temperature: 0.1
    prompt_template: "reviewer_style_prompt"
    output_artifact_type: review_report
    success_pattern: "/review-complete"
    can_skip: true
    can_iterate: false
    parallel_with: "phase-review-func"
    order: 5

  - id: "phase-verify"
    name: "Verification"
    role: verifier
    provider_config:
      provider_type: none  # Uses project lint/test/build commands
    prompt_template: null
    output_artifact_type: verification_report
    success_pattern: null  # Determined by command exit codes
    can_skip: false
    can_iterate: false
    order: 6
```

---

## 9. Prompt Templates

### 9.1 Analyzer Prompt

```markdown
# Role: Codebase Analyzer

You are analyzing a codebase to create a structured task list for implementation.

## Project Path
{{ project_path }}

## Task Description
{{ task_description }}

## Instructions

1. Explore the codebase structure to understand the architecture
2. Identify files relevant to the task
3. Analyze dependencies and potential impact areas
4. Create a prioritized task list

## Output Format

When complete, output a JSON task list in this format, then type `/analysis-complete`:

```json
{
  "summary": "Brief summary of what needs to be done",
  "complexity": "low|medium|high",
  "estimated_time": "e.g., 2-4 hours",
  "tasks": [
    {
      "id": 1,
      "title": "Task title",
      "description": "Detailed description",
      "files": ["src/file1.py", "src/file2.py"],
      "priority": "high|medium|low",
      "dependencies": []  // IDs of tasks this depends on
    }
  ],
  "risks": ["Potential risk 1", "Potential risk 2"],
  "questions": ["Clarification needed on X"]
}
```

/analysis-complete
```

### 9.2 Implementer Prompt

```markdown
# Role: Code Implementer

You are implementing code changes based on a structured task list.

## Project Path
{{ project_path }}

## Task List
{{ artifact:task_list }}

## Codebase Documentation
{{ artifact:codebase_docs }}

## Instructions

1. Implement each task in priority order
2. Follow existing code patterns and style
3. Write/update tests for changes
4. Commit after each logical unit with message: "Task N: <description>"
5. Run verification commands if available:
   - Lint: {{ lint_command }}
   - Test: {{ test_command }}
   - Build: {{ build_command }}

## Iteration Context
{% if iteration > 1 %}
This is iteration {{ iteration }}. Previous review feedback:
{{ artifact:review_report }}

Focus on addressing the issues raised.
{% endif %}

When all tasks are complete and tests pass, type `/complete`
```

### 9.3 Reviewer Prompt (Functional)

```markdown
# Role: Functional Code Reviewer

You are reviewing code changes for functional correctness.

## Project Path
{{ project_path }}

## Original Task
{{ task_description }}

## Task List
{{ artifact:task_list }}

## Code Changes
{{ artifact:code_diff }}

## Instructions

1. Review each change for functional correctness
2. Verify the implementation matches the task requirements
3. Check for edge cases and error handling
4. Identify potential bugs or issues

## Output Format

```json
{
  "approved": true|false,
  "summary": "Overall assessment",
  "issues": [
    {
      "severity": "critical|major|minor",
      "file": "path/to/file.py",
      "line": 42,
      "description": "Issue description",
      "suggestion": "How to fix"
    }
  ],
  "suggestions": [
    "Optional improvement suggestions"
  ]
}
```

/review-complete
```

---

## 10. Implementation Phases

### Phase 1: Foundation (Days 1-3)
- [ ] Create `src/workflow/models.py` with all data classes
- [ ] Update database schema with new tables
- [ ] Create `src/workflow/template_manager.py`
- [ ] Create default workflow template YAML
- [ ] Add provider keys encrypted storage

### Phase 2: Provider Extensions (Days 4-6)
- [ ] Create `src/workflow/providers/gemini.py` (SDK + OpenRouter)
- [ ] Create `src/workflow/providers/openai.py` (direct API)
- [ ] Enhance `src/workflow/providers/ollama.py` with auto-detect
- [ ] Enhance `src/workflow/providers/lm_studio.py` with auto-detect
- [ ] Create `src/workflow/providers/model_registry.py`
- [ ] Implement provider key prompting on first use

### Phase 3: Workflow Engine (Days 7-10)
- [ ] Create `src/workflow/engine.py` (WorkflowOrchestrator)
- [ ] Create `src/workflow/phase_runner.py`
- [ ] Create `src/workflow/artifact_manager.py`
- [ ] Implement phase transitions and state machine
- [ ] Implement parallel phase execution
- [ ] Implement iteration control and feedback loops
- [ ] Create `src/workflow/budget_tracker.py`

### Phase 4: CLI Implementation (Days 11-13)
- [ ] Create `src/cli/main.py` entry point
- [ ] Create `src/cli/workflow_commands.py`
- [ ] Create `src/cli/template_commands.py`
- [ ] Create `src/cli/output_formatter.py` (terminal UI)
- [ ] Create `src/cli/interactive.py`
- [ ] Add command aliases (`wf`, `run`, `uc`)

### Phase 5: API & WebSocket (Days 14-16)
- [ ] Add workflow API endpoints to `server.py`
- [ ] Add artifact API endpoints
- [ ] Add provider/budget API endpoints
- [ ] Implement WebSocket events for workflow updates
- [ ] Update existing automation to optionally use workflows

### Phase 6: Web UI (Days 17-20)
- [ ] Create `web/templates/workflow.html`
- [ ] Create `web/static/css/workflow.css`
- [ ] Create `web/static/js/workflow.js`
- [ ] Implement workflow visualization with phase indicators
- [ ] Implement artifact viewer/editor
- [ ] Add workflow triggers to Issues page
- [ ] Add provider key management UI

### Phase 7: Testing & Polish (Days 21-23)
- [ ] Unit tests for workflow engine
- [ ] Integration tests for provider interactions
- [ ] End-to-end workflow tests
- [ ] Documentation updates
- [ ] Error handling and edge cases

---

## 11. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| API rate limits | Implement exponential backoff, fallback providers |
| Infinite loops | Max iterations, quality gate detection |
| Budget overruns | Real-time tracking, hard limits, pause on threshold |
| Provider failures | Fallback chain, graceful degradation |
| Artifact corruption | Validation, checksums, backup before edit |
| Parallel race conditions | Synchronization barriers, atomic operations |

---

## 12. Success Criteria

1. ✅ Can run complete pipeline: Gemini → Claude → GPT-4/Gemini review
2. ✅ All three trigger modes work (GitHub, Manual, Directory Scan)
3. ✅ CLI and Web UI both functional
4. ✅ Iteration with feedback loops working
5. ✅ Parallel reviews execute correctly
6. ✅ Budget tracking accurate within 5%
7. ✅ Artifacts stored and editable
8. ✅ Templates exportable/importable
9. ✅ Provider auto-detection works for Ollama/LM Studio
10. ✅ Graceful failure handling with fallbacks

---

## Appendix A: Token Cost Estimates

| Provider | Model | Input ($/1K) | Output ($/1K) |
|----------|-------|--------------|---------------|
| Gemini | gemini-1.5-pro | $0.00125 | $0.005 |
| Gemini | gemini-1.5-flash | $0.000075 | $0.0003 |
| OpenAI | gpt-4-turbo | $0.01 | $0.03 |
| OpenAI | gpt-4o | $0.005 | $0.015 |
| OpenRouter | varies | varies | varies |
| Ollama | local | $0.00 | $0.00 |
| LM Studio | local | $0.00 | $0.00 |
| Claude Code | CLI | N/A | N/A |

---

## Appendix B: State Transition Matrix

| From State | Event | To State | Condition |
|------------|-------|----------|-----------|
| PENDING | start | RUNNING | - |
| RUNNING | phase_complete | RUNNING | more phases |
| RUNNING | phase_complete | AWAITING_APPROVAL | iteration_behavior=pause |
| RUNNING | all_phases_done | COMPLETED | all passed |
| RUNNING | review_failed | RUNNING | iteration < max |
| RUNNING | review_failed | FAILED | iteration >= max |
| RUNNING | budget_exceeded | BUDGET_EXCEEDED | cost > limit |
| RUNNING | pause | PAUSED | - |
| RUNNING | cancel | CANCELLED | - |
| RUNNING | error | FAILED | - |
| PAUSED | resume | RUNNING | - |
| AWAITING_APPROVAL | approve | RUNNING | - |
| AWAITING_APPROVAL | reject | FAILED | - |
