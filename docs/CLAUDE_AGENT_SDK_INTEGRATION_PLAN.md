# Claude Agent SDK Hybrid Integration Plan

## Overview

This document outlines the plan to integrate Anthropic's Claude Agent SDK with UltraClaude using a **hybrid approach**: SDK for orchestration/planning phases, tmux-based CLI for execution phases.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         UltraClaude                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                   WorkflowOrchestrator                        │   │
│  │                   (src/workflow/engine.py)                    │   │
│  └──────────────────────────────┬───────────────────────────────┘   │
│                                 │                                    │
│         ┌───────────────────────┼───────────────────────┐           │
│         │                       │                       │           │
│         ▼                       ▼                       ▼           │
│  ┌─────────────┐      ┌─────────────────┐      ┌─────────────┐      │
│  │ SDK Bridge  │      │  Phase Runner   │      │ tmux-based  │      │
│  │ (NEW)       │      │  (existing)     │      │ Sessions    │      │
│  │             │      │                 │      │ (existing)  │      │
│  │ - Planning  │      │ - Gemini/OpenAI │      │             │      │
│  │ - Analysis  │      │ - Ollama        │      │ - Claude    │      │
│  │ - Todos     │      │ - LM Studio     │      │   Code CLI  │      │
│  └──────┬──────┘      └────────┬────────┘      └──────┬──────┘      │
│         │                      │                      │              │
│         ▼                      ▼                      ▼              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                   TodoSyncManager (NEW)                       │   │
│  │            Unified todo/phase state management                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                 │                                    │
│                                 ▼                                    │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                     WebSocket API                             │   │
│  │               Real-time UI updates                            │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Implementation Phases

### Phase 1: Foundation (Days 1-2)
**Goal**: Install SDK, create bridge module, add todo models

### Phase 2: SDK Provider Integration (Days 3-4)
**Goal**: Create SDK-based provider for planning phases

### Phase 3: Todo Synchronization (Days 5-6)
**Goal**: Sync SDK todos with PhaseExecution status

### Phase 4: UI Integration (Days 7-8)
**Goal**: Real-time todo updates in web UI

### Phase 5: Testing & Polish (Days 9-10)
**Goal**: Comprehensive testing, edge cases, documentation

---

## Phase 1: Foundation

### 1.1 Install Dependencies

```bash
# Python SDK
pip install claude-agent-sdk

# Update requirements.txt
echo "claude-agent-sdk>=0.1.0" >> requirements.txt
```

### 1.2 Create Todo Models

**File**: `src/workflow/sdk_models.py`

```python
"""
SDK Todo Models - Bridge between Claude Agent SDK and UltraClaude
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class TodoStatus(Enum):
    """SDK-compatible todo status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TodoPriority(Enum):
    """Todo priority levels"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class SDKTodo:
    """Represents a todo item from Claude Agent SDK"""
    id: str
    content: str
    status: TodoStatus = TodoStatus.PENDING
    priority: TodoPriority = TodoPriority.MEDIUM
    phase_execution_id: Optional[str] = None  # Link to UltraClaude phase
    workflow_execution_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status.value,
            "priority": self.priority.value,
            "phase_execution_id": self.phase_execution_id,
            "workflow_execution_id": self.workflow_execution_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_sdk_todo(cls, sdk_todo: dict, workflow_id: str) -> "SDKTodo":
        """Create from Claude Agent SDK TodoWrite output"""
        return cls(
            id=sdk_todo.get("id", ""),
            content=sdk_todo.get("content", ""),
            status=TodoStatus(sdk_todo.get("status", "pending")),
            priority=TodoPriority(sdk_todo.get("priority", "medium")),
            workflow_execution_id=workflow_id,
        )


@dataclass
class TodoSyncState:
    """Tracks synchronization between SDK todos and phases"""
    workflow_execution_id: str
    todos: List[SDKTodo] = field(default_factory=list)
    last_sync: Optional[str] = None
    
    def get_progress(self) -> tuple[int, int]:
        """Returns (completed, total)"""
        completed = sum(1 for t in self.todos if t.status == TodoStatus.COMPLETED)
        return completed, len(self.todos)
```

### 1.3 Create Database Schema for Todos

**File**: `src/database.py` (additions)

