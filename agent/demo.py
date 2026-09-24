from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from .loop import InvestigationAgent
from .models import Action, Evidence, NextBestAction, Trigger


class DemoGraph:
    async def get_transaction_context(self, transaction_id: str) -> dict[str, Any]:
        return {"transaction_id": transaction_id, "amount": 842.10, "risk_score": 0.91}

    async def get_account_context(self, account_id: str) -> dict[str, Any]:
        return {"account_id": account_id, "customer_status": "active"}

    async def account_device_ring(self, account_id: str, min_shared_accounts: int) -> dict[str, Any]:
        return {"shared_account_count": 6, "shared_device_count": 1}

    async def account_velocity(
        self,
        account_id: str,
        window_start: datetime,
        window_end: datetime,
        velocity_threshold: int,
        amount_threshold: float,
    ) -> dict[str, Any]:
        return {"transaction_count": 4, "total_amount": 1840.50, "window_minutes": 30}

    async def prior_similar_cases(self, account_id: str | None, pattern_id: str | None) -> list[dict[str, Any]]:
        return [{"case_id": "case_prior_001", "outcome": "confirmed_fraud", "similarity": 0.86}]

    async def write_case_memory(self, case) -> bool:
        print(f"Graph memory write: {case.case_id}")
        return True


class DemoGraphRAG:
    async def retrieve(self, query: str, evidence: list[Evidence]) -> dict[str, Any]:
        return {
            "policy": "Require step-up authentication when velocity and device-sharing signals co-occur.",
            "retrieved_evidence_count": len(evidence),
        }


class DemoActions:
    async def execute(self, action: Action) -> dict[str, Any]:
        return {"mock": True, "executed_action": action.action}


class DemoReasoner:
    def __init__(self) -> None:
        self.assessment_count = 0

    async def assess(self, context: dict[str, Any]) -> dict[str, Any]:
        self.assessment_count += 1
        if self.assessment_count == 1:
            return {
                "risk_level": "high",
                "confidence": 0.62,
                "enough_evidence": False,
                "decision": "request_step_up_auth",
                "requested_evidence_type": "step_up_auth",
                "evidence_gap": "Confirm that the account owner initiated the transaction.",
                "findings": [],
            }
        return {
            "risk_level": "high",
            "confidence": 0.91,
            "enough_evidence": True,
            "decision": "block_transaction_and_escalate",
            "findings": [],
        }

    async def choose_next_best_action(self, context: dict[str, Any]) -> NextBestAction:
        if self.assessment_count == 1:
            return NextBestAction(
                action="request_step_up_auth",
                rationale="Evidence is not yet sufficient for an irreversible action.",
                confidence=0.62,
            )
        return NextBestAction(
            action="block_transaction",
            rationale="High velocity, shared-device activity, and matching prior fraud evidence.",
            confidence=0.91,
        )

    async def explain(self, context: dict[str, Any]) -> str:
        return "The decision used transaction risk, shared-device activity, velocity, prior cases, policy, and step-up evidence."


async def main() -> None:
    agent = InvestigationAgent(DemoGraph(), DemoGraphRAG(), DemoActions(), DemoReasoner())
    case = await agent.investigate(
        Trigger(
            type="risk_score",
            source="demo",
            account_id="acct_demo_001",
            transaction_id="txn_demo_001",
            reason="High bank risk score",
        )
    )
    print(json.dumps(case.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
