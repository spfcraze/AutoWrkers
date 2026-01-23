from typing import Any
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .models import (
    WorkflowStatus,
    PhaseStatus,
    TriggerMode,
    IterationBehavior,
    WorkflowPhase,
    PhaseExecution,
)
from .engine import workflow_orchestrator, WorkflowOrchestrator
from .template_manager import template_manager
from .artifact_manager import artifact_manager
from .budget_tracker import budget_manager
from .providers.registry import model_registry


router = APIRouter(prefix="/api/workflow", tags=["workflow"])


class WorkflowCreateRequest(BaseModel):
    task_description: str
    project_path: str = ""
    template_id: str | None = None
    project_id: int | None = None
    issue_session_id: int | None = None
    budget_limit: float | None = None
    interactive_mode: bool = False


class TemplateCreateRequest(BaseModel):
    name: str
    description: str = ""
    phases: list[dict[str, Any]] = []
    max_iterations: int = 3
    iteration_behavior: str = "auto_iterate"
    failure_behavior: str = "pause_notify"
    budget_limit: float | None = None
    is_global: bool = True
    project_id: int | None = None


class ProviderKeysRequest(BaseModel):
    gemini_api_key: str = ""
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    ollama_url: str = "http://localhost:11434"
    lm_studio_url: str = "http://localhost:1234/v1"


@router.get("/templates")
async def list_templates(project_id: int | None = None):
    templates = template_manager.get_all(project_id)
    return {
        "templates": [t.to_dict() for t in templates],
        "count": len(templates),
    }


@router.get("/templates/{template_id}")
async def get_template(template_id: str):
    template = template_manager.get(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"template": template.to_dict()}


@router.post("/templates")
async def create_template(request: TemplateCreateRequest):
    from .models import (
        WorkflowTemplate,
        WorkflowPhase,
        ProviderConfig,
        ProviderType,
        PhaseRole,
        ArtifactType,
        IterationBehavior,
        FailureBehavior,
        generate_id,
    )
    
    phases = []
    for i, p in enumerate(request.phases):
        provider_data = p.get("provider_config", p.get("provider", {}))
        provider_config = ProviderConfig(
            provider_type=ProviderType(provider_data.get("provider_type", provider_data.get("type", "claude_code"))),
            model_name=provider_data.get("model_name", provider_data.get("model", "")),
            temperature=provider_data.get("temperature", 0.1),
            context_length=provider_data.get("context_length", 8192),
        )
        
        phase = WorkflowPhase(
            id=generate_id(),
            name=p.get("name", f"Phase {i+1}"),
            role=PhaseRole(p.get("role", "analyzer")),
            provider_config=provider_config,
            prompt_template=p.get("prompt_template", ""),
            output_artifact_type=ArtifactType(p.get("output_artifact_type", p.get("output_type", "custom"))),
            success_pattern=p.get("success_pattern", "/complete"),
            can_skip=p.get("can_skip", True),
            can_iterate=p.get("can_iterate", False),
            max_retries=p.get("max_retries", 2),
            timeout_seconds=p.get("timeout_seconds", 3600),
            parallel_with=p.get("parallel_with"),
            order=p.get("order", i),
        )
        phases.append(phase)
    
    template = WorkflowTemplate(
        id=generate_id(),
        name=request.name,
        description=request.description,
        phases=phases,
        max_iterations=request.max_iterations,
        iteration_behavior=IterationBehavior(request.iteration_behavior),
        failure_behavior=FailureBehavior(request.failure_behavior),
        budget_limit=request.budget_limit,
        is_global=request.is_global,
        project_id=request.project_id,
    )
    
    template_id = template_manager.create(template)
    return {"success": True, "template_id": template_id, "template": template.to_dict()}


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str):
    if not template_manager.delete(template_id):
        raise HTTPException(status_code=404, detail="Template not found")
    return {"success": True}


@router.post("/templates/{template_id}/default")
async def set_default_template(template_id: str, project_id: int | None = None):
    if not template_manager.set_default(template_id, project_id):
        raise HTTPException(status_code=404, detail="Template not found")
    return {"success": True}


