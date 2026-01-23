import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.workflow.models import (
    WorkflowStatus,
    PhaseStatus,
    ProviderType,
    ArtifactType,
    TriggerMode,
    IterationBehavior,
    FailureBehavior,
    PhaseRole,
    generate_id,
    WorkflowTemplate,
    WorkflowPhase,
    WorkflowExecution,
    PhaseExecution,
    Artifact,
    ProviderConfig,
    BudgetTracker,
)


class TestWorkflowModels:
    def test_generate_id_unique(self):
        ids = [generate_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_generate_id_length(self):
        id_val = generate_id()
        assert len(id_val) == 8

    def test_workflow_status_values(self):
        assert WorkflowStatus.PENDING.value == "pending"
        assert WorkflowStatus.RUNNING.value == "running"
        assert WorkflowStatus.COMPLETED.value == "completed"
        assert WorkflowStatus.FAILED.value == "failed"

    def test_phase_status_values(self):
        assert PhaseStatus.PENDING.value == "pending"
        assert PhaseStatus.RUNNING.value == "running"
        assert PhaseStatus.COMPLETED.value == "completed"
        assert PhaseStatus.SKIPPED.value == "skipped"

    def test_provider_type_values(self):
        assert ProviderType.CLAUDE_CODE.value == "claude_code"
        assert ProviderType.GEMINI_SDK.value == "gemini_sdk"
        assert ProviderType.OPENAI.value == "openai"
        assert ProviderType.OLLAMA.value == "ollama"
        assert ProviderType.LM_STUDIO.value == "lm_studio"

    def test_provider_config_creation(self):
        config = ProviderConfig(
            provider_type=ProviderType.GEMINI_SDK,
            model_name="gemini-pro",
            temperature=0.2,
            context_length=8192,
        )
        assert config.provider_type == ProviderType.GEMINI_SDK
        assert config.model_name == "gemini-pro"
        assert config.temperature == 0.2

    def test_provider_config_to_dict(self):
        config = ProviderConfig(
            provider_type=ProviderType.OPENAI,
            model_name="gpt-4",
        )
        d = config.to_dict()
        assert d["provider_type"] == "openai"
        assert d["model_name"] == "gpt-4"

    def test_provider_config_from_dict(self):
        data = {
            "provider_type": "gemini_sdk",
            "model_name": "gemini-pro",
            "temperature": 0.5,
            "context_length": 16000,
        }
        config = ProviderConfig.from_dict(data)
        assert config.provider_type == ProviderType.GEMINI_SDK
        assert config.temperature == 0.5

    def test_workflow_phase_creation(self):
        config = ProviderConfig(
            provider_type=ProviderType.CLAUDE_CODE,
            model_name="claude-3",
        )
        phase = WorkflowPhase(
            id="phase1",
            name="Analysis",
            role=PhaseRole.ANALYZER,
            provider_config=config,
            prompt_template="Analyze {task}",
            output_artifact_type=ArtifactType.TASK_LIST,
        )
        assert phase.name == "Analysis"
        assert phase.role == PhaseRole.ANALYZER
        assert phase.can_skip is True

    def test_workflow_phase_to_dict(self):
        config = ProviderConfig(
            provider_type=ProviderType.GEMINI_SDK,
            model_name="gemini-pro",
        )
        phase = WorkflowPhase(
            id="p1",
            name="Review",
            role=PhaseRole.REVIEWER_FUNC,
            provider_config=config,
            prompt_template="Review this",
            output_artifact_type=ArtifactType.REVIEW_REPORT,
        )
        d = phase.to_dict()
        assert d["id"] == "p1"
        assert d["name"] == "Review"
        assert d["role"] == "reviewer_functional"

    def test_workflow_template_creation(self):
        template = WorkflowTemplate(
            id="tmpl1",
            name="Standard Pipeline",
            description="Default workflow template",
            phases=[],
            max_iterations=3,
        )
        assert template.name == "Standard Pipeline"
        assert template.max_iterations == 3
        assert template.is_global is True

    def test_workflow_template_to_dict(self):
        template = WorkflowTemplate(
            id="tmpl1",
            name="Test Template",
            description="Test",
            phases=[],
        )
        d = template.to_dict()
        assert d["id"] == "tmpl1"
        assert d["name"] == "Test Template"
        assert "phases" in d

    def test_workflow_execution_creation(self):
        execution = WorkflowExecution(
            id="exec1",
            template_id="tmpl1",
            template_name="Standard Pipeline",
            trigger_mode=TriggerMode.MANUAL_TASK,
            task_description="Fix bug #123",
        )
        assert execution.status == WorkflowStatus.PENDING
        assert execution.trigger_mode == TriggerMode.MANUAL_TASK
        assert execution.iteration == 1

    def test_workflow_execution_to_dict(self):
        execution = WorkflowExecution(
            id="exec1",
            template_id="tmpl1",
            template_name="Test",
            trigger_mode=TriggerMode.GITHUB_ISSUE,
            task_description="Test task",
        )
        d = execution.to_dict()
        assert d["id"] == "exec1"
        assert d["status"] == "pending"
        assert d["trigger_mode"] == "github_issue"

    def test_phase_execution_creation(self):
        phase_exec = PhaseExecution(
            id="pexec1",
            workflow_execution_id="exec1",
            phase_id="phase1",
            phase_name="Analysis",
            phase_role=PhaseRole.ANALYZER,
        )
        assert phase_exec.status == PhaseStatus.PENDING
        assert phase_exec.tokens_input == 0

    def test_phase_execution_to_dict(self):
        phase_exec = PhaseExecution(
            id="pexec1",
            workflow_execution_id="exec1",
            phase_id="phase1",
            phase_name="Analysis",
            phase_role=PhaseRole.ANALYZER,
            tokens_input=1000,
            tokens_output=500,
        )
        d = phase_exec.to_dict()
        assert d["id"] == "pexec1"
        assert d["phase_name"] == "Analysis"
        assert d["tokens_input"] == 1000

    def test_artifact_creation(self):
        artifact = Artifact(
            id="art1",
            workflow_execution_id="exec1",
            phase_execution_id="phase1",
            artifact_type=ArtifactType.REVIEW_REPORT,
            name="Code Review",
            content="All good!",
            file_path="/tmp/review.md",
        )
        assert artifact.artifact_type == ArtifactType.REVIEW_REPORT
        assert artifact.content == "All good!"

    def test_artifact_to_dict(self):
        artifact = Artifact(
            id="art1",
            workflow_execution_id="exec1",
            phase_execution_id="phase1",
            artifact_type=ArtifactType.TASK_LIST,
            name="Tasks",
            content="- Task 1",
            file_path="/tmp/tasks.md",
        )
        d = artifact.to_dict()
        assert d["id"] == "art1"
        assert d["artifact_type"] == "task_list"

    def test_budget_tracker_creation(self):
        tracker = BudgetTracker(
            id="bt1",
            scope="execution",
            scope_id="exec1",
            period_start="2024-01-01T00:00:00",
            budget_limit=10.0,
        )
        assert tracker.scope == "execution"
        assert tracker.budget_limit == 10.0
        assert tracker.total_spent == 0.0

    def test_budget_tracker_to_dict(self):
        tracker = BudgetTracker(
            id="bt1",
            scope="project",
            scope_id="proj1",
            period_start="2024-01-01T00:00:00",
            total_spent=5.50,
            token_count_input=10000,
            token_count_output=5000,
        )
        d = tracker.to_dict()
        assert d["scope"] == "project"
        assert d["total_spent"] == 5.50


class TestProviderTypes:
    def test_all_provider_types_have_values(self):
        for provider in ProviderType:
            assert provider.value is not None
            assert isinstance(provider.value, str)

    def test_iteration_behavior_options(self):
        assert IterationBehavior.AUTO_ITERATE.value == "auto_iterate"
        assert IterationBehavior.PAUSE_FOR_APPROVAL.value == "pause_for_approval"

    def test_failure_behavior_options(self):
        assert FailureBehavior.PAUSE_NOTIFY.value == "pause_notify"
        assert FailureBehavior.FALLBACK_PROVIDER.value == "fallback_provider"
        assert FailureBehavior.SKIP_PHASE.value == "skip_phase"

    def test_phase_role_values(self):
        assert PhaseRole.ANALYZER.value == "analyzer"
        assert PhaseRole.IMPLEMENTER.value == "implementer"
        assert PhaseRole.VERIFIER.value == "verifier"

    def test_artifact_type_values(self):
        assert ArtifactType.TASK_LIST.value == "task_list"
        assert ArtifactType.CODE_DIFF.value == "code_diff"
        assert ArtifactType.REVIEW_REPORT.value == "review_report"

    def test_trigger_mode_values(self):
        assert TriggerMode.GITHUB_ISSUE.value == "github_issue"
        assert TriggerMode.MANUAL_TASK.value == "manual_task"
        assert TriggerMode.DIRECTORY_SCAN.value == "directory_scan"


class TestModelSerialization:
    def test_workflow_template_roundtrip(self):
        config = ProviderConfig(
            provider_type=ProviderType.GEMINI_SDK,
            model_name="gemini-pro",
        )
        phase = WorkflowPhase(
            id="p1",
            name="Analysis",
            role=PhaseRole.ANALYZER,
            provider_config=config,
            prompt_template="Analyze",
            output_artifact_type=ArtifactType.TASK_LIST,
        )
        template = WorkflowTemplate(
            id="t1",
            name="Test",
            description="Test template",
            phases=[phase],
        )
        d = template.to_dict()
        restored = WorkflowTemplate.from_dict(d)
        assert restored.id == template.id
        assert restored.name == template.name
        assert len(restored.phases) == 1
        assert restored.phases[0].name == "Analysis"

    def test_workflow_execution_roundtrip(self):
        phase_exec = PhaseExecution(
            id="pe1",
            workflow_execution_id="exec1",
            phase_id="p1",
            phase_name="Analysis",
            phase_role=PhaseRole.ANALYZER,
            status=PhaseStatus.COMPLETED,
            tokens_input=1000,
        )
        execution = WorkflowExecution(
            id="exec1",
            template_id="t1",
            template_name="Test",
            trigger_mode=TriggerMode.MANUAL_TASK,
            task_description="Do something",
            phase_executions=[phase_exec],
        )
        d = execution.to_dict()
        restored = WorkflowExecution.from_dict(d)
        assert restored.id == execution.id
        assert len(restored.phase_executions) == 1
        assert restored.phase_executions[0].status == PhaseStatus.COMPLETED
