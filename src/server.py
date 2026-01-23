import asyncio
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from typing import Set, Optional, List
from pydantic import BaseModel

from .logging_config import setup_logging, get_logger
from .session_manager import manager, SessionStatus
from .models import (
    project_manager, issue_session_manager,
    Project, IssueSession, IssueSessionStatus, ProjectStatus, IssueFilter
)
from .github_client import get_github_client, GitHubError, GitHubAuthError, GitHubNotFoundError
from .workflow.api import router as workflow_router

setup_logging()
logger = get_logger("ultraclaude.server")

app = FastAPI(title="UltraClaude", version="0.1.0")

# Paths
BASE_DIR = Path(__file__).parent.parent
WEB_DIR = BASE_DIR / "web"

app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")

app.include_router(workflow_router)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)

        for conn in disconnected:
            self.active_connections.discard(conn)


ws_manager = ConnectionManager()


# Register callbacks with session manager
async def on_output(session_id: int, data: str):
    print(f"[DEBUG] Broadcasting output for session {session_id}: {len(data)} chars, {len(ws_manager.active_connections)} connections")
    await ws_manager.broadcast({
        "type": "output",
        "session_id": session_id,
        "data": data
    })


async def on_status_change(session_id: int, status: SessionStatus):
    session = manager.get_session(session_id)
    await ws_manager.broadcast({
        "type": "status",
        "session_id": session_id,
        "status": status.value,
        "session": session.to_dict() if session else None
    })


async def on_session_created(session):
    await ws_manager.broadcast({
        "type": "session_created",
        "session": session.to_dict()
    })


manager.add_output_callback(on_output)
manager.add_status_callback(on_status_change)
manager.add_session_created_callback(on_session_created)


async def on_automation_event(event_type: str, data: dict):
    await ws_manager.broadcast({
        "type": "automation_event",
        "event": event_type,
        "data": data
    })


from .automation import automation_controller
automation_controller.add_event_callback(on_automation_event)


@app.on_event("startup")
async def startup_event():
    """Recover state and start output readers for any reconnected tmux sessions"""
    await manager.start_output_readers()
    await automation_controller.recover_interrupted_sessions()
    
    from .workflow.engine import workflow_orchestrator
    await workflow_orchestrator.recover_interrupted_executions()


@app.get("/health")
async def health_check():
    import shutil
    
    tmux_available = shutil.which("tmux") is not None
    
    try:
        sessions = manager.get_all_sessions()
        session_manager_ok = True
        active_sessions = len([s for s in sessions if s.status == SessionStatus.RUNNING])
        total_sessions = len(sessions)
    except Exception:
        session_manager_ok = False
        active_sessions = 0
        total_sessions = 0
    
    try:
        projects = project_manager.get_all()
        project_manager_ok = True
        total_projects = len(projects)
    except Exception:
        project_manager_ok = False
        total_projects = 0
    
    try:
        issue_sessions = list(issue_session_manager.sessions.values())
        issue_session_manager_ok = True
        pending_issues = len([s for s in issue_sessions if s.status == IssueSessionStatus.PENDING])
        in_progress_issues = len([s for s in issue_sessions if s.status == IssueSessionStatus.IN_PROGRESS])
    except Exception:
        issue_session_manager_ok = False
        pending_issues = 0
        in_progress_issues = 0
    
    automation_ok = automation_controller is not None
    
    all_ok = all([
        tmux_available,
        session_manager_ok,
        project_manager_ok,
        issue_session_manager_ok,
        automation_ok
    ])
    
    return {
        "status": "healthy" if all_ok else "degraded",
        "components": {
            "tmux": {"status": "ok" if tmux_available else "error", "available": tmux_available},
            "session_manager": {
                "status": "ok" if session_manager_ok else "error",
                "active_sessions": active_sessions,
                "total_sessions": total_sessions
            },
            "project_manager": {
                "status": "ok" if project_manager_ok else "error",
                "total_projects": total_projects
            },
            "issue_session_manager": {
                "status": "ok" if issue_session_manager_ok else "error",
                "pending_issues": pending_issues,
                "in_progress_issues": in_progress_issues
            },
            "automation_controller": {
                "status": "ok" if automation_ok else "error"
            }
        },
        "websocket_connections": len(ws_manager.active_connections)
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "sessions": [s.to_dict() for s in manager.get_all_sessions()]
    })


@app.get("/api/sessions")
async def get_sessions():
    return {"sessions": [s.to_dict() for s in manager.get_all_sessions()]}