```python
# Add to schema creation
"""
CREATE TABLE IF NOT EXISTS sdk_todos (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority TEXT NOT NULL DEFAULT 'medium',
    phase_execution_id TEXT,
    workflow_execution_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    FOREIGN KEY (workflow_execution_id) REFERENCES workflow_executions(id),
    FOREIGN KEY (phase_execution_id) REFERENCES phase_executions(id)
);

CREATE INDEX IF NOT EXISTS idx_sdk_todos_workflow ON sdk_todos(workflow_execution_id);
CREATE INDEX IF NOT EXISTS idx_sdk_todos_status ON sdk_todos(status);
"""
```

### 1.4 Create SDK Bridge Base

**File**: `src/workflow/sdk_bridge.py`

```python
"""
Claude Agent SDK Bridge - Integrates SDK with UltraClaude workflow system
"""
import asyncio
from typing import AsyncIterator, Callable, Optional, Any
from dataclasses import dataclass

from .sdk_models import SDKTodo, TodoStatus, TodoSyncState


@dataclass
class SDKConfig:
    """Configuration for SDK integration"""
    max_turns: int = 20
    timeout_seconds: int = 300
    enable_todo_sync: bool = True


class SDKBridge:
    """
    Bridge between Claude Agent SDK and UltraClaude.
    
    Handles:
    - SDK query execution
    - Todo extraction from tool_use blocks
    - Synchronization with PhaseExecution status
    """
    
    def __init__(
        self,
        config: SDKConfig | None = None,
        on_todo_update: Callable[[str, list[SDKTodo]], Any] | None = None,
        on_message: Callable[[str, str], Any] | None = None,
    ):
        self.config = config or SDKConfig()
        self._on_todo_update = on_todo_update
        self._on_message = on_message
        self._active_sessions: dict[str, TodoSyncState] = {}
    
    async def query(
        self,
        prompt: str,
        workflow_execution_id: str,
    ) -> AsyncIterator[tuple[str, list[SDKTodo] | None]]:
        """
        Execute SDK query and stream results with todo updates.
        
        Yields:
            tuple of (content_chunk, todos_if_updated)
        """
        try:
            from claude_agent_sdk import query as sdk_query, AssistantMessage, ToolUseBlock
        except ImportError:
            raise RuntimeError("claude-agent-sdk not installed. Run: pip install claude-agent-sdk")
        
        sync_state = TodoSyncState(workflow_execution_id=workflow_execution_id)
        self._active_sessions[workflow_execution_id] = sync_state
        
        try:
            async for message in sdk_query(
                prompt=prompt,
                options={"max_turns": self.config.max_turns}
            ):
                if isinstance(message, AssistantMessage):
                    # Extract content
                    content = ""
                    todos_updated = None
                    
                    for block in message.content:
                        if hasattr(block, 'text'):
                            content += block.text
                        
                        # Check for TodoWrite tool calls
                        if isinstance(block, ToolUseBlock) and block.name == "TodoWrite":
                            todos = self._parse_todos(
                                block.input.get("todos", []),
                                workflow_execution_id
                            )
                            sync_state.todos = todos
                            todos_updated = todos
                            
                            if self._on_todo_update:
                                await self._on_todo_update(workflow_execution_id, todos)
                    
                    if content:
                        yield content, todos_updated
                        
        finally:
            if workflow_execution_id in self._active_sessions:
                del self._active_sessions[workflow_execution_id]
    
    def _parse_todos(self, sdk_todos: list[dict], workflow_id: str) -> list[SDKTodo]:
        """Parse SDK todo format to our models"""
        return [
            SDKTodo.from_sdk_todo(t, workflow_id)
            for t in sdk_todos
        ]
    
    def get_todos(self, workflow_execution_id: str) -> list[SDKTodo]:
        """Get current todos for a workflow"""
        if workflow_execution_id in self._active_sessions:
            return self._active_sessions[workflow_execution_id].todos
        return []
    
    def get_progress(self, workflow_execution_id: str) -> tuple[int, int]:
        """Get (completed, total) for a workflow"""
        if workflow_execution_id in self._active_sessions:
            return self._active_sessions[workflow_execution_id].get_progress()
        return 0, 0


# Singleton instance
sdk_bridge = SDKBridge()
```

---

## Phase 2: SDK Provider Integration

### 2.1 Create SDK-based Workflow Provider

