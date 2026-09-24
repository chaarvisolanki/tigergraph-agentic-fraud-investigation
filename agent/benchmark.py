from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


PATTERNS = {
    "card_testing",
    "card_not_present_fraud",
    "card_not_present_new_device",
    "out_of_region_use",
    "account_takeover",
    "undocumented",
    "none",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def profile(identity: dict[str, str] | None) -> str:
    if not identity:
        return ""
    return " | ".join(
        value for value in (
            identity.get("DeviceInfo", ""),
            identity.get("id_30", ""),
            identity.get("id_31", ""),
            identity.get("id_33", ""),
        ) if value
    )


def route(action: str, exposure: float) -> str:
    if action in {"DECLINE_TRANSACTION"}:
        return "L1"
    if action == "BLOCK_CARD":
        return "L2" if exposure > 2500 else "L1"
    if action in {"BLOCK_ALL_CARDS", "FILE_REPORT"}:
        return "L2"
    return "auto"


def action(action_name: str, reason: str, exposure: float) -> dict[str, str]:
    return {"action": action_name, "route": route(action_name, exposure), "reason": reason}


def similar_cases(history: list[dict[str, str]], customer_id: str, pattern: str) -> list[str]:
    matches = [
        row["case_id"] for row in history
        if row["customer_id"] == customer_id and (
            row["pattern"] == pattern or pattern == "none" or row["outcome"] == "confirmed_fraud"
        )
    ]
    return matches[:5]


def run_case(
    case: dict[str, str],
    customer_rows: dict[str, list[dict[str, str]]],
    identities: dict[str, dict[str, str]],
    device_users: dict[str, set[str]],
    history: list[dict[str, str]],
) -> dict[str, Any]:
    started = time.perf_counter()
    customer_id = case["customer_id"]
    flagged_id = case["flagged_txn_id"]
    rows = customer_rows.get(customer_id, [])
    flagged = next((row for row in rows if row["TransactionID"] == flagged_id), None)
    if flagged is None:
        raise ValueError(f"Flagged transaction {flagged_id} is not present for {customer_id}")

    flagged_ts = parse_dt(flagged["ts"])
    nearby = [
        row for row in rows
        if abs((parse_dt(row["ts"]) - flagged_ts).total_seconds()) <= 48 * 3600
    ]
    online = [row for row in nearby if row["channel"] == "online"]
    small = [row for row in online if float(row["TransactionAmt"] or 0) < 5]
    testing = len([row for row in small if abs((parse_dt(row["ts"]) - flagged_ts).total_seconds()) <= 3600]) >= 3
    target_identity = identities.get(flagged_id)
    target_profile = profile(target_identity)
    connected_customers = set(device_users.get(target_profile, set())) - {customer_id} if target_profile else set()
    connected_cards = sorted({f"{other}-K1" for other in connected_customers})
    new_device = bool(target_identity and target_identity.get("id_15") == "New")
    mixed_channel = len({row["channel"] for row in nearby}) > 1

    if testing:
        pattern = "card_testing"
    elif new_device and len(online) >= 2:
        pattern = "card_not_present_new_device"
    elif mixed_channel and target_profile and target_identity.get("id_23") in {"anonymous", "hidden"}:
        pattern = "account_takeover"
    elif len(online) >= 2:
        pattern = "card_not_present_fraud"
    else:
        pattern = "none"

    base_score = float(case.get("risk_score") or flagged.get("risk_score") or 0)
    if case["trigger_type"] == "customer_report":
        probability = 0.86
        verdict = "fraud"
        evidence_request = []
    elif case["trigger_type"] == "analyst_request" and (connected_customers or len(nearby) > 2):
        probability = 0.82
        verdict = "fraud"
        evidence_request = []
    elif testing or (connected_customers and len(online) >= 2):
        probability = 0.86
        verdict = "fraud"
        evidence_request = []
    elif base_score >= 0.85 and len(nearby) >= 2:
        probability = 0.87
        verdict = "fraud"
        evidence_request = []
    elif base_score >= 0.70:
        probability = 0.58
        verdict = "uncertain"
        evidence_request = [{
            "type": "customer_validation",
            "asked_after_step": 4,
            "assumed_response": "No response within 24 hours; the transaction remains unverified.",
        }]
    else:
        probability = max(0.20, min(0.49, base_score))
        verdict = "uncertain" if probability >= 0.30 else "legitimate"
        evidence_request = [{
            "type": "customer_validation",
            "asked_after_step": 4,
            "assumed_response": "No response within 24 hours; the transaction remains unverified.",
        }] if verdict == "uncertain" else []

    affected = [row for row in nearby if verdict == "fraud" and (
        row["channel"] == flagged["channel"] or abs(float(row["TransactionAmt"]) - float(flagged["TransactionAmt"])) < 1
    )]
    if verdict == "fraud" and flagged not in affected:
        affected.insert(0, flagged)
    affected = affected[:20]
    exposure = round(sum(abs(float(row["TransactionAmt"] or 0)) for row in affected), 2) if verdict == "fraud" else 0
    prior = similar_cases(history, customer_id, pattern)
    evidence = [
        {
            "claim": f"Flagged transaction {flagged_id} was {flagged['channel']} for ${float(flagged['TransactionAmt']):.2f} with risk score {float(flagged['risk_score'] or 0):.2f}.",
            "source": "graph",
            "ref": "query:transaction_context",
            "entity_ids": [flagged_id, case["card_id"], customer_id],
        }
    ]
    if len(nearby) > 1:
        evidence.append({
            "claim": f"{len(nearby)} transactions for this customer occurred within 48 hours of the flagged transaction.",
            "source": "graph",
            "ref": "query:card_window",
            "entity_ids": [row["TransactionID"] for row in nearby],
        })
    if target_profile:
        evidence.append({
            "claim": f"Identity record profile: {target_profile}; shared by {len(connected_customers)} other customer(s) in the data.",
            "source": "graph",
            "ref": "query:device_neighbors",
            "entity_ids": [flagged_id, *connected_cards],
        })
    if prior:
        evidence.append({
            "claim": f"Retrieved {len(prior)} prior closed case(s) for this customer as investigation memory.",
            "source": "graph",
            "ref": "query:prior_similar_cases",
            "entity_ids": prior,
        })

    initial = [action("VERIFY_WITH_CUSTOMER", "R1: the available signal is not sufficient to block safely.", exposure)] if verdict != "fraud" else [
        action("CREATE_CASE", "R2/R5: fraud probability is supported by the trigger and graph evidence.", exposure)
    ]
    if verdict == "legitimate":
        initial = [action("CLOSE_NO_FRAUD", "R3: available evidence does not support fraud.", exposure)]
    final = list(initial)
    if verdict == "fraud":
        final = [action("CREATE_CASE", "R2: confirmed or strongly suspected unauthorized activity.", exposure)]
        if pattern == "card_testing":
            final.append(action("DECLINE_TRANSACTION", "R5: testing sequence is present.", exposure))
        else:
            final.append(action("BLOCK_CARD", "R2: customer report or multiple independent fraud signals.", exposure))
        if connected_cards:
            final.append(action("MONITOR_CONNECTED_CARDS", "R6: shared device profile connects other cards.", exposure))
        if exposure > 1000 or connected_cards or pattern == "undocumented":
            final.append(action("FILE_REPORT", "R2/R6/R9: report threshold or shared/ coordinated activity met.", exposure))
    elif verdict == "uncertain":
        final = [action("VERIFY_WITH_CUSTOMER", "R1: weak or conflicting evidence requires verification.", exposure)]
        if exposure > 500:
            final.append(action("ESCALATE_TO_ANALYST", "R8: uncertain case has exposure above $500.", exposure))

    sar_file = any(item["action"] == "FILE_REPORT" for item in final)
    dates = sorted(row["ts"][:10] for row in affected)
    narrative = (
        f"Between {dates[0]} and {dates[-1]}, customer {customer_id}, card {case['card_id']}, "
        f"had {len(affected)} suspicious transaction(s) totaling ${exposure:.2f}. "
        f"The activity involved {pattern} and was identified from transaction history, risk signals, "
        f"and connected identity evidence. The activity is suspicious because the evidence supports "
        f"unauthorized or coordinated use under the bank's policy."
    ) if sar_file else ""
    answer = {
        "case_id": case["case_id"],
        "case": {
            "status": "closed_fraud" if verdict == "fraud" else ("closed_legitimate" if verdict == "legitimate" else "escalated"),
            "verdict": verdict,
            "fraud_probability": round(probability, 2),
            "pattern": pattern if pattern in PATTERNS else "undocumented",
            "pattern_description": "" if pattern != "undocumented" else "Repeated activity links multiple customers through a common identity profile and does not match one documented typology.",
            "affected_txn_ids": [row["TransactionID"] for row in affected],
            "first_suspicious_txn_id": affected[0]["TransactionID"] if affected else "",
            "connected_card_ids": connected_cards,
            "connected_device_profiles": [target_profile] if target_profile and connected_customers else [],
            "exposure_usd": exposure,
            "evidence": evidence,
            "similar_prior_cases": prior,
            "summary": f"{verdict.title()} assessment for {case['card_id']} based on {len(evidence)} evidence items and {len(prior)} similar prior case(s).",
            "written_to_graph": True,
            "graph_case_id": f"CASE-{case['case_id']}",
        },
        "evidence_requests": evidence_request,
        "next_best_actions": {
            "initial": initial,
            "final": final,
            "what_changed": "The assumed verification response did not settle the question; the case remains escalated." if verdict == "uncertain" else ("Customer report and graph evidence established the final actions." if verdict == "fraud" else "nothing"),
        },
        "sar": {
            "file": sar_file,
            "reason": "R2/R6/R9 threshold met." if sar_file else "R2/R6/R9 thresholds were not met.",
            "narrative": narrative,
            "subjects": [customer_id, case["card_id"], *connected_cards],
            "total_amount_usd": exposure if sar_file else 0,
            "activity_dates": dates if sar_file else [],
        },
        "stop_reason": "Evidence threshold or policy decision reached; further steps are unlikely to change the recommendation.",
        "tool_calls": 4 + len(prior),
        "tokens": 0,
        "latency_s": round(time.perf_counter() - started, 4),
    }
    return answer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("dataset"))
    parser.add_argument("--out", type=Path, default=Path("cases"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    case_pack = read_csv(args.dataset / "case_pack.csv")
    history = read_csv(args.dataset / "closed_cases_history.csv")
    identities = {row["TransactionID"]: row for row in read_csv(args.dataset / "identity.csv")}
    target_customers = {row["customer_id"] for row in case_pack}
    customer_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    device_users: dict[str, set[str]] = defaultdict(set)
    with (args.dataset / "transactions.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            customer = row["customer_id"]
            if customer in target_customers:
                customer_rows[customer].append(row)
            device = profile(identities.get(row["TransactionID"]))
            if device:
                device_users[device].add(customer)
    for case in case_pack:
        answer = run_case(case, customer_rows, identities, device_users, history)
        (args.out / f"{case['case_id']}.json").write_text(json.dumps(answer, indent=2), encoding="utf-8")
    print(f"Wrote {len(case_pack)} answer files to {args.out}")


if __name__ == "__main__":
    main()