@app.post("/api/sessions")
async def create_session(
    name: str = None,
    working_dir: str = None,
    parent_id: int = None,
    initial_prompt: str = None
):
    """
    Create a new session.

    - parent_id: If specified, this session will be queued until the parent completes
    - initial_prompt: If specified, this prompt will be sent to Claude after startup
    """
    try:
        session = manager.create_session(
            name=name,
            working_dir=working_dir,
            parent_id=parent_id,
            initial_prompt=initial_prompt
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    success = await manager.start_session(session)
    return {
        "success": success,
        "session": session.to_dict()
    }


@app.post("/api/sessions/{session_id}/input")
async def send_input(session_id: int, data: str):
    # Auto-add carriage return if not present (to press Enter)
    if not data.endswith('\r'):
        data = data + '\r'
    success = await manager.send_input(session_id, data)
    return {"success": success}


@app.post("/api/sessions/{session_id}/stop")
async def stop_session(session_id: int):
    success = await manager.stop_session(session_id)
    return {"success": success}


@app.post("/api/sessions/{session_id}/complete")
async def complete_session(session_id: int):
    """Mark a session as completed, which will trigger any queued child sessions to start"""
    success = await manager.mark_session_completed(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": success}


@app.post("/api/sessions/{session_id}/parent")
async def update_session_parent(session_id: int, request: Request):
    """Update a session's parent (for Kanban drag & drop and context menu)"""
    try:
        body = await request.json()
        parent_id = body.get("parent_id")
    except Exception:
        parent_id = None
    success = await manager.update_session_parent(session_id, parent_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update parent")
    session = manager.get_session(session_id)
    return {"success": success, "session": session.to_dict() if session else None}


@app.get("/api/sessions/queued")
async def get_queued_sessions(parent_id: int = None):
    """Get all queued sessions, optionally filtered by parent"""
    sessions = manager.get_queued_sessions(parent_id)
    return {"sessions": [s.to_dict() for s in sessions]}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: int):
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session.to_dict()}


@app.get("/api/sessions/{session_id}/output")
async def get_session_output(session_id: int):
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"output": manager.get_session_output(session_id)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)

    # Send current state
    await websocket.send_json({
        "type": "init",
        "sessions": [s.to_dict() for s in manager.get_all_sessions()]
    })

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "input":
                session_id = data.get("session_id")
                input_data = data.get("data", "")
                await manager.send_input(session_id, input_data)

            elif data.get("type") == "create":
                name = data.get("name")
                working_dir = data.get("working_dir")
                parent_id = data.get("parent_id")
                initial_prompt = data.get("initial_prompt")
                try:
                    session = manager.create_session(
                        name=name,
                        working_dir=working_dir,
                        parent_id=parent_id,
                        initial_prompt=initial_prompt
                    )
                    await manager.start_session(session)
                except ValueError as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e)
                    })

            elif data.get("type") == "stop":
                session_id = data.get("session_id")
                await manager.stop_session(session_id)

            elif data.get("type") == "complete":
                session_id = data.get("session_id")
                await manager.mark_session_completed(session_id)

            elif data.get("type") == "update_parent":
                session_id = data.get("session_id")
                parent_id = data.get("parent_id")  # None to remove parent
                await manager.update_session_parent(session_id, parent_id)

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# ==================== Pydantic Models for Request Bodies ====================

class ProjectCreate(BaseModel):
    name: str
    github_repo: str
    github_token: str = ""
    working_dir: str = ""
    default_branch: str = "main"
    auto_sync: bool = True
    auto_start: bool = False
    verification_command: str = ""
    lint_command: str = ""
    build_command: str = ""
    test_command: str = ""
    max_concurrent: int = 1
    issue_filter: Optional[dict] = None
    # LLM Provider settings
    llm_provider: str = "claude_code"  # claude_code, ollama, lm_studio, openrouter
    llm_model: str = ""
    llm_api_url: str = ""
    llm_api_key: str = ""  # Will be encrypted before storage
    llm_context_length: int = 8192
    llm_temperature: float = 0.1


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    github_token: Optional[str] = None
    working_dir: Optional[str] = None
    default_branch: Optional[str] = None
    auto_sync: Optional[bool] = None
    auto_start: Optional[bool] = None
    verification_command: Optional[str] = None
    lint_command: Optional[str] = None
    build_command: Optional[str] = None
    test_command: Optional[str] = None
    max_concurrent: Optional[int] = None
    issue_filter: Optional[dict] = None
    # LLM Provider settings
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_context_length: Optional[int] = None
    llm_temperature: Optional[float] = None


class LLMTestRequest(BaseModel):
    """Request body for testing LLM connection"""
    provider: str  # ollama, lm_studio, openrouter
    api_url: str = ""
    api_key: str = ""
    model_name: str = ""