**File**: `src/workflow/providers/sdk_provider.py`

```python
"""
Claude Agent SDK Provider for Workflow Phases

Uses the SDK for planning/analysis phases where todo tracking is valuable.
"""
import asyncio
from typing import AsyncIterator, Optional
from datetime import datetime

from ..models import ProviderConfig, ProviderType
from ..sdk_bridge import sdk_bridge, SDKConfig
from ..sdk_models import SDKTodo
from . import WorkflowLLMProvider, GenerationResult


class ClaudeSDKProvider(WorkflowLLMProvider):
    """
    Provider that uses Claude Agent SDK instead of direct API calls.
    
    Benefits:
    - Native todo tracking via TodoWrite
    - Structured tool use handling
    - Better for planning/analysis phases
    """
    
    def __init__(
        self,
        config: ProviderConfig,
        workflow_execution_id: str | None = None,
    ):
        self.config = config
        self.workflow_execution_id = workflow_execution_id
        self._sdk_config = SDKConfig(
            max_turns=config.extra_params.get("max_turns", 20),
            timeout_seconds=config.extra_params.get("timeout", 300),
        )
        self._accumulated_content = ""
        self._todos: list[SDKTodo] = []
    
    async def generate(self, prompt: str) -> GenerationResult:
        """Execute SDK query and return full result"""
        content_parts = []
        
        async for chunk, todos in sdk_bridge.query(
            prompt=prompt,
            workflow_execution_id=self.workflow_execution_id or "default",
        ):
            content_parts.append(chunk)
            if todos:
                self._todos = todos
        
        full_content = "".join(content_parts)
        
        return GenerationResult(
            content=full_content,
            model_used="claude-sdk",
            tokens_input=0,  # SDK doesn't expose token counts directly
            tokens_output=0,
            metadata={
                "todos": [t.to_dict() for t in self._todos],
                "todo_progress": sdk_bridge.get_progress(
                    self.workflow_execution_id or "default"
                ),
            }
        )
    
    async def generate_stream(self, prompt: str) -> AsyncIterator[str]:
        """Stream SDK query results"""
        async for chunk, todos in sdk_bridge.query(
            prompt=prompt,
            workflow_execution_id=self.workflow_execution_id or "default",
        ):
            if todos:
                self._todos = todos
            yield chunk
    
    def get_todos(self) -> list[SDKTodo]:
        """Get todos extracted during generation"""
        return self._todos
    
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.CLAUDE_CODE  # Reuse existing type or add new


# Register with model registry
def register_sdk_provider():
    """Call during startup to register SDK provider"""
    from .registry import model_registry
    
    def create_sdk_provider(config: ProviderConfig) -> ClaudeSDKProvider:
        return ClaudeSDKProvider(config)
    
    # Register for a new provider type or override existing
    model_registry.register_factory(
        ProviderType.CLAUDE_CODE,  # Or create new ProviderType.CLAUDE_SDK
        create_sdk_provider,
        condition=lambda c: c.extra_params.get("use_sdk", False)
    )
```

### 2.2 Update Provider Registry

**File**: `src/workflow/providers/registry.py` (additions)

```python
# Add SDK provider support
def create_provider(self, config: ProviderConfig) -> WorkflowLLMProvider:
    """Create provider, preferring SDK for planning phases"""
    
    # Check if SDK should be used
    use_sdk = config.extra_params.get("use_sdk", False)
    
    if use_sdk and config.provider_type == ProviderType.CLAUDE_CODE:
        from .sdk_provider import ClaudeSDKProvider
        return ClaudeSDKProvider(config)
    
    # Fall back to existing providers
    return self._create_standard_provider(config)
```

---

## Phase 3: Todo Synchronization

### 3.1 Create Todo Sync Manager

**File**: `src/workflow/todo_sync.py`

