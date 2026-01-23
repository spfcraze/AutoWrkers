from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import yaml

from ..database import db
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


class TemplateManager:
    def __init__(self):
        self._ensure_default_template()

    def _ensure_default_template(self):
        existing = db.get_default_workflow_template()
        if not existing:
            self.create_default_template()

    def create(self, template: WorkflowTemplate) -> str:
        return db.create_workflow_template(template.to_dict())

    def get(self, template_id: str) -> Optional[WorkflowTemplate]:
        data = db.get_workflow_template(template_id)
        return WorkflowTemplate.from_dict(data) if data else None

    def get_all(
        self, 
        project_id: Optional[int] = None, 
        include_global: bool = True
    ) -> List[WorkflowTemplate]:
        templates = db.get_workflow_templates(project_id, include_global)
        return [WorkflowTemplate.from_dict(t) for t in templates]

    def get_default(self, project_id: Optional[int] = None) -> Optional[WorkflowTemplate]:
        data = db.get_default_workflow_template(project_id)
        return WorkflowTemplate.from_dict(data) if data else None

    def update(self, template_id: str, updates: Dict[str, Any]) -> bool:
        if 'phases' in updates and isinstance(updates['phases'], list):
            updates['phases'] = [
                p.to_dict() if isinstance(p, WorkflowPhase) else p 
                for p in updates['phases']
            ]
        return db.update_workflow_template(template_id, updates)

    def delete(self, template_id: str) -> bool:
        return db.delete_workflow_template(template_id)

    def set_default(self, template_id: str, project_id: Optional[int] = None) -> bool:
        template = self.get(template_id)
        if not template:
            return False
        
        if project_id:
            for t in self.get_all(project_id, include_global=False):
                if t.is_default and t.id != template_id:
                    self.update(t.id, {'is_default': False})
        else:
            for t in self.get_all():
                if t.is_global and t.is_default and t.id != template_id:
                    self.update(t.id, {'is_default': False})
        
        return self.update(template_id, {'is_default': True})

    def duplicate(
        self, 
        template_id: str, 
        new_name: Optional[str] = None,
        project_id: Optional[int] = None
    ) -> Optional[str]:
        template = self.get(template_id)
        if not template:
            return None
        
        new_id = generate_id()
        new_template = WorkflowTemplate(
            id=new_id,
            name=new_name or f"{template.name} (Copy)",
            description=template.description,
            phases=[
                WorkflowPhase(
                    id=generate_id(),
                    name=p.name,
                    role=p.role,
                    provider_config=p.provider_config,
                    prompt_template=p.prompt_template,
                    output_artifact_type=p.output_artifact_type,
                    success_pattern=p.success_pattern,
                    can_skip=p.can_skip,
                    can_iterate=p.can_iterate,
                    max_retries=p.max_retries,
                    timeout_seconds=p.timeout_seconds,
                    parallel_with=p.parallel_with,
                    order=p.order,
                )
                for p in template.phases
            ],
            max_iterations=template.max_iterations,
            iteration_behavior=template.iteration_behavior,
            failure_behavior=template.failure_behavior,
            budget_limit=template.budget_limit,
            budget_scope=template.budget_scope,
            is_default=False,
            is_global=project_id is None,
            project_id=project_id,
        )
        return self.create(new_template)

    def export_yaml(self, template_id: str, file_path: Path) -> bool:
        template = self.get(template_id)
        if not template:
            return False
        
        export_data = {
            'name': template.name,
            'description': template.description,
            'max_iterations': template.max_iterations,
            'iteration_behavior': template.iteration_behavior.value,
            'failure_behavior': template.failure_behavior.value,
            'budget_limit': template.budget_limit,
            'budget_scope': template.budget_scope,
            'phases': [
                {
                    'name': p.name,
                    'role': p.role.value,
                    'provider': {
                        'type': p.provider_config.provider_type.value,
                        'model': p.provider_config.model_name,
                        'temperature': p.provider_config.temperature,
                        'context_length': p.provider_config.context_length,
                    },
                    'prompt_template': p.prompt_template,
                    'output_type': p.output_artifact_type.value,
                    'success_pattern': p.success_pattern,
                    'can_skip': p.can_skip,
                    'can_iterate': p.can_iterate,
                    'max_retries': p.max_retries,
                    'timeout_seconds': p.timeout_seconds,
                    'parallel_with': p.parallel_with,
                }
                for p in template.phases
            ],
        }
        
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w') as f:
            yaml.dump(export_data, f, default_flow_style=False, sort_keys=False)
        return True

    def import_yaml(
        self, 
        file_path: Path, 
        project_id: Optional[int] = None
    ) -> Optional[str]:
        if not file_path.exists():
            return None
        
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)
        
        if not data or 'name' not in data or 'phases' not in data:
            return None
        
        phases = []
        for i, p in enumerate(data.get('phases', [])):
            provider_data = p.get('provider', {})
            provider_config = ProviderConfig(
                provider_type=ProviderType(provider_data.get('type', 'claude_code')),
                model_name=provider_data.get('model', ''),
                temperature=provider_data.get('temperature', 0.1),
                context_length=provider_data.get('context_length', 8192),
            )
            
            phase = WorkflowPhase(
                id=generate_id(),
                name=p.get('name', f'Phase {i+1}'),
                role=PhaseRole(p.get('role', 'analyzer')),
                provider_config=provider_config,
                prompt_template=p.get('prompt_template', ''),
                output_artifact_type=ArtifactType(p.get('output_type', 'custom')),
                success_pattern=p.get('success_pattern', '/complete'),
                can_skip=p.get('can_skip', True),
                can_iterate=p.get('can_iterate', False),
                max_retries=p.get('max_retries', 2),
                timeout_seconds=p.get('timeout_seconds', 3600),
                parallel_with=p.get('parallel_with'),
                order=i,
            )
            phases.append(phase)
        
        template = WorkflowTemplate(
            id=generate_id(),
            name=data['name'],
            description=data.get('description', ''),
            phases=phases,
            max_iterations=data.get('max_iterations', 3),
            iteration_behavior=IterationBehavior(data.get('iteration_behavior', 'auto_iterate')),
            failure_behavior=FailureBehavior(data.get('failure_behavior', 'pause_notify')),
            budget_limit=data.get('budget_limit'),
            budget_scope=data.get('budget_scope', 'execution'),
            is_default=False,
            is_global=project_id is None,
            project_id=project_id,
        )
        
        return self.create(template)

    def create_default_template(self) -> str:
        phases = [
            WorkflowPhase(
                id=generate_id(),
                name="Analysis",
                role=PhaseRole.ANALYZER,
                provider_config=ProviderConfig(
                    provider_type=ProviderType.GEMINI_SDK,
                    model_name="gemini-2.0-flash",
                    temperature=0.1,
                ),
                prompt_template="""Analyze this codebase and task:

## Task
{task_description}

## Project Path
{project_path}

## Instructions
1. Understand the existing code structure
2. Identify relevant files and modules
3. List dependencies and patterns used
4. Create a detailed task breakdown

Output a structured analysis document with:
- Overview of relevant code
- List of files to modify
- Technical approach
- Potential risks

End with /complete when done.""",
                output_artifact_type=ArtifactType.TASK_LIST,
                order=0,
            ),
            WorkflowPhase(
                id=generate_id(),
                name="Documentation",
                role=PhaseRole.PLANNER,
                provider_config=ProviderConfig(
                    provider_type=ProviderType.GEMINI_SDK,
                    model_name="gemini-2.0-flash",
                    temperature=0.1,
                ),
                prompt_template="""Based on the analysis, create implementation documentation:

## Previous Analysis
{artifact:analysis}

## Task
{task_description}

## Instructions
Create a detailed implementation plan including:
1. Step-by-step implementation guide
2. Code patterns to follow
3. Testing requirements
4. Acceptance criteria

End with /complete when done.""",
                output_artifact_type=ArtifactType.IMPLEMENTATION_PLAN,
                order=1,
            ),
            WorkflowPhase(
                id=generate_id(),
                name="Implementation",
                role=PhaseRole.IMPLEMENTER,
                provider_config=ProviderConfig(
                    provider_type=ProviderType.CLAUDE_CODE,
                ),
                prompt_template="""Implement the planned changes:

## Implementation Plan
{artifact:documentation}

## Task
{task_description}

## Project Path
{project_path}

## Instructions
1. Follow the implementation plan exactly
2. Make incremental changes
3. Test each change
4. Create atomic commits

End with /complete when implementation is done.""",
                output_artifact_type=ArtifactType.CODE_DIFF,
                can_iterate=True,
                order=2,
            ),
            WorkflowPhase(
                id=generate_id(),
                name="Functional Review",
                role=PhaseRole.REVIEWER_FUNC,
                provider_config=ProviderConfig(
                    provider_type=ProviderType.OPENAI,
                    model_name="gpt-4o",
                    temperature=0.1,
                ),
                prompt_template="""Review the implementation for functional correctness:

## Original Task
{task_description}

## Implementation
{artifact:implementation}

## Instructions
Review for:
1. Correctness - does it solve the problem?
2. Edge cases - are they handled?
3. Error handling - is it robust?
4. Logic - any bugs or issues?

Provide specific feedback. If changes needed, list them clearly.
If approved, end with /complete.""",
                output_artifact_type=ArtifactType.REVIEW_REPORT,
                parallel_with=None,
                order=3,
            ),
            WorkflowPhase(
                id=generate_id(),
                name="Style Review",
                role=PhaseRole.REVIEWER_STYLE,
                provider_config=ProviderConfig(
                    provider_type=ProviderType.GEMINI_SDK,
                    model_name="gemini-2.0-flash",
                    temperature=0.1,
                ),
                prompt_template="""Review the implementation for code style and best practices:

## Implementation
{artifact:implementation}

## Instructions
Review for:
1. Code style consistency
2. Naming conventions
3. Documentation quality
4. Best practices adherence
5. Performance considerations

Provide specific feedback. If changes needed, list them clearly.
If approved, end with /complete.""",
                output_artifact_type=ArtifactType.REVIEW_REPORT,
                parallel_with="Functional Review",
                order=3,
            ),
            WorkflowPhase(
                id=generate_id(),
                name="Verification",
                role=PhaseRole.VERIFIER,
                provider_config=ProviderConfig(
                    provider_type=ProviderType.CLAUDE_CODE,
                ),
                prompt_template="""Verify the implementation:

## Project Path
{project_path}

## Instructions
1. Run lint checks
2. Run tests
3. Run build
4. Verify all checks pass

Report results. End with /complete if all pass.""",
                output_artifact_type=ArtifactType.VERIFICATION_REPORT,
                order=4,
            ),
        ]
        
        template = WorkflowTemplate(
            id=generate_id(),
            name="Standard Pipeline",
            description="Default multi-LLM workflow: Analysis → Documentation → Implementation → Review → Verification",
            phases=phases,
            max_iterations=3,
            iteration_behavior=IterationBehavior.AUTO_ITERATE,
            failure_behavior=FailureBehavior.PAUSE_NOTIFY,
            is_default=True,
            is_global=True,
        )
        
        return self.create(template)


template_manager = TemplateManager()