@router.post("/templates/{template_id}/export")
async def export_template(template_id: str):
    from pathlib import Path
    import tempfile
    
    template = template_manager.get(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        file_path = Path(f.name)
    
    template_manager.export_yaml(template_id, file_path)
    content = file_path.read_text()
    file_path.unlink()
    
    return {"success": True, "yaml": content, "filename": f"{template.name}.yaml"}


@router.get("/executions")
async def list_executions(
    project_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
):
    ws = None
    if status:
        try:
            ws = WorkflowStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    executions = workflow_orchestrator.get_executions(
        project_id=project_id,
        status=ws,
        limit=limit,
    )
    
    return {
        "executions": [e.to_dict() for e in executions],
        "count": len(executions),
    }


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: str):
    execution = workflow_orchestrator.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    artifacts = workflow_orchestrator.get_artifacts(execution_id)
    budget = workflow_orchestrator.get_budget_summary(execution_id)
    
    return {
        "execution": execution.to_dict(),
        "artifacts": [a.to_dict() for a in artifacts],
        "budget": budget,
    }


@router.post("/executions")
async def create_execution(request: WorkflowCreateRequest):
    try:
        execution = workflow_orchestrator.create_execution(
            template_id=request.template_id,
            trigger_mode=TriggerMode.MANUAL_TASK,
            project_id=request.project_id,
            project_path=request.project_path,
            issue_session_id=request.issue_session_id,
            task_description=request.task_description,
            budget_limit=request.budget_limit,
            interactive_mode=request.interactive_mode,
        )
        return {"success": True, "execution": execution.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/executions/{execution_id}/run")
async def run_execution(execution_id: str):
    execution = workflow_orchestrator.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    if execution.status not in (WorkflowStatus.PENDING, WorkflowStatus.PAUSED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot run execution in {execution.status.value} status"
        )
    
    import asyncio
    asyncio.create_task(workflow_orchestrator.run(execution_id))
    
    return {"success": True, "message": "Workflow started", "execution_id": execution_id}


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(execution_id: str):
    if not await workflow_orchestrator.cancel(execution_id):
        raise HTTPException(status_code=400, detail="Cannot cancel execution")
    return {"success": True}


@router.post("/executions/{execution_id}/resume")
async def resume_execution(execution_id: str):
    result = await workflow_orchestrator.resume(execution_id)
    if not result:
        raise HTTPException(status_code=400, detail="Cannot resume execution")
    return {"success": True, "execution": result.to_dict()}


@router.post("/executions/{execution_id}/skip/{phase_id}")
async def skip_phase(execution_id: str, phase_id: str):
    if not workflow_orchestrator.skip_phase(execution_id, phase_id):
        raise HTTPException(status_code=400, detail="Cannot skip phase")
    return {"success": True}


@router.get("/executions/{execution_id}/artifacts")
async def get_execution_artifacts(execution_id: str):
    artifacts = workflow_orchestrator.get_artifacts(execution_id)
    return {
        "artifacts": [a.to_dict() for a in artifacts],
        "count": len(artifacts),
    }


@router.get("/executions/{execution_id}/budget")
async def get_execution_budget(execution_id: str):
    return workflow_orchestrator.get_budget_summary(execution_id)


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str):
    artifact = artifact_manager.get(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"artifact": artifact.to_dict()}


@router.get("/artifacts/{artifact_id}/content")
async def get_artifact_content(artifact_id: str):
    content = artifact_manager.read_content(artifact_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"content": content}


@router.put("/artifacts/{artifact_id}")
async def update_artifact(artifact_id: str, content: str):
    if not artifact_manager.update_content(artifact_id, content):
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"success": True}


@router.get("/providers")
async def list_providers():
    status = model_registry.get_provider_status()
    return {"providers": status}


@router.get("/providers/detect")
async def detect_local_providers():
    result = await model_registry.detect_local_providers()
    return {
        "ollama": {
            "available": result["ollama"][0],
            "models": result["ollama"][1],
        },
        "lm_studio": {
            "available": result["lm_studio"][0],
            "models": result["lm_studio"][1],
        },
    }