```python
"""
Todo Synchronization Manager

Bridges SDK todos with UltraClaude's phase execution tracking.
Provides real-time updates to the web UI via WebSocket.
"""
import asyncio
from datetime import datetime
from typing import Callable, Optional, Any

from .sdk_models import SDKTodo, TodoStatus, TodoSyncState
from .models import PhaseExecution, PhaseStatus
from ..database import db


class TodoSyncManager:
    """
    Manages synchronization between:
    - Claude Agent SDK TodoWrite events
    - UltraClaude PhaseExecution status
    - WebSocket broadcasts to UI
    """
    
    def __init__(
        self,
        on_todos_changed: Callable[[str, list[dict]], Any] | None = None,
    ):
        self._on_todos_changed = on_todos_changed
        self._todo_cache: dict[str, list[SDKTodo]] = {}
    
    async def handle_todo_update(
        self,
        workflow_execution_id: str,
        todos: list[SDKTodo],
    ):
        """Called when SDK emits TodoWrite events"""
        # Update cache
        self._todo_cache[workflow_execution_id] = todos
        
        # Persist to database
        for todo in todos:
            self._save_todo(todo)
        
        # Map to phase status if applicable
        await self._sync_to_phases(workflow_execution_id, todos)
        
        # Broadcast to UI
        if self._on_todos_changed:
            await self._on_todos_changed(
                workflow_execution_id,
                [t.to_dict() for t in todos]
            )
    
    async def _sync_to_phases(
        self,
        workflow_execution_id: str,
        todos: list[SDKTodo],
    ):
        """
        Map SDK todo status to PhaseExecution status.
        
        Mapping:
        - SDK pending -> Phase PENDING
        - SDK in_progress -> Phase RUNNING
        - SDK completed -> Phase COMPLETED
        """
        for todo in todos:
            if todo.phase_execution_id:
                phase_status = self._map_todo_to_phase_status(todo.status)
                db.update_phase_execution(
                    todo.phase_execution_id,
                    {"status": phase_status.value}
                )
    
    def _map_todo_to_phase_status(self, todo_status: TodoStatus) -> PhaseStatus:
        """Map SDK todo status to phase status"""
        mapping = {
            TodoStatus.PENDING: PhaseStatus.PENDING,
            TodoStatus.IN_PROGRESS: PhaseStatus.RUNNING,
            TodoStatus.COMPLETED: PhaseStatus.COMPLETED,
            TodoStatus.CANCELLED: PhaseStatus.SKIPPED,
        }
        return mapping.get(todo_status, PhaseStatus.PENDING)
    
    def _save_todo(self, todo: SDKTodo):
        """Persist todo to database"""
        todo.updated_at = datetime.now().isoformat()
        db.upsert_sdk_todo(todo.to_dict())
    
    def get_todos(self, workflow_execution_id: str) -> list[SDKTodo]:
        """Get todos from cache or database"""
        if workflow_execution_id in self._todo_cache:
            return self._todo_cache[workflow_execution_id]
        
        # Load from database
        data = db.get_sdk_todos(workflow_execution_id)
        todos = [SDKTodo(**d) for d in data]
        self._todo_cache[workflow_execution_id] = todos
        return todos
    
    def get_progress_summary(self, workflow_execution_id: str) -> dict:
        """Get summary of todo progress"""
        todos = self.get_todos(workflow_execution_id)
        
        total = len(todos)
        if total == 0:
            return {"total": 0, "completed": 0, "in_progress": 0, "pending": 0, "percent": 0}
        
        completed = sum(1 for t in todos if t.status == TodoStatus.COMPLETED)
        in_progress = sum(1 for t in todos if t.status == TodoStatus.IN_PROGRESS)
        pending = sum(1 for t in todos if t.status == TodoStatus.PENDING)
        
        return {
            "total": total,
            "completed": completed,
            "in_progress": in_progress,
            "pending": pending,
            "percent": round(completed / total * 100),
        }


# Singleton
todo_sync_manager = TodoSyncManager()
```

### 3.2 Integrate with Workflow API

**File**: `src/workflow/api.py` (additions)

```python
# Add todo endpoints and WebSocket events

@router.get("/executions/{execution_id}/todos")
async def get_execution_todos(execution_id: str):
    """Get todos for a workflow execution"""
    from .todo_sync import todo_sync_manager
    
    todos = todo_sync_manager.get_todos(execution_id)
    progress = todo_sync_manager.get_progress_summary(execution_id)
    
    return {
        "todos": [t.to_dict() for t in todos],
        "progress": progress,
    }


# Add to WebSocket handler
async def broadcast_todo_update(execution_id: str, todos: list[dict]):
    """Broadcast todo updates to connected clients"""
    message = {
        "type": "todo_update",
        "execution_id": execution_id,
        "todos": todos,
        "progress": todo_sync_manager.get_progress_summary(execution_id),
    }
    await connection_manager.broadcast(message)
```

