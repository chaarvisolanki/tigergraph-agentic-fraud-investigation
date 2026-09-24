from __future__ import annotations

import os

from .adapters import MockActionAdapter, PolicyGraphRAG, RuleReasoner, TigerGraphAdapter
from .api import create_app
from .loop import InvestigationAgent
from .llm_reasoner import LLMReasoner


class MemoryGraph(TigerGraphAdapter):
    async def get_transaction_context(self, transaction_id: str):
        return {"transaction_id": transaction_id, "amount": 842.10, "risk_score": 0.91}

    async def get_account_context(self, account_id: str):
        return {"account_id": account_id, "status": "active"}

    async def account_device_ring(self, account_id: str, min_shared_accounts: int):
        return {"shared_account_count": 6, "shared_device_count": 1}

    async def account_velocity(self, account_id, window_start, window_end, velocity_threshold, amount_threshold):
        return {"transaction_count": 4, "total_amount": 1840.50}

    async def prior_similar_cases(self, account_id, pattern_id):
        return [{"case_id": "prior_demo", "outcome": "confirmed_fraud", "similarity": 0.86}]


graph = TigerGraphAdapter()
if not graph.base_url and graph.allow_demo_fallback:
    graph = MemoryGraph()

reasoner = LLMReasoner() if os.getenv("OPENAI_API_KEY") else RuleReasoner()
agent = InvestigationAgent(graph, PolicyGraphRAG(), MockActionAdapter(), reasoner)
app = create_app(agent)
