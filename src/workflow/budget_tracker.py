from datetime import datetime
from typing import Any

from .models import BudgetTracker, generate_id, estimate_cost
from ..database import db


class BudgetManager:
    
    def __init__(self):
        self._trackers: dict[str, BudgetTracker] = {}

    def _get_tracker_key(self, scope: str, scope_id: str) -> str:
        return f"{scope}:{scope_id}"

    def get_or_create(
        self,
        scope: str,
        scope_id: str,
        budget_limit: float | None = None,
    ) -> BudgetTracker:
        key = self._get_tracker_key(scope, scope_id)
        
        if key in self._trackers:
            return self._trackers[key]
        
        data = db.get_budget_tracker(scope, scope_id)
        if data:
            tracker = BudgetTracker(
                id=data["id"],
                scope=data["scope"],
                scope_id=data["scope_id"],
                period_start=data["period_start"],
                budget_limit=data.get("budget_limit"),
                total_spent=data.get("total_spent", 0.0),
                token_count_input=data.get("token_count_input", 0),
                token_count_output=data.get("token_count_output", 0),
            )
        else:
            tracker = BudgetTracker(
                id=generate_id(),
                scope=scope,
                scope_id=scope_id,
                period_start=datetime.now().isoformat(),
                budget_limit=budget_limit,
            )
            db.create_budget_tracker(tracker.to_dict())
        
        self._trackers[key] = tracker
        return tracker

    def record_usage(
        self,
        scope: str,
        scope_id: str,
        model: str,
        tokens_input: int,
        tokens_output: int,
    ) -> tuple[float, bool]:
        tracker = self.get_or_create(scope, scope_id)
        cost = estimate_cost(model, tokens_input, tokens_output)
        
        tracker.total_spent += cost
        tracker.token_count_input += tokens_input
        tracker.token_count_output += tokens_output
        
        db.increment_budget(scope, scope_id, cost, tokens_input, tokens_output)
        
        is_ok, _ = tracker.check_budget()
        return cost, is_ok

    def check_budget(
        self,
        scope: str,
        scope_id: str,
        additional_cost: float = 0.0,
    ) -> tuple[bool, float]:
        tracker = self.get_or_create(scope, scope_id)
        return tracker.check_budget(additional_cost)

    def set_limit(
        self,
        scope: str,
        scope_id: str,
        limit: float | None,
    ) -> bool:
        tracker = self.get_or_create(scope, scope_id)
        tracker.budget_limit = limit
        return db.update_budget_tracker(tracker.id, {"budget_limit": limit})

    def get_summary(self, scope: str, scope_id: str) -> dict[str, Any]:
        tracker = self.get_or_create(scope, scope_id)
        is_ok, remaining = tracker.check_budget()
        
        return {
            "scope": scope,
            "scope_id": scope_id,
            "budget_limit": tracker.budget_limit,
            "total_spent": tracker.total_spent,
            "remaining": remaining if tracker.budget_limit else None,
            "tokens_input": tracker.token_count_input,
            "tokens_output": tracker.token_count_output,
            "total_tokens": tracker.token_count_input + tracker.token_count_output,
            "within_budget": is_ok,
            "period_start": tracker.period_start,
        }

    def get_execution_summary(self, execution_id: str) -> dict[str, Any]:
        return self.get_summary("execution", execution_id)

    def get_project_summary(self, project_id: int) -> dict[str, Any]:
        return self.get_summary("project", str(project_id))

    def get_global_summary(self) -> dict[str, Any]:
        return self.get_summary("global", "global")

    def record_execution_usage(
        self,
        execution_id: str,
        project_id: int | None,
        model: str,
        tokens_input: int,
        tokens_output: int,
    ) -> tuple[float, bool]:
        cost, exec_ok = self.record_usage(
            "execution", execution_id, model, tokens_input, tokens_output
        )
        
        project_ok = True
        if project_id:
            _, project_ok = self.record_usage(
                "project", str(project_id), model, tokens_input, tokens_output
            )
        
        _, global_ok = self.record_usage(
            "global", "global", model, tokens_input, tokens_output
        )
        
        return cost, exec_ok and project_ok and global_ok

    def reset_tracker(self, scope: str, scope_id: str) -> bool:
        key = self._get_tracker_key(scope, scope_id)
        if key in self._trackers:
            del self._trackers[key]
        
        tracker = self.get_or_create(scope, scope_id)
        tracker.total_spent = 0.0
        tracker.token_count_input = 0
        tracker.token_count_output = 0
        tracker.period_start = datetime.now().isoformat()
        
        return db.update_budget_tracker(tracker.id, {
            "total_spent": 0.0,
            "token_count_input": 0,
            "token_count_output": 0,
            "period_start": tracker.period_start,
        })


budget_manager = BudgetManager()