# ==================== Project API Endpoints ====================

@app.get("/projects", response_class=HTMLResponse)
async def projects_page(request: Request):
    return templates.TemplateResponse("projects.html", {
        "request": request,
        "projects": [p.to_dict() for p in project_manager.get_all()]
    })


@app.get("/issues", response_class=HTMLResponse)
async def issues_page(request: Request):
    return templates.TemplateResponse("issues.html", {"request": request})


@app.get("/workflows", response_class=HTMLResponse)
async def workflows_page(request: Request):
    return templates.TemplateResponse("workflows.html", {"request": request})


@app.get("/api/browse-dirs")
async def browse_directories(path: str = "~"):
    import os
    
    if path == "~":
        path = os.path.expanduser("~")
    
    path = os.path.abspath(path)
    
    if not os.path.exists(path):
        return {"error": "Path does not exist", "path": path, "dirs": [], "parent": None}
    
    if not os.path.isdir(path):
        path = os.path.dirname(path)
    
    try:
        entries = os.listdir(path)
    except PermissionError:
        return {"error": "Permission denied", "path": path, "dirs": [], "parent": os.path.dirname(path)}
    
    dirs = []
    for entry in sorted(entries):
        if entry.startswith('.'):
            continue
        full_path = os.path.join(path, entry)
        if os.path.isdir(full_path):
            is_git = os.path.isdir(os.path.join(full_path, ".git"))
            dirs.append({"name": entry, "path": full_path, "is_git": is_git})
    
    parent = os.path.dirname(path) if path != "/" else None
    
    return {
        "path": path,
        "dirs": dirs,
        "parent": parent,
    }


@app.get("/api/projects")
async def get_projects():
    """Get all projects"""
    return {"projects": [p.to_dict() for p in project_manager.get_all()]}


def normalize_github_repo(repo: str) -> str:
    """Normalize GitHub repo to owner/repo format"""
    repo = repo.strip()
    # Remove common URL prefixes
    prefixes = [
        "https://github.com/",
        "http://github.com/",
        "github.com/",
        "www.github.com/",
    ]
    for prefix in prefixes:
        if repo.lower().startswith(prefix):
            repo = repo[len(prefix):]
            break
    # Remove trailing slashes and .git
    repo = repo.rstrip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]
    return repo


@app.post("/api/projects")
async def create_project(project: ProjectCreate):
    """Create a new project"""
    # Normalize the repo format (handle full URLs)
    github_repo = normalize_github_repo(project.github_repo)

    # Validate repo format
    if "/" not in github_repo or github_repo.count("/") != 1:
        raise HTTPException(status_code=400, detail="Invalid repository format. Use 'owner/repo' format (e.g., 'spfcraze/WP-booking-pro')")

    # Validate GitHub token if provided
    if project.github_token:
        client = get_github_client(project.github_token)
        try:
            if not await client.verify_access(github_repo):
                raise HTTPException(status_code=400, detail="Cannot access repository. Check that the repo exists and your token has access.")
        except GitHubAuthError:
            raise HTTPException(status_code=401, detail="Invalid GitHub token")
        except GitHubError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Create project
    issue_filter = IssueFilter.from_dict(project.issue_filter) if project.issue_filter else IssueFilter()

    new_project = project_manager.create(
        name=project.name,
        github_repo=github_repo,
        github_token=project.github_token,
        working_dir=project.working_dir,
        default_branch=project.default_branch,
        issue_filter=issue_filter,
        auto_sync=project.auto_sync,
        auto_start=project.auto_start,
        verification_command=project.verification_command,
        lint_command=project.lint_command,
        build_command=project.build_command,
        test_command=project.test_command,
        max_concurrent=project.max_concurrent,
        llm_provider=project.llm_provider,
        llm_model=project.llm_model,
        llm_api_url=project.llm_api_url,
        llm_context_length=project.llm_context_length,
        llm_temperature=project.llm_temperature,
    )

    # Set LLM API key if provided (encrypted separately)
    if project.llm_api_key:
        new_project.set_llm_api_key(project.llm_api_key)
        project_manager.save()

    return {"success": True, "project": new_project.to_dict()}


@app.get("/api/projects/{project_id}")
async def get_project(project_id: int):
    """Get a project by ID"""
    project = project_manager.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": project.to_dict()}


