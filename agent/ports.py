from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from .models import Action, CaseRecord, Evidence, NextBestAction


class GraphPort(Protocol):
    async def get_transaction_context(self, transaction_id: str) -> dict[str, Any]: ...
    async def get_account_context(self, account_id: str) -> dict[str, Any]: ...
    async def account_device_ring(self, account_id: str, min_shared_accounts: int) -> dict[str, Any]: ...
    async def account_velocity(
        self,
        account_id: str,
        window_start: datetime,
        window_end: datetime,
        velocity_threshold: int,
        amount_threshold: float,
    ) -> dict[str, Any]: ...
    async def prior_similar_cases(
        self, account_id: str | None, pattern_id: str | None
    ) -> list[dict[str, Any]]: ...
    async def write_case_memory(self, case: CaseRecord) -> bool: ...


class GraphRAGPort(Protocol):
    async def retrieve(self, query: str, evidence: list[Evidence]) -> dict[str, Any]: ...


class ActionPort(Protocol):
    async def execute(self, action: Action) -> dict[str, Any]: ...


class ReasonerPort(Protocol):
    async def assess(self, context: dict[str, Any]) -> dict[str, Any]: ...
    async def choose_next_best_action(self, context: dict[str, Any]) -> NextBestAction: ...
    async def explain(self, context: dict[str, Any]) -> str: ...