---

## Phase 4: UI Integration

### 4.1 Add Todo Display to Workflow UI

**File**: `web/static/js/workflow.js` (additions)

```javascript
// Add todo tracking state
this.executionTodos = new Map(); // execution_id -> todos[]

// Handle todo WebSocket updates
handleWebSocketMessage(data) {
    // ... existing handlers ...
    
    if (data.type === 'todo_update') {
        this.handleTodoUpdate(data);
    }
}

handleTodoUpdate(data) {
    const { execution_id, todos, progress } = data;
    
    // Update cache
    this.executionTodos.set(execution_id, todos);
    
    // Update UI if this execution is selected
    if (this.selectedExecution?.id === execution_id) {
        this.renderTodoProgress(progress);
        this.renderTodoList(todos);
    }
    
    // Update mini-progress in list
    this.updateExecutionCardProgress(execution_id, progress);
}

renderTodoProgress(progress) {
    const container = document.getElementById('todo-progress');
    if (!container) return;
    
    container.innerHTML = `
        <div class="todo-progress-bar">
            <div class="todo-progress-fill" style="width: ${progress.percent}%"></div>
        </div>
        <div class="todo-progress-text">
            ${progress.completed}/${progress.total} tasks 
            ${progress.in_progress > 0 ? `(${progress.in_progress} in progress)` : ''}
        </div>
    `;
}

renderTodoList(todos) {
    const container = document.getElementById('todo-list');
    if (!container) return;
    
    if (todos.length === 0) {
        container.innerHTML = '<div class="empty-todos">No tasks tracked</div>';
        return;
    }
    
    container.innerHTML = todos.map(todo => `
        <div class="todo-item todo-${todo.status}">
            <span class="todo-status-icon">${this.getTodoIcon(todo.status)}</span>
            <span class="todo-content">${this.escapeHtml(todo.content)}</span>
            <span class="todo-priority todo-priority-${todo.priority}">${todo.priority}</span>
        </div>
    `).join('');
}

getTodoIcon(status) {
    const icons = {
        'pending': '○',
        'in_progress': '◐',
        'completed': '●',
        'cancelled': '✕'
    };
    return icons[status] || '○';
}
```

### 4.2 Add Todo Styles

**File**: `web/static/css/workflow.css` (additions)

```css
/* Todo Progress */
.todo-progress-container {
    margin: 16px 0;
    padding: 12px;
    background: var(--bg-tertiary);
    border-radius: 8px;
}

.todo-progress-bar {
    height: 8px;
    background: var(--border-color);
    border-radius: 4px;
    overflow: hidden;
}

.todo-progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent-cyan), var(--accent-green));
    border-radius: 4px;
    transition: width 0.3s ease;
}

.todo-progress-text {
    margin-top: 8px;
    font-size: 12px;
    color: var(--text-secondary);
}

/* Todo List */
.todo-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-top: 16px;
}

.todo-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    background: var(--bg-secondary);
    border-radius: 6px;
    border-left: 3px solid var(--border-color);
}

.todo-item.todo-pending {
    border-left-color: var(--text-secondary);
}

.todo-item.todo-in_progress {
    border-left-color: var(--accent-cyan);
    background: rgba(88, 166, 255, 0.05);
}

.todo-item.todo-completed {
    border-left-color: var(--accent-green);
    opacity: 0.7;
}

.todo-item.todo-completed .todo-content {
    text-decoration: line-through;
}

.todo-status-icon {
    font-size: 14px;
    width: 20px;
    text-align: center;
}

.todo-item.todo-in_progress .todo-status-icon {
    color: var(--accent-cyan);
    animation: spin 2s linear infinite;
}

.todo-item.todo-completed .todo-status-icon {
    color: var(--accent-green);
}

@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

.todo-content {
    flex: 1;
    font-size: 13px;
}

.todo-priority {
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 4px;
    text-transform: uppercase;
}

.todo-priority-high {
    background: rgba(248, 81, 73, 0.2);
    color: var(--accent-red);
}

.todo-priority-medium {
    background: rgba(210, 153, 34, 0.2);
    color: var(--accent-yellow);
}

.todo-priority-low {
    background: rgba(139, 148, 158, 0.2);
    color: var(--text-secondary);
}

.empty-todos {
    text-align: center;
    padding: 20px;
    color: var(--text-secondary);
    font-style: italic;
}
```