@router.post("/providers/validate/{provider_type}")
async def validate_provider(provider_type: str):
    from .models import ProviderType
    
    try:
        ptype = ProviderType(provider_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid provider type: {provider_type}")
    
    is_valid, error = await model_registry.validate_provider(ptype)
    return {"valid": is_valid, "error": error if not is_valid else None}


@router.get("/providers/{provider_type}/models")
async def get_provider_models(provider_type: str, refresh: bool = False):
    from .models import ProviderType
    
    try:
        ptype = ProviderType(provider_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid provider type: {provider_type}")
    
    if refresh:
        models = await model_registry.refresh_models(ptype)
    else:
        models = model_registry.get_cached_models(ptype)
    
    return {
        "provider": provider_type,
        "models": [
            {
                "model_id": m.model_id,
                "model_name": m.model_name,
                "context_length": m.context_length,
                "supports_tools": m.supports_tools,
                "supports_vision": m.supports_vision,
                "cost_input_per_1k": m.cost_input_per_1k,
                "cost_output_per_1k": m.cost_output_per_1k,
            }
            for m in models
        ],
        "count": len(models),
    }


@router.get("/providers/keys")
async def get_provider_keys():
    keys = model_registry._load_keys()
    return {
        "gemini_configured": bool(keys.gemini_api_key),
        "openai_configured": bool(keys.openai_api_key),
        "openrouter_configured": bool(keys.openrouter_api_key),
        "ollama_url": keys.ollama_url,
        "lm_studio_url": keys.lm_studio_url,
    }


@router.post("/providers/keys")
async def save_provider_keys(request: ProviderKeysRequest):
    from .models import ProviderKeys
    
    keys = ProviderKeys(
        gemini_api_key=request.gemini_api_key,
        openai_api_key=request.openai_api_key,
        openrouter_api_key=request.openrouter_api_key,
        ollama_url=request.ollama_url,
        lm_studio_url=request.lm_studio_url,
    )
    model_registry.save_keys(keys)
    return {"success": True}


@router.get("/budget/global")
async def get_global_budget():
    return budget_manager.get_global_summary()


@router.get("/budget/project/{project_id}")
async def get_project_budget(project_id: int):
    return budget_manager.get_project_summary(project_id)


@router.post("/budget/global/limit")
async def set_global_budget_limit(limit: float | None = None):
    budget_manager.set_limit("global", "global", limit)
    return {"success": True}


@router.post("/budget/project/{project_id}/limit")
async def set_project_budget_limit(project_id: int, limit: float | None = None):
    budget_manager.set_limit("project", str(project_id), limit)
    return {"success": True}


class WorkflowWebSocketManager:
    
    def __init__(self):
        self.connections: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, execution_id: str):
        await websocket.accept()
        if execution_id not in self.connections:
            self.connections[execution_id] = set()
        self.connections[execution_id].add(websocket)

    def disconnect(self, websocket: WebSocket, execution_id: str):
        if execution_id in self.connections:
            self.connections[execution_id].discard(websocket)
            if not self.connections[execution_id]:
                del self.connections[execution_id]

    async def broadcast(self, execution_id: str, message: dict[str, Any]):
        if execution_id not in self.connections:
            return
        
        disconnected = set()
        for ws in self.connections[execution_id]:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.add(ws)
        
        for ws in disconnected:
            self.connections[execution_id].discard(ws)


ws_manager = WorkflowWebSocketManager()


@router.websocket("/ws/{execution_id}")
async def workflow_websocket(websocket: WebSocket, execution_id: str):
    await ws_manager.connect(websocket, execution_id)
    
    execution = workflow_orchestrator.get_execution(execution_id)
    if execution:
        await websocket.send_json({
            "type": "init",
            "execution": execution.to_dict(),
        })
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "run":
                import asyncio
                asyncio.create_task(workflow_orchestrator.run(execution_id))
            
            elif data.get("type") == "cancel":
                await workflow_orchestrator.cancel(execution_id)
            
            elif data.get("type") == "approve":
                pass
            
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, execution_id)


async def broadcast_workflow_event(execution_id: str, event_type: str, data: dict[str, Any]):
    await ws_manager.broadcast(execution_id, {
        "type": event_type,
        **data,
    })
