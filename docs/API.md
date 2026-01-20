# API Reference

Complete API documentation for UltraClaude's REST and WebSocket endpoints.

## Table of Contents

- [Overview](#overview)
- [Authentication](#authentication)
- [Sessions API](#sessions-api)
- [Projects API](#projects-api)
- [Issues API](#issues-api)
- [Automation API](#automation-api)
- [LLM API](#llm-api)
- [WebSocket API](#websocket-api)
- [Error Handling](#error-handling)

---

## Overview

### Base URL

```
http://localhost:8420
```

### Content Type

All requests and responses use JSON:
```
Content-Type: application/json
```

### Response Format

Successful responses:
```json
{
  "success": true,
  "data": { ... }
}
```

Error responses:
```json
{
  "detail": "Error message"
}
```

---

## Authentication

Currently, UltraClaude does not require API authentication. GitHub tokens are stored per-project and used for GitHub API calls only.

---

## Sessions API

### List All Sessions

```http
GET /api/sessions
```

**Response:**
```json
{
  "sessions": [
    {
      "id": 1,
      "name": "Fix login bug",
      "working_dir": "/home/user/project",
      "status": "running",
      "tmux_session": "ultraclaude_1",
      "created_at": "2024-01-15T10:30:00",
      "parent_id": null
    }
  ]
}
```

### Create Session

```http
POST /api/sessions
```

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| name | string | No | Session name |
| working_dir | string | No | Working directory path |
| parent_id | integer | No | Parent session ID for queuing |
| initial_prompt | string | No | Initial prompt to send |

**Request:**
```json
{
  "name": "Implement feature",
  "working_dir": "/home/user/project",
  "initial_prompt": "Add user authentication"
}
```

**Response:**
```json
{
  "success": true,
  "session": {
    "id": 2,
    "name": "Implement feature",
    "status": "running",
    ...
  }
}
```

### Get Session

```http
GET /api/sessions/{session_id}
```

**Response:**
```json
{
  "session": {
    "id": 1,
    "name": "Fix login bug",
    "status": "running",
    ...
  }
}
```

### Get Session Output

```http
GET /api/sessions/{session_id}/output
```

**Response:**
```json
{
  "output": "Claude Code session output text..."
}
```

### Send Input to Session

```http
POST /api/sessions/{session_id}/input
```

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| data | string | Yes | Input text to send |

**Request:**
```json
{
  "data": "Please add error handling"
}
```

**Response:**
```json
{
  "success": true
}
```

### Stop Session

```http
POST /api/sessions/{session_id}/stop
```

**Response:**
```json
{
  "success": true
}
```

### Complete Session

```http
POST /api/sessions/{session_id}/complete
```

Mark a session as completed, triggering any queued child sessions.

**Response:**
```json
{
  "success": true
}
```

### Update Session Parent

```http
POST /api/sessions/{session_id}/parent
```

**Request:**
```json
{
  "parent_id": 5
}
```

**Response:**
```json
{
  "success": true,
  "session": { ... }
}
```

### Get Queued Sessions

```http
GET /api/sessions/queued?parent_id={parent_id}
```

**Response:**
```json
{
  "sessions": [ ... ]
}
```

---

## Projects API

### List Projects

```http
GET /api/projects
```

**Response:**
```json
{
  "projects": [
    {
      "id": 1,
      "name": "My Project",
      "github_repo": "user/repo",
      "working_dir": "/home/user/project",
      "default_branch": "main",
      "status": "running",
      "has_token": true,
      "last_sync": "2024-01-15T12:00:00"
    }
  ]
}
```

### Create Project

```http
POST /api/projects
```

**Request:**
```json
{
  "name": "My Project",
  "github_repo": "user/repo",
  "github_token": "ghp_xxxxx",
  "working_dir": "/home/user/project",
  "default_branch": "main",
  "auto_sync": true,
  "auto_start": false,
  "max_concurrent": 1,
  "lint_command": "npm run lint",
  "test_command": "npm test",
  "build_command": "npm run build",
  "issue_filter": {
    "labels": ["bug", "enhancement"],
    "exclude_labels": ["wontfix"]
  },
  "llm_provider": "claude_code",
  "llm_model": "",
  "llm_api_url": "",
  "llm_api_key": "",
  "llm_context_length": 8192,
  "llm_temperature": 0.1
}
```

**Response:**
```json
{
  "success": true,
  "project": { ... }
}
```

### Get Project

```http
GET /api/projects/{project_id}
```

**Response:**
```json
{
  "project": { ... }
}
```

### Update Project

```http
PUT /api/projects/{project_id}
```

**Request:** (partial update supported)
```json
{
  "name": "Updated Name",
  "auto_start": true
}
```

**Response:**
```json
{
  "success": true,
  "project": { ... }
}
```

### Delete Project

```http
DELETE /api/projects/{project_id}
```

**Response:**
```json
{
  "success": true
}
```

### Test Project Token

```http
GET /api/projects/{project_id}/test-token
```

**Response:**
```json
{
  "success": true,
  "token_prefix": "ghp_xxxx...",
  "repo": "user/repo",
  "checks": {
    "auth": { "success": true, "user": "username" },
    "repo_read": { "success": true, "private": false },
    "scopes": { "success": true, "scopes": "repo, workflow" }
  }
}
```

### Sync Project Issues

```http
POST /api/projects/{project_id}/sync
```

**Response:**
```json
{
  "success": true,
  "synced": 10,
  "created": 3,
  "existing": 7,
  "issue_sessions": [ ... ]
}
```

---

## Git Repository API

### Get Git Status

```http
GET /api/projects/{project_id}/git/status
```

**Response:**
```json
{
  "status": "ready",
  "message": "Repository is set up correctly",
  "is_git_repo": true,
  "remote_url": "https://github.com/user/repo.git",
  "current_branch": "main",
  "is_clean": true,
  "ahead_behind": { "ahead": 0, "behind": 0 }
}
```

**Status values:**
- `not_configured` - Working directory not set
- `missing` - Directory doesn't exist
- `not_initialized` - Not a git repository
- `wrong_remote` - Remote URL mismatch
- `ready` - Repository ready

### Setup Git Repository

```http
POST /api/projects/{project_id}/git/setup
```

Clone or update repository.

**Response:**
```json
{
  "success": true,
  "action": "cloned",
  "message": "Repository cloned successfully"
}
```

### Pull Latest

```http
POST /api/projects/{project_id}/git/pull
```

**Response:**
```json
{
  "success": true,
  "message": "Pulled latest changes",
  "output": "Already up to date."
}
```

---

## Issues API

### Get Project Issues

```http
GET /api/projects/{project_id}/issues?status={status}
```

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| status | string | Filter by status (pending, in_progress, etc.) |

**Response:**
```json
{
  "issue_sessions": [
    {
      "id": 1,
      "project_id": 1,
      "github_issue_number": 42,
      "github_issue_title": "Fix login bug",
      "github_issue_body": "...",
      "github_issue_url": "https://github.com/...",
      "github_issue_labels": ["bug"],
      "status": "pending",
      "branch_name": "fix/issue-42",
      "session_id": null,
      "pr_number": null,
      "pr_url": null,
      "attempts": 0,
      "max_attempts": 3,
      "last_error": null
    }
  ]
}
```

### Get Issue Session

```http
GET /api/issue-sessions/{session_id}
```

### Start Issue Session

```http
POST /api/issue-sessions/{session_id}/start
```

**Response:**
```json
{
  "success": true,
  "issue_session": { ... }
}
```

### Retry Issue Session

```http
POST /api/issue-sessions/{session_id}/retry
```

### Skip Issue Session

```http
POST /api/issue-sessions/{session_id}/skip
```

---

## Automation API

### Start Automation

```http
POST /api/projects/{project_id}/automation/start
```

**Response:**
```json
{
  "success": true,
  "status": "running"
}
```

### Stop Automation

```http
POST /api/projects/{project_id}/automation/stop
```

**Response:**
```json
{
  "success": true,
  "status": "paused"
}
```

### Get Automation Status

```http
GET /api/projects/{project_id}/automation/status
```

**Response:**
```json
{
  "project_id": 1,
  "status": "running",
  "automation": {
    "issues_processed": 5,
    "issues_completed": 3,
    "issues_failed": 1
  }
}
```

### Get Automation Logs

```http
GET /api/projects/{project_id}/automation/logs?limit={limit}
```

**Response:**
```json
{
  "project_id": 1,
  "logs": [
    {
      "timestamp": "2024-01-15T10:30:00",
      "level": "info",
      "message": "Starting work on issue #42"
    }
  ]
}
```

---

## LLM API

### Test LLM Connection

```http
POST /api/llm/test
```

**Request:**
```json
{
  "provider": "ollama",
  "api_url": "http://localhost:11434",
  "api_key": "",
  "model_name": "llama3.2:latest"
}
```

**Provider values:** `ollama`, `lm_studio`, `openrouter`

**Response:**
```json
{
  "success": true,
  "message": "Connected to Ollama. 5 models available.",
  "models": ["llama3.2:latest", "codellama:13b", ...]
}
```

### List Ollama Models

```http
GET /api/llm/ollama/models?api_url={url}
```

**Response:**
```json
{
  "success": true,
  "api_url": "http://localhost:11434",
  "models": [
    {
      "name": "llama3.2:latest",
      "size": 2000000000,
      "modified_at": "2024-01-15T10:00:00"
    }
  ],
  "count": 5
}
```

### List LM Studio Models

```http
GET /api/llm/lmstudio/models?api_url={url}
```

### List OpenRouter Models

```http
GET /api/llm/openrouter/models?api_key={key}
```

**Response:**
```json
{
  "success": true,
  "models": [
    {
      "id": "anthropic/claude-3.5-sonnet",
      "name": "Claude 3.5 Sonnet",
      "context_length": 200000,
      "pricing": { "prompt": "0.003", "completion": "0.015" }
    }
  ],
  "count": 50
}
```

---

## WebSocket API

### Connect

```javascript
const ws = new WebSocket('ws://localhost:8420/ws');
```

### Initial State

After connecting, you receive the current state:

```json
{
  "type": "init",
  "sessions": [ ... ]
}
```

### Message Types

#### Output Event

Real-time session output:
```json
{
  "type": "output",
  "session_id": 1,
  "data": "Output text..."
}
```

#### Status Event

Session status change:
```json
{
  "type": "status",
  "session_id": 1,
  "status": "completed",
  "session": { ... }
}
```

#### Session Created Event

New session created:
```json
{
  "type": "session_created",
  "session": { ... }
}
```

### Client Messages

#### Send Input

```json
{
  "type": "input",
  "session_id": 1,
  "data": "User input text"
}
```

#### Create Session

```json
{
  "type": "create",
  "name": "New Session",
  "working_dir": "/path/to/dir",
  "parent_id": null,
  "initial_prompt": "..."
}
```

#### Stop Session

```json
{
  "type": "stop",
  "session_id": 1
}
```

#### Complete Session

```json
{
  "type": "complete",
  "session_id": 1
}
```

#### Update Parent

```json
{
  "type": "update_parent",
  "session_id": 1,
  "parent_id": 5
}
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad Request - Invalid parameters |
| 401 | Unauthorized - Invalid token |
| 404 | Not Found - Resource doesn't exist |
| 500 | Server Error - Internal error |

### Error Response Format

```json
{
  "detail": "Error message describing the issue"
}
```

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| "Session not found" | Invalid session ID | Check session exists |
| "Project not found" | Invalid project ID | Check project exists |
| "Invalid GitHub token" | Token expired or invalid | Update token |
| "Cannot access repository" | Token lacks permissions | Add repo scope |

---

## Rate Limits

UltraClaude itself has no rate limits, but:

- **GitHub API**: 5000 requests/hour (authenticated)
- **OpenRouter**: Based on your plan
- **Ollama/LM Studio**: No limits (local)

Monitor GitHub rate limits:
```bash
curl -H "Authorization: token YOUR_TOKEN" \
  https://api.github.com/rate_limit
```