---

## Phase 5: Testing

### 5.1 Unit Tests

**File**: `tests/test_sdk_integration.py`

```python
"""
Tests for Claude Agent SDK Integration
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from src.workflow.sdk_models import SDKTodo, TodoStatus, TodoPriority
from src.workflow.sdk_bridge import SDKBridge, SDKConfig
from src.workflow.todo_sync import TodoSyncManager


class TestSDKTodo:
    """Tests for SDKTodo model"""
    
    def test_create_from_sdk_format(self):
        sdk_data = {
            "id": "todo-1",
            "content": "Implement feature X",
            "status": "in_progress",
            "priority": "high",
        }
        
        todo = SDKTodo.from_sdk_todo(sdk_data, "workflow-123")
        
        assert todo.id == "todo-1"
        assert todo.content == "Implement feature X"
        assert todo.status == TodoStatus.IN_PROGRESS
        assert todo.priority == TodoPriority.HIGH
        assert todo.workflow_execution_id == "workflow-123"
    
    def test_to_dict(self):
        todo = SDKTodo(
            id="todo-1",
            content="Test task",
            status=TodoStatus.COMPLETED,
        )
        
        data = todo.to_dict()
        
        assert data["id"] == "todo-1"
        assert data["status"] == "completed"


class TestSDKBridge:
    """Tests for SDKBridge"""
    
    @pytest.fixture
    def bridge(self):
        return SDKBridge(config=SDKConfig(max_turns=5))
    
    def test_parse_todos(self, bridge):
        sdk_todos = [
            {"id": "1", "content": "Task 1", "status": "pending"},
            {"id": "2", "content": "Task 2", "status": "completed"},
        ]
        
        todos = bridge._parse_todos(sdk_todos, "workflow-1")
        
        assert len(todos) == 2
        assert todos[0].status == TodoStatus.PENDING
        assert todos[1].status == TodoStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_get_progress_empty(self, bridge):
        completed, total = bridge.get_progress("nonexistent")
        assert completed == 0
        assert total == 0


class TestTodoSyncManager:
    """Tests for TodoSyncManager"""
    
    @pytest.fixture
    def sync_manager(self):
        return TodoSyncManager()
    
    def test_map_todo_to_phase_status(self, sync_manager):
        from src.workflow.models import PhaseStatus
        
        assert sync_manager._map_todo_to_phase_status(TodoStatus.PENDING) == PhaseStatus.PENDING
        assert sync_manager._map_todo_to_phase_status(TodoStatus.IN_PROGRESS) == PhaseStatus.RUNNING
        assert sync_manager._map_todo_to_phase_status(TodoStatus.COMPLETED) == PhaseStatus.COMPLETED
    
    def test_get_progress_summary_empty(self, sync_manager):
        progress = sync_manager.get_progress_summary("nonexistent")
        
        assert progress["total"] == 0
        assert progress["percent"] == 0
    
    def test_get_progress_summary_with_todos(self, sync_manager):
        # Add todos to cache
        sync_manager._todo_cache["workflow-1"] = [
            SDKTodo(id="1", content="Done", status=TodoStatus.COMPLETED),
            SDKTodo(id="2", content="Working", status=TodoStatus.IN_PROGRESS),
            SDKTodo(id="3", content="Pending", status=TodoStatus.PENDING),
        ]
        
        progress = sync_manager.get_progress_summary("workflow-1")
        
        assert progress["total"] == 3
        assert progress["completed"] == 1
        assert progress["in_progress"] == 1
        assert progress["pending"] == 1
        assert progress["percent"] == 33


class TestIntegration:
    """Integration tests for SDK with workflow system"""
    
    @pytest.mark.asyncio
    async def test_todo_update_broadcasts(self):
        """Test that todo updates trigger WebSocket broadcasts"""
        broadcast_called = asyncio.Event()
        broadcast_data = []
        
        async def mock_broadcast(execution_id, todos):
            broadcast_data.append((execution_id, todos))
            broadcast_called.set()
        
        sync_manager = TodoSyncManager(on_todos_changed=mock_broadcast)
        
        todos = [
            SDKTodo(id="1", content="Test", status=TodoStatus.IN_PROGRESS, workflow_execution_id="exec-1")
        ]
        
        await sync_manager.handle_todo_update("exec-1", todos)
        
        # Wait for broadcast
        await asyncio.wait_for(broadcast_called.wait(), timeout=1.0)
        
        assert len(broadcast_data) == 1
        assert broadcast_data[0][0] == "exec-1"
```

