from __future__ import annotations

import json
import os
from typing import Any

from .adapters import RuleReasoner
from .models import NextBestAction


class LLMReasoner:
    """Optional OpenAI-compatible reasoner with deterministic fallback."""

    def __init__(self) -> None:
        self.fallback = RuleReasoner()
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.client = None
        if os.getenv("OPENAI_API_KEY"):
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI()

    async def _ask(self, instruction: str, context: dict[str, Any]) -> dict[str, Any]:
        if self.client is None:
            return {}
        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Return JSON only. Use only supplied evidence and policy."},
                {"role": "user", "content": instruction + "\n" + json.dumps(context, default=str)},
            ],
        )
        return json.loads(response.choices[0].message.content or "{}")

    async def assess(self, context: dict[str, Any]) -> dict[str, Any]:
        return await self._ask("Assess risk and evidence sufficiency.", context) or await self.fallback.assess(context)

    async def choose_next_best_action(self, context: dict[str, Any]) -> NextBestAction:
        result = await self._ask("Choose the next policy action.", context)
        return NextBestAction.model_validate(result) if result else await self.fallback.choose_next_best_action(context)

    async def explain(self, context: dict[str, Any]) -> str:
        result = await self._ask("Return JSON with an explanation citing policy rules.", context)
        return result.get("explanation") or await self.fallback.explain(context)