@app.put("/api/projects/{project_id}")
async def update_project(project_id: int, updates: ProjectUpdate):
    """Update a project"""
    project = project_manager.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    update_data = updates.dict(exclude_unset=True)

    # Handle issue_filter separately
    if "issue_filter" in update_data and update_data["issue_filter"]:
        update_data["issue_filter"] = IssueFilter.from_dict(update_data["issue_filter"])

    # Handle LLM API key separately (needs encryption)
    llm_api_key = update_data.pop("llm_api_key", None)

    updated = project_manager.update(project_id, **update_data)

    # Set LLM API key if provided
    if llm_api_key is not None:
        if llm_api_key:  # Non-empty string - encrypt and store
            updated.set_llm_api_key(llm_api_key)
        else:  # Empty string - clear the key
            updated.llm_api_key_encrypted = ""
        project_manager.save()

    return {"success": True, "project": updated.to_dict()}


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: int):
    """Delete a project"""
    if not project_manager.delete(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"success": True}


@app.get("/api/projects/{project_id}/test-token")
async def test_project_token(project_id: int):
    """Test if the project's GitHub token has proper access"""
    project = project_manager.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.github_token_encrypted:
        return {"success": False, "error": "No token configured"}

    token = project.get_token()
    client = get_github_client(token)

    results = {
        "token_prefix": token[:8] + "..." if len(token) > 8 else "***",
        "repo": project.github_repo,
        "checks": {}
    }

    # Test 1: Can we get the authenticated user?
    try:
        user_info = await client._request("GET", "/user")
        results["checks"]["auth"] = {"success": True, "user": user_info.get("login")}
    except Exception as e:
        results["checks"]["auth"] = {"success": False, "error": str(e)}

    # Test 2: Can we access the repository?
    try:
        repo_info = await client._request("GET", f"/repos/{project.github_repo}")
        results["checks"]["repo_read"] = {
            "success": True,
            "private": repo_info.get("private"),
            "permissions": repo_info.get("permissions", {})
        }
    except Exception as e:
        results["checks"]["repo_read"] = {"success": False, "error": str(e)}

    # Test 3: Check token scopes from response headers (if available)
    try:
        # Make a simple request to check scopes
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
            ) as resp:
                scopes = resp.headers.get("X-OAuth-Scopes", "")
                results["checks"]["scopes"] = {"success": True, "scopes": scopes}
    except Exception as e:
        results["checks"]["scopes"] = {"success": False, "error": str(e)}

    # Overall success
    results["success"] = all(
        c.get("success", False) for c in results["checks"].values()
    )

    if not results["success"]:
        results["hint"] = "Token needs 'repo' scope for full access to private repositories"

    return results


# ==================== GitHub Sync Endpoints ====================

@app.post("/api/projects/{project_id}/sync")
async def sync_project_issues(project_id: int):
    """Sync issues from GitHub for a project"""
    project = project_manager.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.github_token_encrypted:
        raise HTTPException(status_code=400, detail="Project has no GitHub token configured")

    client = get_github_client(project.get_token())

    try:
        issues = await client.get_all_issues(
            project.github_repo,
            project.issue_filter if isinstance(project.issue_filter, IssueFilter) else None
        )
    except GitHubError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Create issue sessions for new issues
    created = []
    existing = []
    for issue in issues:
        existing_session = issue_session_manager.get_by_issue(project_id, issue.number)
        if existing_session:
            existing.append(existing_session.to_dict())
        else:
            session = issue_session_manager.create(project_id, issue)
            created.append(session.to_dict())

    # Update last sync time
    from datetime import datetime
    project_manager.update(project_id, last_sync=datetime.now().isoformat())

    return {
        "success": True,
        "synced": len(issues),
        "created": len(created),
        "existing": len(existing),
        "issue_sessions": created + existing
    }


# ==================== Git Repository Endpoints ====================