### 5.2 Integration Test Script

**File**: `tests/test_sdk_e2e.py`

```python
"""
End-to-end tests for SDK integration
"""
import pytest
import asyncio

# Skip if SDK not installed
pytest.importorskip("claude_agent_sdk")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sdk_query_with_todos():
    """Test real SDK query that generates todos"""
    from src.workflow.sdk_bridge import sdk_bridge
    
    prompt = """
    Create a todo list for implementing a user authentication system.
    Break it down into specific tasks.
    """
    
    chunks = []
    todos = None
    
    async for chunk, updated_todos in sdk_bridge.query(
        prompt=prompt,
        workflow_execution_id="test-e2e-1"
    ):
        chunks.append(chunk)
        if updated_todos:
            todos = updated_todos
    
    # Should have received content
    assert len(chunks) > 0
    
    # Should have generated todos (if SDK properly configured)
    # Note: This may not always create todos depending on SDK behavior
    if todos:
        assert all(hasattr(t, 'status') for t in todos)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sdk_provider_in_workflow():
    """Test SDK provider within workflow execution"""
    from src.workflow.engine import workflow_orchestrator
    from src.workflow.models import TriggerMode
    
    # Create execution with SDK-enabled template
    execution = workflow_orchestrator.create_execution(
        template_id="sdk-test-template",  # Needs to exist
        trigger_mode=TriggerMode.MANUAL_TASK,
        task_description="Test SDK integration",
    )
    
    # Run and check todos are tracked
    result = await workflow_orchestrator.run(execution.id)
    
    assert result is not None
```

---

## File Structure Summary

```
src/workflow/
├── sdk_models.py          # NEW: SDK todo models
├── sdk_bridge.py          # NEW: SDK integration bridge
├── todo_sync.py           # NEW: Todo synchronization manager
├── providers/
│   └── sdk_provider.py    # NEW: SDK-based workflow provider
├── engine.py              # MODIFY: Add SDK support
├── api.py                 # MODIFY: Add todo endpoints
└── models.py              # EXISTING: Add ProviderType.CLAUDE_SDK

web/static/
├── js/
│   └── workflow.js        # MODIFY: Add todo UI
└── css/
    └── workflow.css       # MODIFY: Add todo styles

tests/
├── test_sdk_integration.py    # NEW: Unit tests
└── test_sdk_e2e.py            # NEW: E2E tests
```

---

## Rollout Checklist

### Pre-Implementation
- [ ] Install `claude-agent-sdk` package
- [ ] Verify SDK authentication works
- [ ] Create test workflow template for SDK phases

### Phase 1 (Foundation)
- [ ] Create `sdk_models.py`
- [ ] Add database schema for todos
- [ ] Create `sdk_bridge.py` base
- [ ] Unit tests for models

### Phase 2 (SDK Provider)
- [ ] Create `sdk_provider.py`
- [ ] Update provider registry
- [ ] Test SDK provider independently

### Phase 3 (Sync)
- [ ] Create `todo_sync.py`
- [ ] Add API endpoints
- [ ] WebSocket integration
- [ ] Sync tests

### Phase 4 (UI)
- [ ] Add todo JS handlers
- [ ] Add todo CSS styles
- [ ] Playwright UI tests

### Phase 5 (Polish)
- [ ] E2E integration tests
- [ ] Error handling review
- [ ] Performance testing
- [ ] Documentation update

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| SDK not available/changed | Feature flag to disable SDK mode |
| Todo sync conflicts | Conflict resolution with timestamps |
| Performance degradation | Caching layer in TodoSyncManager |
| Breaking existing workflows | SDK is opt-in via `use_sdk` flag |

---

## Success Metrics

1. **Functional**: SDK todos appear in UI during workflow execution
2. **Performance**: No noticeable latency increase
3. **Reliability**: 100% of SDK todo events captured and synced
4. **Compatibility**: All existing workflows continue to work unchanged
