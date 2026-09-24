# Agentic Fraud Investigation

## What this project does

This project investigates the 20 HHGOA benchmark cases using:

- The supplied IEEE-CIS-derived transaction and identity data
- Closed investigation history as case memory
- Graph relationships for customers, cards, transactions, devices, and evidence
- Policy-grounded next-best-action decisions
- Optional TigerGraph Savanna, TigerGraph MCP, LangGraph, and OpenAI integration
- A FastAPI API and a small analyst UI

The local system works without external credentials. It uses deterministic demo adapters until TigerGraph and an LLM are configured.

## Current status

Completed:

- Actual dataset extracted under `dataset/`
- 20 benchmark answer files generated under `cases/`
- Conditional evidence-request branch
- Initial and final next-best-actions
- Approval routes (`auto`, `L1`, `L2`)
- SAR decision and narrative fields
- Graph schema and GSQL query drafts
- FastAPI endpoint and UI
- Optional LLM and LangGraph adapters
- Savanna-compatible 27-column transaction export

Savanna status:

- A first graph has already been created from `dataset/transactions_savanna.csv`
- It contains `Customer`, `Card`, and `Transaction`
- The API key is not yet wired to the application

## Folder layout

```text
agent/
  api.py              FastAPI routes and answer-file persistence
  adapters.py         TigerGraph, GraphRAG, action, and rule adapters
  benchmark.py        Generates all 20 benchmark JSON files
  demo.py             Offline end-to-end demonstration
  langgraph_flow.py   Optional LangGraph wrapper
  llm_reasoner.py     Optional OpenAI-compatible reasoner
  loop.py             Investigation orchestration
  main.py             FastAPI application entrypoint
  models.py           Pydantic case and action models
  ports.py            Reusable adapter interfaces
  sources.py          Local policy and closed-case sources

graph/
  schema.gsql         Graph vertex and edge definitions
  queries.gsql        Device ring, velocity, and prior-case queries

dataset/
  README.md
  transactions.csv
  transactions_savanna.csv
  identity.csv
  closed_cases_history.csv
  case_pack.csv

cases/                20 generated benchmark answer files
ui/index.html         Minimal analyst dashboard
requirements.txt      Python dependencies
```

## Local setup

From PowerShell:

```powershell
Set-Location "E:\TigerGraph Agentic Fraud Investigation HHGOA"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

## Run the benchmark

```powershell
python -m agent.benchmark --dataset dataset --out cases
```

Expected result:

```text
Wrote 20 answer files to cases
```

Each answer follows the dataset README format:

- `case`
- `evidence_requests`
- `next_best_actions.initial`
- `next_best_actions.final`
- `sar`
- `stop_reason`
- tool and latency metadata

## Run the offline demo

```powershell
python -m agent.demo
```

The demo shows:

1. A risk-score trigger opens a case.
2. Graph facts and policy context are retrieved.
3. The first assessment requests step-up evidence.
4. The initial next-best-action is recorded.
5. Mock evidence is received.
6. The final action is selected and executed if allowed.
7. Case memory is written through the graph adapter.

## Run FastAPI and the UI

```powershell
uvicorn agent.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/ui/index.html
http://127.0.0.1:8000/docs
```

The endpoint is:

```text
POST /investigations
```

Example request:

```json
{
  "type": "risk_score",
  "source": "analyst_dashboard",
  "account_id": "C12382",
  "transaction_id": "3514030",
  "reason": "High-risk transaction requires review"
}
```

## Savanna and API keys

An API key alone is not sufficient. The application also needs:

1. Savanna/TigerGraph REST host URL
2. Graph name
3. A token accepted by that graph's RESTPP endpoint
4. Installed GSQL query names

The organization API key shown in Savanna settings may authenticate organization resources but may not be the same credential used by the graph REST API. Use the graph's connection details or database secrets for the application.

Set credentials locally; never commit them:

```powershell
$env:TIGERGRAPH_URL = "https://your-graph-host"
$env:TIGERGRAPH_GRAPH = "your-graph-name"
$env:TIGERGRAPH_TOKEN = "your-graph-token"
$env:ALLOW_DEMO_FALLBACK = "false"
```

If the graph credentials are not configured, leave:

```powershell
$env:ALLOW_DEMO_FALLBACK = "true"
```

This keeps the local demo working.

## Savanna graph currently created

The first Savanna import used `dataset/transactions_savanna.csv` because Savanna's import wizard limits CSV files to 120 columns. The original file has 397 columns and remains unchanged for benchmark processing.

The first graph contains:

```text
Customer -> Card -> Transaction
```

The next graph additions are:

```text
DeviceProfile
EmailDomain
BillingRegion
ClosedCase
Evidence
FraudPattern
PolicyClause
```

Use the GSQL editor only after selecting the correct Savanna workspace and graph. Do not paste a new schema into an existing generated graph unless the graph is recreated; vertex and edge names must match the deployed graph.

## Optional LLM

Without an API key, the project uses `RuleReasoner`.

To enable the OpenAI-compatible reasoner:

```powershell
$env:OPENAI_API_KEY = "your-key"
$env:OPENAI_MODEL = "gpt-4o-mini"
```

Then restart Uvicorn. The LLM receives structured graph and policy context, not the raw transaction CSV.

## Optional LangGraph

The default custom loop is intentionally simple and is allowed by the hackathon. To use LangGraph:

```powershell
pip install langgraph
```

Use `build_langgraph()` from `agent/langgraph_flow.py` around an `InvestigationAgent`.

## Investigation workflow

```text
Trigger
  -> Create/open case
  -> Query transaction, account, device, velocity, and prior cases
  -> Retrieve policy and evidence context
  -> Assess risk, confidence, and evidence sufficiency
  -> If insufficient: request controlled evidence
  -> Record initial next-best-action
  -> Reassess after assumed response
  -> Record final next-best-action
  -> Execute only pre-approved actions
  -> Mark approval-required actions for L1/L2
  -> Generate explanation and SAR when policy requires
  -> Write case memory to graph
  -> Persist answer JSON
```

## Recommended demo order

1. Run `python -m agent.demo`.
2. Run the benchmark and show the 20 files in `cases/`.
3. Start FastAPI and open the UI.
4. Show the Savanna graph with Customer, Card, and Transaction.
5. Show the GSQL editor and execute a graph query.
6. Explain that the local adapters can be switched to real TigerGraph using the environment variables above.

## Important data rule

Do not use the public IEEE-CIS/Kaggle dataset to recover fraud outcomes. The supplied dataset intentionally transforms identifiers, timestamps, and amounts. Use only the files in `dataset/`.