@app.get("/api/projects/{project_id}/git/status")
async def get_git_status(project_id: int):
    """Check the git repository status for a project"""
    project = project_manager.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    working_dir = project.working_dir
    if not working_dir:
        return {
            "status": "not_configured",
            "message": "Working directory not configured",
            "is_git_repo": False,
            "remote_url": None,
            "current_branch": None,
            "is_clean": None,
            "ahead_behind": None
        }

    import os
    import subprocess

    # Check if directory exists
    if not os.path.isdir(working_dir):
        return {
            "status": "missing",
            "message": f"Directory does not exist: {working_dir}",
            "is_git_repo": False,
            "remote_url": None,
            "current_branch": None,
            "is_clean": None,
            "ahead_behind": None
        }

    # Check if it's a git repo
    git_dir = os.path.join(working_dir, ".git")
    if not os.path.isdir(git_dir):
        return {
            "status": "not_initialized",
            "message": "Directory exists but is not a git repository",
            "is_git_repo": False,
            "remote_url": None,
            "current_branch": None,
            "is_clean": None,
            "ahead_behind": None
        }

    # Get remote URL
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=working_dir,
            capture_output=True,
            text=True
        )
        remote_url = result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        remote_url = None

    # Get current branch
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=working_dir,
            capture_output=True,
            text=True
        )
        current_branch = result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        current_branch = None

    # Check if working tree is clean
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=working_dir,
            capture_output=True,
            text=True
        )
        is_clean = len(result.stdout.strip()) == 0 if result.returncode == 0 else None
    except Exception:
        is_clean = None

    # Check ahead/behind status
    ahead_behind = None
    try:
        result = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", f"HEAD...origin/{project.default_branch}"],
            cwd=working_dir,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split()
            if len(parts) == 2:
                ahead_behind = {"ahead": int(parts[0]), "behind": int(parts[1])}
    except Exception:
        pass

    # Determine overall status
    expected_remote = f"https://github.com/{project.github_repo}.git"
    expected_remote_ssh = f"git@github.com:{project.github_repo}.git"

    if remote_url and (expected_remote in remote_url or expected_remote_ssh in remote_url or project.github_repo in remote_url):
        status = "ready"
        message = "Repository is set up correctly"
    elif remote_url:
        status = "wrong_remote"
        message = f"Remote URL doesn't match expected repository"
    else:
        status = "no_remote"
        message = "No remote configured"

    return {
        "status": status,
        "message": message,
        "is_git_repo": True,
        "remote_url": remote_url,
        "expected_remote": expected_remote,
        "current_branch": current_branch,
        "default_branch": project.default_branch,
        "is_clean": is_clean,
        "ahead_behind": ahead_behind
    }


