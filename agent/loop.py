from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

from .models import (
    Action,
    ActionStatus,
    CaseRecord,
    CaseStatus,
    Evidence,
    Finding,
    Trigger,
    utc_now,
)
from .ports import ActionPort, GraphPort, GraphRAGPort, ReasonerPort


class InvestigationAgent:
    """Deterministic orchestration layer; LLMs and external systems are ports."""

    def __init__(
        self,
        graph: GraphPort,
        graphrag: GraphRAGPort,
        actions: ActionPort,
        reasoner: ReasonerPort,
    ) -> None:
        self.graph = graph
        self.graphrag = graphrag
        self.actions = actions
        self.reasoner = reasoner

    async def investigate(self, trigger: Trigger) -> CaseRecord:
        case = CaseRecord(
            case_id=f"case_{uuid4().hex[:12]}",
            status=CaseStatus.OPEN,
            trigger=trigger,
            account_id=trigger.account_id,
            transaction_id=trigger.transaction_id,
        )

        # Investigate and gather deterministic graph facts.
        graph_context = await self._investigate_entities(case)
        case.evidence.extend(self._evidence_from_graph(graph_context))
        rag_context = await self.graphrag.retrieve(
            query=self._build_retrieval_query(case, graph_context),
            evidence=case.evidence,
        )
        context = {"case": case.model_dump(mode="json"), "graph": graph_context, "rag": rag_context}

        assessment = await self.reasoner.assess(context)
        self._apply_assessment(case, assessment)
        case.next_best_action_before_evidence = await self.reasoner.choose_next_best_action(
            {**context, "assessment": assessment}
        )

        # This is the required conditional branch. It is not executed for every case.
        if not case.enough_evidence_before_request:
            case.status = CaseStatus.EVIDENCE_REQUESTED
            case.additional_evidence_requested = self._controlled_evidence_request(case, assessment)
            received_evidence = await self._receive_requested_evidence(case.additional_evidence_requested)
            case.additional_evidence_received = received_evidence is not None
            if received_evidence is not None:
                case.status = CaseStatus.UNDER_REVIEW
                case.evidence.append(
                    Evidence(
                        evidence_id=f"ev_{uuid4().hex[:12]}",
                        type=case.additional_evidence_requested["type"],
                        source="controlled_action",
                        summary=received_evidence["summary"],
                        strength=0.65,
                        polarity="neutral",
                    )
                )
                post_context = {
                    **context,
                    "case": case.model_dump(mode="json"),
                    "additional_evidence": case.evidence[-1].model_dump(mode="json"),
                }
                post_assessment = await self.reasoner.assess(post_context)
                self._apply_assessment(case, post_assessment)
                case.next_best_action_after_evidence = await self.reasoner.choose_next_best_action(
                    {**post_context, "assessment": post_assessment}
                )
        else:
            case.next_best_action_after_evidence = case.next_best_action_before_evidence

        final_context = {"case": case.model_dump(mode="json"), "graph": graph_context, "rag": rag_context}
        await self._apply_recommended_action(case, case.next_best_action_after_evidence)
        case.explanation = await self.reasoner.explain(final_context)
        case.sar_required = case.risk_level in {"high", "critical"} and any(
            action.action in {"block_transaction", "block_account", "file_sar"} for action in case.actions
        )
        if case.sar_required:
            case.sar_text = (
                f"Suspicious activity case {case.case_id}: {case.explanation} "
                f"Risk level {case.risk_level}, confidence {case.confidence:.2f}. "
                "This SAR draft requires compliance review before filing."
            )
        case.status = CaseStatus.RESOLVED
        case.updated_at = utc_now()
        case.graph_written = await self.graph.write_case_memory(case)
        return case

    async def _investigate_entities(self, case: CaseRecord) -> dict[str, Any]:
        context: dict[str, Any] = {}
        if case.transaction_id:
            context["transaction"] = await self.graph.get_transaction_context(case.transaction_id)
        if case.account_id:
            context["account"] = await self.graph.get_account_context(case.account_id)
            context["device_ring"] = await self.graph.account_device_ring(case.account_id, 2)
            now = utc_now()
            context["velocity"] = await self.graph.account_velocity(
                case.account_id, now - timedelta(minutes=30), now, 3, 1000.0
            )
            context["prior_cases"] = await self.graph.prior_similar_cases(case.account_id, None)
        return context

    @staticmethod
    def _evidence_from_graph(context: dict[str, Any]) -> list[Evidence]:
        evidence: list[Evidence] = []
        for key, value in context.items():
            if not value:
                continue
            evidence.append(
                Evidence(
                    evidence_id=f"ev_{uuid4().hex[:12]}",
                    type=key,
                    source="tigergraph",
                    summary=f"{key}: {value}",
                    strength=0.5,
                    polarity="neutral",
                    metadata={"raw": value},
                )
            )
        return evidence

    @staticmethod
    def _build_retrieval_query(case: CaseRecord, graph_context: dict[str, Any]) -> str:
        return (
            f"Investigate {case.trigger.type} for account {case.account_id or 'unknown'} "
            f"and transaction {case.transaction_id or 'unknown'} using these graph signals: "
            f"{', '.join(graph_context.keys())}."
        )

    @staticmethod
    def _apply_assessment(case: CaseRecord, assessment: dict[str, Any]) -> None:
        case.risk_level = assessment.get("risk_level", case.risk_level)
        case.confidence = float(assessment.get("confidence", case.confidence))
        case.enough_evidence_before_request = bool(assessment.get("enough_evidence", False))
        case.findings = [Finding.model_validate(item) for item in assessment.get("findings", [])]
        case.decisions.append(assessment.get("decision", "continue_review"))

    @staticmethod
    def _controlled_evidence_request(case: CaseRecord, assessment: dict[str, Any]) -> dict[str, Any]:
        requested_type = assessment.get("requested_evidence_type", "analyst_review")
        allowed = {"step_up_auth", "account_owner_confirmation", "analyst_review"}
        if requested_type not in allowed:
            requested_type = "analyst_review"
        return {
            "type": requested_type,
            "reason": assessment.get("evidence_gap", "Evidence is insufficient for a confident decision."),
            "case_id": case.case_id,
        }

    async def _receive_requested_evidence(self, request: dict[str, Any]) -> dict[str, str] | None:
        # Replace with a real event/callback integration. Stub returns a controlled result.
        return {
            "type": request["type"],
            "summary": f"Controlled evidence received for {request['type']}.",
        }

    async def _apply_recommended_action(self, case: CaseRecord, next_action: Any) -> None:
        if next_action is None:
            return
        action = Action(
            action_id=f"act_{uuid4().hex[:12]}",
            action=next_action.action,
            status=(
                ActionStatus.PENDING_APPROVAL
                if next_action.requires_human_approval
                else ActionStatus.RECOMMENDED
            ),
            rationale=next_action.rationale,
            requires_human_approval=next_action.requires_human_approval,
            approval_route="fraud_analyst" if next_action.requires_human_approval else None,
        )
        if not action.requires_human_approval:
            action.result = await self.actions.execute(action)
            action.status = ActionStatus.EXECUTED
        case.actions.append(action)
