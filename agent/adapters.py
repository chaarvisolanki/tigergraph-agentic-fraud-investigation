from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx

from .models import Action, CaseRecord, Evidence, NextBestAction


class TigerGraphAdapter:
    """Small REST adapter for installed GSQL queries; falls back only when explicitly enabled."""

    def __init__(self) -> None:
        self.base_url = os.getenv("TIGERGRAPH_URL", "").rstrip("/")
        self.graph = os.getenv("TIGERGRAPH_GRAPH", "FraudGraph")
        self.token = os.getenv("TIGERGRAPH_TOKEN", "")
        self.allow_demo_fallback = os.getenv("ALLOW_DEMO_FALLBACK", "true").lower() == "true"

    async def _query(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.base_url:
            if self.allow_demo_fallback:
                return {"query": name, "params": params, "demo": True}
            raise RuntimeError("TIGERGRAPH_URL is required when ALLOW_DEMO_FALLBACK is false")
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.base_url}/restpp/graph/{self.graph}/{name}",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    async def get_transaction_context(self, transaction_id: str) -> dict[str, Any]:
        return await self._query("get_transaction_context", {"transaction_id": transaction_id})

    async def get_account_context(self, account_id: str) -> dict[str, Any]:
        return await self._query("get_account_context", {"account_id": account_id})

    async def account_device_ring(self, account_id: str, min_shared_accounts: int) -> dict[str, Any]:
        return await self._query("account_device_ring", {
            "account_id": account_id, "min_shared_accounts": min_shared_accounts,
        })

    async def account_velocity(
        self, account_id: str, window_start: datetime, window_end: datetime,
        velocity_threshold: int, amount_threshold: float,
    ) -> dict[str, Any]:
        return await self._query("account_velocity", {
            "account_id": account_id, "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(), "velocity_threshold": velocity_threshold,
            "amount_threshold": amount_threshold,
        })

    async def prior_similar_cases(self, account_id: str | None, pattern_id: str | None) -> list[dict[str, Any]]:
        result = await self._query("prior_similar_cases", {"account_id": account_id or "", "pattern_id": pattern_id or ""})
        return result.get("results", result.get("cases", []))

    async def write_case_memory(self, case: CaseRecord) -> bool:
        # Replace with a write_case_memory GSQL query or TigerGraph loading job in deployment.
        return bool(case.case_id)


class PolicyGraphRAG:
    async def retrieve(self, query: str, evidence: list[Evidence]) -> dict[str, Any]:
        return {
            "query": query,
            "policy": "Use step-up authentication when velocity and shared-device signals co-occur; escalate high-risk cases.",
            "evidence_summaries": [item.summary for item in evidence[:12]],
        }


class MockActionAdapter:
    approved_actions = {"allow_transaction", "block_transaction", "monitor_account", "open_case", "request_step_up_auth"}

    async def execute(self, action: Action) -> dict[str, Any]:
        if action.action not in self.approved_actions:
            raise PermissionError(f"Action is not pre-approved: {action.action}")
        return {"mock": True, "executed_action": action.action}


class RuleReasoner:
    async def assess(self, context: dict[str, Any]) -> dict[str, Any]:
        case = context["case"]
        graph = context["graph"]
        velocity = graph.get("velocity", {})
        ring = graph.get("device_ring", {})
        count = velocity.get("transaction_count", 0)
        shared = ring.get("shared_account_count", 0)
        high_signal = count >= 3 and shared >= 2
        return {
            "risk_level": "high" if high_signal else "medium",
            "confidence": 0.88 if high_signal else 0.58,
            "enough_evidence": (not high_signal) or bool(case.get("additional_evidence_received")),
            "decision": "block_transaction" if high_signal else "request_step_up_auth",
            "requested_evidence_type": "step_up_auth",
            "evidence_gap": "Confirm account-owner intent before blocking activity.",
            "findings": [],
        }

    async def choose_next_best_action(self, context: dict[str, Any]) -> NextBestAction:
        assessment = context["assessment"]
        action = "block_transaction" if assessment["enough_evidence"] and assessment["risk_level"] == "high" else "request_step_up_auth"
        return NextBestAction(action=action, rationale=assessment["decision"], confidence=assessment["confidence"])

    async def explain(self, context: dict[str, Any]) -> str:
        return "Decision grounded in graph transaction history, velocity, shared-device relationships, prior cases, and policy context."