@app.post("/api/projects/{project_id}/git/setup")
async def setup_git_repository(project_id: int):
    """Clone or update the git repository for a project"""
    project = project_manager.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.github_token_encrypted:
        raise HTTPException(status_code=400, detail="Project has no GitHub token configured")

    working_dir = project.working_dir
    if not working_dir:
        raise HTTPException(status_code=400, detail="Working directory not configured")

    import os
    import subprocess

    token = project.get_token()
    # Use x-access-token format which works with both classic and fine-grained PATs
    clone_url = f"https://x-access-token:{token}@github.com/{project.github_repo}.git"
    safe_clone_url = f"https://x-access-token:***@github.com/{project.github_repo}.git"  # For logging

    # First, verify token has access to the repository
    try:
        client = get_github_client(token)
        # Quick check to verify token works
        import asyncio
        loop = asyncio.get_event_loop()
        # Verify access synchronously within the async context
    except Exception as e:
        return {
            "success": False,
            "action": "verify",
            "message": f"Token verification failed. Please update your GitHub token in project settings with 'repo' scope. Error: {str(e)}"
        }

    # Ensure parent directory exists
    parent_dir = os.path.dirname(working_dir)
    if parent_dir and not os.path.exists(parent_dir):
        try:
            os.makedirs(parent_dir, exist_ok=True)
            print(f"[Git Setup] Created parent directory: {parent_dir}")
        except PermissionError:
            return {
                "success": False,
                "action": "mkdir",
                "message": f"Permission denied creating directory: {parent_dir}. Please check permissions or choose a different path.",
                "suggested_path": f"/home/{os.environ.get('USER', 'user')}/repos/{project.name}"
            }
        except Exception as e:
            return {
                "success": False,
                "action": "mkdir",
                "message": f"Failed to create directory {parent_dir}: {str(e)}"
            }

    # Check if directory exists
    if os.path.isdir(working_dir):
        git_dir = os.path.join(working_dir, ".git")
        if os.path.isdir(git_dir):
            # It's a git repo - fetch and pull latest using credential helper
            import tempfile

            # Create a temporary credential helper script
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                f.write(f'''#!/bin/bash
echo "username=x-access-token"
echo "password={token}"
''')
                credential_helper = f.name

            os.chmod(credential_helper, 0o700)

            try:
                # Fetch from remote with credentials
                subprocess.run(
                    ["git", "-c", f"credential.helper=!{credential_helper}", "fetch", "origin"],
                    cwd=working_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
                )

                # Checkout default branch
                subprocess.run(
                    ["git", "checkout", project.default_branch],
                    cwd=working_dir,
                    capture_output=True,
                    text=True
                )

                # Pull latest with credentials
                result = subprocess.run(
                    ["git", "-c", f"credential.helper=!{credential_helper}", "pull", "origin", project.default_branch],
                    cwd=working_dir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
                )

                if result.returncode != 0:
                    error_msg = result.stderr.replace(token, "***")
                    return {
                        "success": False,
                        "action": "pull",
                        "message": f"Failed to pull latest changes: {error_msg}"
                    }

                return {
                    "success": True,
                    "action": "updated",
                    "message": f"Repository updated successfully",
                    "output": result.stdout
                }
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "action": "pull",
                    "message": "Operation timed out"
                }
            except Exception as e:
                return {
                    "success": False,
                    "action": "pull",
                    "message": str(e)
                }
            finally:
                # Clean up credential helper
                try:
                    os.unlink(credential_helper)
                except:
                    pass
        else:
            # Directory exists but is not a git repo
            # We should not overwrite - inform user
            return {
                "success": False,
                "action": "none",
                "message": f"Directory exists but is not a git repository. Please remove it or choose a different working directory."
            }
    else:
        # Clone the repository
        try:
            # Create parent directory if needed
            parent_dir = os.path.dirname(working_dir)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir)

            import tempfile

            # Create a temporary credential helper script
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                f.write(f'''#!/bin/bash
echo "username=x-access-token"
echo "password={token}"
''')
                credential_helper = f.name

            os.chmod(credential_helper, 0o700)

            try:
                # Clone using the credential helper
                https_url = f"https://github.com/{project.github_repo}.git"
                result = subprocess.run(
                    ["git", "clone",
                     "-c", f"credential.helper=!{credential_helper}",
                     https_url, working_dir],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
                )
            finally:
                # Clean up credential helper script
                try:
                    os.unlink(credential_helper)
                except:
                    pass

            if result.returncode != 0:
                # Sanitize error message to not expose token
                error_msg = result.stderr.replace(token, "***")

                # Detect common token permission issues
                if "403" in error_msg or "Write access" in error_msg or "Permission denied" in error_msg:
                    return {
                        "success": False,
                        "action": "clone",
                        "message": "Token permission error: Your GitHub token doesn't have access to this repository.",
                        "hint": "Please update your token in project Settings with the 'repo' scope enabled.",
                        "details": error_msg
                    }
                elif "401" in error_msg or "Authentication" in error_msg:
                    return {
                        "success": False,
                        "action": "clone",
                        "message": "Authentication failed: Your GitHub token may be invalid or expired.",
                        "hint": "Please generate a new token and update it in project Settings.",
                        "details": error_msg
                    }
                elif "404" in error_msg or "not found" in error_msg.lower():
                    return {
                        "success": False,
                        "action": "clone",
                        "message": "Repository not found: Check the repository name or token permissions for private repos.",
                        "hint": "For private repositories, ensure your token has 'repo' scope.",
                        "details": error_msg
                    }

                return {
                    "success": False,
                    "action": "clone",
                    "message": f"Failed to clone repository: {error_msg}"
                }

            return {
                "success": True,
                "action": "cloned",
                "message": f"Repository cloned successfully to {working_dir}"
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "action": "clone",
                "message": "Clone operation timed out (exceeded 5 minutes)"
            }
        except Exception as e:
            return {
                "success": False,
                "action": "clone",
                "message": str(e)
            }


@app.post("/api/projects/{project_id}/git/pull")
async def pull_git_repository(project_id: int):
    """Pull latest changes from remote"""
    project = project_manager.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    working_dir = project.working_dir
    if not working_dir:
        raise HTTPException(status_code=400, detail="Working directory not configured")

    import os
    import subprocess
    import tempfile

    if not os.path.isdir(os.path.join(working_dir, ".git")):
        raise HTTPException(status_code=400, detail="Not a git repository. Use setup endpoint first.")

    token = project.get_token()
    if not token:
        raise HTTPException(status_code=400, detail="No GitHub token configured")

    # Create a temporary credential helper script
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
        f.write(f'''#!/bin/bash
echo "username=x-access-token"
echo "password={token}"
''')
        credential_helper = f.name

    os.chmod(credential_helper, 0o700)

    try:
        # Fetch with credentials
        subprocess.run(
            ["git", "-c", f"credential.helper=!{credential_helper}", "fetch", "origin"],
            cwd=working_dir,
            capture_output=True,
            timeout=60,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        )

        # Pull with credentials
        result = subprocess.run(
            ["git", "-c", f"credential.helper=!{credential_helper}", "pull", "origin", project.default_branch],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        )

        if result.returncode != 0:
            error_msg = result.stderr.replace(token, "***")
            return {"success": False, "message": error_msg}

        return {"success": True, "message": "Pulled latest changes", "output": result.stdout}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Pull operation timed out"}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        # Clean up credential helper
        try:
            os.unlink(credential_helper)
        except:
            pass


