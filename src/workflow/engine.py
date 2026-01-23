import asyncio
from datetime import datetime
from typing import Callable, Awaitable, Any

from .models import (
    WorkflowTemplate,
    WorkflowExecution,
    WorkflowPhase,
    PhaseExecution,
    WorkflowStatus,
    PhaseStatus,
    TriggerMode,
    IterationBehavior,
    FailureBehavior,
    Artifact,
    generate_id,
)
from .template_manager import template_manager
from .phase_runner import PhaseRunner
from .artifact_manager import artifact_manager
from .budget_tracker import budget_manager
from ..database import db


class WorkflowOrchestrator:
    
    def __init__(
        self,
        on_phase_start: Callable[[str, WorkflowPhase], Awaitable[None]] | None = None,
        on_phase_complete: Callable[[str, PhaseExecution], Awaitable[None]] | None = None,
        on_phase_output: Callable[[str, str, str], Awaitable[None]] | None = None,
        on_workflow_status: Callable[[str, WorkflowStatus], Awaitable[None]] | None = None,
        on_approval_needed: Callable[[str, str], Awaitable[bool]] | None = None,
    ):
        self._on_phase_start = on_phase_start
        self._on_phase_complete = on_phase_complete
        self._on_phase_output = on_phase_output
        self._on_workflow_status = on_workflow_status
        self._on_approval_needed = on_approval_needed
        self._active_executions: dict[str, WorkflowExecution] = {}
        self._phase_runners: dict[str, PhaseRunner] = {}

    async def _emit_workflow_status(self, execution_id: str, status: WorkflowStatus):
        if self._on_workflow_status:
            await self._on_workflow_status(execution_id, status)

    async def _emit_phase_start(self, execution_id: str, phase: WorkflowPhase):
        if self._on_phase_start:
            await self._on_phase_start(execution_id, phase)

    async def _emit_phase_complete(self, execution_id: str, phase_exec: PhaseExecution):
        if self._on_phase_complete:
            await self._on_phase_complete(execution_id, phase_exec)

    async def _request_approval(self, execution_id: str, message: str) -> bool:
        if self._on_approval_needed:
            return await self._on_approval_needed(execution_id, message)
        return True

    def create_execution(
        self,
        template_id: str | None = None,
        trigger_mode: TriggerMode = TriggerMode.MANUAL_TASK,
        project_id: int | None = None,
        project_path: str = "",
        issue_session_id: int | None = None,
        task_description: str = "",
        budget_limit: float | None = None,
        interactive_mode: bool = False,
    ) -> WorkflowExecution:
        template = None
        if template_id:
            template = template_manager.get(template_id)
        if not template:
            template = template_manager.get_default(project_id)
        if not template:
            raise ValueError("No workflow template found")
        
        execution = WorkflowExecution(
            id=generate_id(),
            template_id=template.id,
            template_name=template.name,
            trigger_mode=trigger_mode,
            project_id=project_id,
            project_path=project_path,
            issue_session_id=issue_session_id,
            task_description=task_description,
            budget_limit=budget_limit or template.budget_limit,
            iteration_behavior=template.iteration_behavior,
            interactive_mode=interactive_mode,
        )
        
        db.create_workflow_execution(execution.to_dict())
        
        if execution.budget_limit:
            budget_manager.set_limit("execution", execution.id, execution.budget_limit)
        
        self._active_executions[execution.id] = execution
        return execution

    async def run(self, execution_id: str) -> WorkflowExecution:
        execution = self._get_execution(execution_id)
        template = template_manager.get(execution.template_id)
        
        if not template:
            execution.status = WorkflowStatus.FAILED
            db.update_workflow_execution(execution_id, {"status": execution.status.value})
            return execution
        
        execution.status = WorkflowStatus.RUNNING
        execution.started_at = datetime.now().isoformat()
        db.update_workflow_execution(execution_id, {
            "status": execution.status.value,
            "started_at": execution.started_at,
        })
        await self._emit_workflow_status(execution_id, execution.status)
        
        runner = PhaseRunner(
            workflow_execution_id=execution_id,
            project_id=execution.project_id,
            project_path=execution.project_path,
            on_output=lambda pid, content: self._handle_phase_output(execution_id, pid, content),
            on_status=lambda pid, status: self._handle_phase_status(execution_id, pid, status),
        )
        self._phase_runners[execution_id] = runner
        
        try:
            await self._run_phases(execution, template, runner)
        finally:
            await runner.cleanup()
            if execution_id in self._phase_runners:
                del self._phase_runners[execution_id]
        
        return execution

    async def _run_phases(
        self,
        execution: WorkflowExecution,
        template: WorkflowTemplate,
        runner: PhaseRunner,
    ):
        phases = sorted(template.phases, key=lambda p: p.order)
        artifacts: dict[str, Artifact] = {}
        
        i = 0
        while i < len(phases):
            phase = phases[i]
            
            if execution.status in (WorkflowStatus.CANCELLED, WorkflowStatus.BUDGET_EXCEEDED):
                break
            
            parallel_phases = [phase]
            if phase.parallel_with:
                for p in phases[i+1:]:
                    if p.name == phase.parallel_with or p.parallel_with == phase.name:
                        parallel_phases.append(p)
            
            execution.current_phase_id = phase.id
            db.update_workflow_execution(execution.id, {"current_phase_id": phase.id})
            
            if len(parallel_phases) > 1:
                phase_results = await self._run_parallel_phases(
                    execution, parallel_phases, runner, artifacts
                )
            else:
                phase_results = [await self._run_single_phase(
                    execution, phase, runner, artifacts
                )]
            
            all_success = all(pe.status == PhaseStatus.COMPLETED for pe in phase_results)
            any_failed = any(pe.status == PhaseStatus.FAILED for pe in phase_results)
            
            for pe in phase_results:
                execution.phase_executions.append(pe)
                execution.total_tokens_input += pe.tokens_input
                execution.total_tokens_output += pe.tokens_output
                execution.total_cost_usd += pe.cost_usd
                
                if pe.output_artifact_id:
                    artifact = artifact_manager.get(pe.output_artifact_id)
                    if artifact:
                        artifacts[pe.phase_name] = artifact
                        execution.artifact_ids.append(pe.output_artifact_id)
                
                db.create_phase_execution(pe.to_dict())
                await self._emit_phase_complete(execution.id, pe)
            
            db.update_workflow_execution(execution.id, {
                "total_tokens_input": execution.total_tokens_input,
                "total_tokens_output": execution.total_tokens_output,
                "total_cost_usd": execution.total_cost_usd,
                "artifact_ids": execution.artifact_ids,
            })
            
            if any_failed:
                should_iterate = (
                    phase.can_iterate and
                    execution.iteration < template.max_iterations
                )
                
                if should_iterate:
                    if execution.iteration_behavior == IterationBehavior.PAUSE_FOR_APPROVAL:
                        execution.status = WorkflowStatus.AWAITING_APPROVAL
                        db.update_workflow_execution(execution.id, {"status": execution.status.value})
                        await self._emit_workflow_status(execution.id, execution.status)
                        
                        approved = await self._request_approval(
                            execution.id,
                            f"Phase '{phase.name}' failed. Retry iteration {execution.iteration + 1}?"
                        )
                        
                        if not approved:
                            if template.failure_behavior == FailureBehavior.SKIP_PHASE:
                                i += len(parallel_phases)
                                continue
                            else:
                                execution.status = WorkflowStatus.FAILED
                                break
                        
                        execution.status = WorkflowStatus.RUNNING
                        db.update_workflow_execution(execution.id, {"status": execution.status.value})
                    
                    execution.iteration += 1
                    db.update_workflow_execution(execution.id, {"iteration": execution.iteration})
                    continue
                else:
                    if template.failure_behavior == FailureBehavior.SKIP_PHASE:
                        i += len(parallel_phases)
                        continue
                    elif template.failure_behavior == FailureBehavior.FALLBACK_PROVIDER:
                        pass
                    else:
                        execution.status = WorkflowStatus.PAUSED
                        db.update_workflow_execution(execution.id, {"status": execution.status.value})
                        await self._emit_workflow_status(execution.id, execution.status)
                        
                        approved = await self._request_approval(
                            execution.id,
                            f"Phase '{phase.name}' failed after {execution.iteration} iterations. Continue anyway?"
                        )
                        
                        if not approved:
                            execution.status = WorkflowStatus.FAILED
                            break
                        
                        execution.status = WorkflowStatus.RUNNING
                        db.update_workflow_execution(execution.id, {"status": execution.status.value})
            
            is_ok, _ = budget_manager.check_budget("execution", execution.id)
            if not is_ok:
                execution.status = WorkflowStatus.BUDGET_EXCEEDED
                db.update_workflow_execution(execution.id, {"status": execution.status.value})
                await self._emit_workflow_status(execution.id, execution.status)
                break
            
            i += len(parallel_phases)
        
        if execution.status == WorkflowStatus.RUNNING:
            execution.status = WorkflowStatus.COMPLETED
        
        execution.completed_at = datetime.now().isoformat()
        db.update_workflow_execution(execution.id, {
            "status": execution.status.value,
            "completed_at": execution.completed_at,
        })
        await self._emit_workflow_status(execution.id, execution.status)

    async def _run_single_phase(
        self,
        execution: WorkflowExecution,
        phase: WorkflowPhase,
        runner: PhaseRunner,
        artifacts: dict[str, Artifact],
    ) -> PhaseExecution:
        await self._emit_phase_start(execution.id, phase)
        
        return await runner.run_phase(
            phase=phase,
            task_description=execution.task_description,
            input_artifacts=artifacts,
            iteration=execution.iteration,
        )

    async def _run_parallel_phases(
        self,
        execution: WorkflowExecution,
        phases: list[WorkflowPhase],
        runner: PhaseRunner,
        artifacts: dict[str, Artifact],
    ) -> list[PhaseExecution]:
        for phase in phases:
            await self._emit_phase_start(execution.id, phase)
        
        tasks = [
            runner.run_phase(
                phase=phase,
                task_description=execution.task_description,
                input_artifacts=artifacts,
                iteration=execution.iteration,
            )
            for phase in phases
        ]
        
        return await asyncio.gather(*tasks)

    async def _handle_phase_output(self, execution_id: str, phase_id: str, content: str):
        if self._on_phase_output:
            await self._on_phase_output(execution_id, phase_id, content)

    async def _handle_phase_status(self, execution_id: str, phase_id: str, status: PhaseStatus):
        pass

    def _get_execution(self, execution_id: str) -> WorkflowExecution:
        if execution_id in self._active_executions:
            return self._active_executions[execution_id]
        
        data = db.get_workflow_execution(execution_id)
        if not data:
            raise ValueError(f"Workflow execution not found: {execution_id}")
        
        execution = WorkflowExecution.from_dict(data)
        self._active_executions[execution_id] = execution
        return execution

    def get_execution(self, execution_id: str) -> WorkflowExecution | None:
        try:
            return self._get_execution(execution_id)
        except ValueError:
            return None

    def get_executions(
        self,
        project_id: int | None = None,
        status: WorkflowStatus | None = None,
        limit: int = 100,
    ) -> list[WorkflowExecution]:
        data = db.get_workflow_executions(
            project_id=project_id,
            status=status.value if status else None,
            limit=limit,
        )
        return [WorkflowExecution.from_dict(d) for d in data]

    async def cancel(self, execution_id: str) -> bool:
        execution = self._get_execution(execution_id)
        
        if execution.status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
            return False
        
        execution.status = WorkflowStatus.CANCELLED
        execution.completed_at = datetime.now().isoformat()
        
        db.update_workflow_execution(execution_id, {
            "status": execution.status.value,
            "completed_at": execution.completed_at,
        })
        
        await self._emit_workflow_status(execution_id, execution.status)
        
        if execution_id in self._phase_runners:
            await self._phase_runners[execution_id].cleanup()
            del self._phase_runners[execution_id]
        
        return True

    async def resume(self, execution_id: str) -> WorkflowExecution | None:
        execution = self._get_execution(execution_id)
        
        if execution.status not in (WorkflowStatus.PAUSED, WorkflowStatus.AWAITING_APPROVAL):
            return None
        
        return await self.run(execution_id)

    def skip_phase(self, execution_id: str, phase_id: str) -> bool:
        execution = self._get_execution(execution_id)
        
        if execution.status != WorkflowStatus.PAUSED:
            return False
        
        for pe in execution.phase_executions:
            if pe.phase_id == phase_id and pe.status == PhaseStatus.FAILED:
                pe.status = PhaseStatus.SKIPPED
                db.update_phase_execution(pe.id, {"status": pe.status.value})
                return True
        
        return False

    def get_artifacts(self, execution_id: str) -> list[Artifact]:
        return artifact_manager.get_by_workflow(execution_id)

    def get_budget_summary(self, execution_id: str) -> dict[str, Any]:
        return budget_manager.get_execution_summary(execution_id)

    async def recover_interrupted_executions(self) -> int:
        running = self.get_executions(status=WorkflowStatus.RUNNING)
        paused = self.get_executions(status=WorkflowStatus.PAUSED)
        awaiting = self.get_executions(status=WorkflowStatus.AWAITING_APPROVAL)
        
        recovered = 0
        for execution in running:
            print(f"[Workflow Recovery] Execution {execution.id} was running, marking as paused for manual resume")
            execution.status = WorkflowStatus.PAUSED
            db.update_workflow_execution(execution.id, {
                "status": execution.status.value,
            })
            recovered += 1
        
        if recovered:
            print(f"[Workflow Recovery] Marked {recovered} interrupted workflows as paused")
        
        pending_count = len(paused) + len(awaiting)
        if pending_count:
            print(f"[Workflow Recovery] {pending_count} workflows awaiting user action (paused/awaiting approval)")
        
        return recovered


workflow_orchestrator = WorkflowOrchestrator()