@app.get("/api/projects/{project_id}/issues")
async def get_project_issues(project_id: int, status: str = None):
    """Get all issue sessions for a project"""
    project = project_manager.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    sessions = issue_session_manager.get_by_project(project_id)

    if status:
        try:
            status_filter = IssueSessionStatus(status)
            sessions = [s for s in sessions if s.status == status_filter]
        except ValueError:
            pass

    return {"issue_sessions": [s.to_dict() for s in sessions]}


# ==================== Issue Session Endpoints ====================

@app.get("/api/issue-sessions")
async def get_all_issue_sessions():
    """Get all issue sessions"""
    sessions = list(issue_session_manager.sessions.values())
    return {"issue_sessions": [s.to_dict() for s in sessions]}


@app.get("/api/issue-sessions/{session_id}")
async def get_issue_session(session_id: int):
    """Get an issue session by ID"""
    session = issue_session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Issue session not found")
    return {"issue_session": session.to_dict()}


@app.post("/api/issue-sessions/{session_id}/start")
async def start_issue_session(session_id: int):
    """Start working on an issue (creates UltraClaude session)"""
    from .automation import automation_controller
    issue_session = issue_session_manager.get(session_id)
    if not issue_session:
        raise HTTPException(status_code=404, detail="Issue session not found")

    if issue_session.status not in (IssueSessionStatus.PENDING, IssueSessionStatus.FAILED):
        raise HTTPException(status_code=400, detail=f"Cannot start session in {issue_session.status.value} status")

    try:
        await automation_controller.start_issue_session(issue_session)
        return {"success": True, "issue_session": issue_session.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/issue-sessions/{session_id}/retry")
async def retry_issue_session(session_id: int):
    """Retry a failed issue session"""
    issue_session = issue_session_manager.get(session_id)
    if not issue_session:
        raise HTTPException(status_code=404, detail="Issue session not found")

    if issue_session.status not in [IssueSessionStatus.FAILED, IssueSessionStatus.IN_PROGRESS]:
        raise HTTPException(status_code=400, detail="Can only retry failed or stuck in_progress sessions")

    # Reset status - clear linked session manually to avoid parameter conflict
    issue_session = issue_session_manager.get(session_id)
    if issue_session:
        issue_session.session_id = None  # Clear any linked UltraClaude session

    issue_session_manager.update(
        session_id,
        status=IssueSessionStatus.PENDING,
        last_error="",
        attempts=0  # Reset attempt counter for retry
    )

    return {"success": True, "issue_session": issue_session.to_dict()}


@app.post("/api/issue-sessions/{session_id}/skip")
async def skip_issue_session(session_id: int):
    """Skip an issue session"""
    issue_session = issue_session_manager.get(session_id)
    if not issue_session:
        raise HTTPException(status_code=404, detail="Issue session not found")

    issue_session_manager.update(session_id, status=IssueSessionStatus.SKIPPED)
    return {"success": True, "issue_session": issue_session.to_dict()}


# ==================== Automation Control Endpoints ====================

@app.post("/api/projects/{project_id}/automation/start")
async def start_automation(project_id: int):
    """Start automation for a project"""
    from .automation import automation_controller

    project = project_manager.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    await automation_controller.start_project(project_id)
    project_manager.update(project_id, status=ProjectStatus.RUNNING)

    return {"success": True, "status": "running"}


@app.post("/api/projects/{project_id}/automation/stop")
async def stop_automation(project_id: int):
    """Stop automation for a project"""
    from .automation import automation_controller

    project = project_manager.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    await automation_controller.stop_project(project_id)
    project_manager.update(project_id, status=ProjectStatus.PAUSED)

    return {"success": True, "status": "paused"}


@app.get("/api/projects/{project_id}/automation/status")
async def get_automation_status(project_id: int):
    """Get automation status for a project"""
    from .automation import automation_controller

    project = project_manager.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    status = automation_controller.get_project_status(project_id)
    return {
        "project_id": project_id,
        "status": project.status.value,
        "automation": status
    }


@app.get("/api/projects/{project_id}/automation/logs")
async def get_automation_logs(project_id: int, limit: int = 50):
    """Get automation logs for a project"""
    from .automation import automation_controller

    project = project_manager.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    logs = automation_controller.get_project_logs(project_id, limit)
    return {
        "project_id": project_id,
        "logs": logs
    }


# ==================== LLM Provider Endpoints ====================

@app.post("/api/llm/test")
async def test_llm_connection(request: LLMTestRequest):
    """Test connection to an LLM provider"""
    from .llm_provider import LLMProviderConfig, LLMProviderType
    from .agentic_runner import test_llm_connection as do_test

    # Map provider string to enum
    provider_map = {
        "ollama": LLMProviderType.OLLAMA,
        "lm_studio": LLMProviderType.LM_STUDIO,
        "openrouter": LLMProviderType.OPENROUTER,
    }

    if request.provider not in provider_map:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {request.provider}. Must be one of: ollama, lm_studio, openrouter")

    provider_type = provider_map[request.provider]

    # Validate OpenRouter requires API key
    if provider_type == LLMProviderType.OPENROUTER and not request.api_key:
        raise HTTPException(status_code=400, detail="OpenRouter requires an API key")

    config = LLMProviderConfig(
        provider_type=provider_type,
        model_name=request.model_name,
        api_url=request.api_url,
        api_key=request.api_key,
    )

    result = await do_test(config)
    return result


@app.get("/api/llm/ollama/models")
async def list_ollama_models(api_url: str = "http://localhost:11434"):
    """List available models from an Ollama instance"""
    try:
        import httpx
    except ImportError:
        raise HTTPException(status_code=500, detail="httpx not installed. Run: pip install httpx")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{api_url}/api/tags")
            response.raise_for_status()
            data = response.json()

            models = []
            for model in data.get("models", []):
                models.append({
                    "name": model.get("name"),
                    "size": model.get("size"),
                    "modified_at": model.get("modified_at"),
                    "digest": model.get("digest", "")[:12],  # Short digest
                })

            return {
                "success": True,
                "api_url": api_url,
                "models": models,
                "count": len(models)
            }

    except httpx.ConnectError:
        return {
            "success": False,
            "api_url": api_url,
            "error": f"Cannot connect to Ollama at {api_url}. Is Ollama running?",
            "hint": "Start Ollama with: ollama serve"
        }
    except httpx.HTTPStatusError as e:
        return {
            "success": False,
            "api_url": api_url,
            "error": f"HTTP error: {e.response.status_code}"
        }
    except Exception as e:
        return {
            "success": False,
            "api_url": api_url,
            "error": str(e)
        }


@app.get("/api/llm/lmstudio/models")
async def list_lmstudio_models(api_url: str = "http://localhost:1234/v1"):
    """List available models from an LM Studio instance"""
    try:
        import httpx
    except ImportError:
        raise HTTPException(status_code=500, detail="httpx not installed. Run: pip install httpx")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{api_url}/models")
            response.raise_for_status()
            data = response.json()

            models = []
            for model in data.get("data", []):
                models.append({
                    "id": model.get("id"),
                    "object": model.get("object"),
                    "owned_by": model.get("owned_by", "local"),
                })

            return {
                "success": True,
                "api_url": api_url,
                "models": models,
                "count": len(models)
            }

    except httpx.ConnectError:
        return {
            "success": False,
            "api_url": api_url,
            "error": f"Cannot connect to LM Studio at {api_url}. Is LM Studio running with the server enabled?",
            "hint": "Enable 'Local Server' in LM Studio settings"
        }
    except httpx.HTTPStatusError as e:
        return {
            "success": False,
            "api_url": api_url,
            "error": f"HTTP error: {e.response.status_code}"
        }
    except Exception as e:
        return {
            "success": False,
            "api_url": api_url,
            "error": str(e)
        }


@app.get("/api/llm/openrouter/models")
async def list_openrouter_models(api_key: str = None):
    """List available models from OpenRouter"""
    try:
        import httpx
    except ImportError:
        raise HTTPException(status_code=500, detail="httpx not installed. Run: pip install httpx")

    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required for OpenRouter")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": "https://ultraclaude.local",
                }
            )
            response.raise_for_status()
            data = response.json()

            # Filter and format models
            models = []
            for model in data.get("data", []):
                model_id = model.get("id", "")
                # Include popular providers
                if any(p in model_id for p in ["anthropic", "openai", "meta-llama", "google", "mistral", "cohere"]):
                    models.append({
                        "id": model_id,
                        "name": model.get("name", model_id),
                        "context_length": model.get("context_length"),
                        "pricing": model.get("pricing", {}),
                    })

            # Sort by provider then name
            models.sort(key=lambda m: m["id"])

            return {
                "success": True,
                "models": models[:100],  # Limit to top 100
                "count": len(models)
            }

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return {
                "success": False,
                "error": "Invalid API key"
            }
        return {
            "success": False,
            "error": f"HTTP error: {e.response.status_code}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def run_server(host: str = "0.0.0.0", port: int = 8420):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
