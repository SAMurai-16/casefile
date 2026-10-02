# CaseFile: Multi-Agent Claims Orchestration Platform


**CaseFile** is a production-grade multi-agent claims adjudication state machine designed for auto insurance processing. Built on **LangGraph**, **Pydantic**, and **FastAPI**, it decomposes end-to-end claim settlement across specialized worker agents with **strictly typed handoffs**, **externalized SQLite checkpoint persistence**, **deterministic loop guards**, **code-enforced cost ceilings**, and a **mandatory Human-in-the-Loop (HITL) approval gate** before any payout can be issued.

---

## 🏛️ System Architecture

```
                                  [ Raw Intake: FNOL + Estimate + Policy + Aux Docs ]
                                                           │
                                                           ▼
                                                ┌──────────────────────┐
                                                │   SUPERVISOR NODE    │◄─────────────────┐
                                                │ (Deterministic Code) │                  │
                                                └──────────┬───────────┘                  │
                                                           │                              │
                          ┌────────────────────────────────┼──────────────────┐           │
                          │ EXTRACT                        │ INVESTIGATE      │ REVIEW    │ (Rework Loop)
                          ▼                                ▼                  ▼           │
               ┌────────────────────┐            ┌───────────────────┐ ┌───────────────┐  │
               │  EXTRACTOR AGENT   │            │INVESTIGATOR AGENT │ │REVIEWER AGENT ├──┘
               │ (Unstructured FNOL │            │ (Policy & Fraud   │ │(LLM Cross-Doc │
               │  + Shop Estimates) │            │  Scoring Engine)  │ │ Sanity Check) │
               └─────────┬──────────┘            └─────────┬─────────┘ └───────┬───────┘
                         │                                 │                   │
                         └────────────────► [ Supervisor ] ◄───────────────────┘
                                                   │
                             ┌─────────────────────┴──────────────────────┐
                             │                                            │
                             ▼                                            ▼
                  ┌─────────────────────┐                      ┌────────────────────┐
                  │ HUMAN APPROVAL GATE │                      │   TERMINAL SINK    │
                  │ (interrupt() block) │                      │ (Deny / SIU / Exit)│
                  └──────────┬──────────┘                      └────────────────────┘
                             │
                             ▼
                  [ Authorized Settlement ]
```

---

## 🤖 Deep Dive: The Specialized Agents

CaseFile uses an ensemble of specialized worker nodes governed by a deterministic supervisor. Rather than relying on a single monolithic prompt, each agent has an explicit operational scope, strictly typed Pydantic schema contracts, and deterministic code safeguards.

| Agent / Node | Engine Type | Core Responsibilities | Primary Output Schema |
| :--- | :--- | :--- | :--- |
| **Supervisor** | Pure Python | Lifecycle orchestration, circuit breakers, loop guards, budget limits | `HandoffPayload` |
| **Extractor** | LLM + Schema Fallbacks | Document normalization, itemized repair parsing, dual entity extraction | `ExtractionResult` |
| **Investigator** | Hybrid (Python + LightGBM + LLM) | Multi-line coverage evaluation, ACV vehicle valuation, fraud risk scoring, dynamic clause audits | `InvestigationResult` |
| **Reviewer** | Adversarial LLM | Cross-document entity verification, damage physics alignment, payout adjudication | `ReviewResult` |
| **Human Gate** | Cryptographic Barrier | Adjuster review, line-item adjustments, thread resumption | `HumanDecision` |

---

### 1. Supervisor Node (`supervisor_node`)
*Deterministic Orchestration & Circuit Breakers*

The Supervisor is the backbone of the state machine. It does **not** consume LLM tokens for routing; it is implemented entirely in deterministic Python logic to prevent routing hallucination, non-determinism, or state drift.

- **Phase State Machine**: Deterministically transitions the claim across lifecycle phases:
  $$\text{intake} \longrightarrow \text{extraction} \longrightarrow \text{investigation} \longrightarrow \text{review} \longrightarrow \text{human\_gate} \longrightarrow \text{terminate}$$
- **Loop Guards & Recursion Controls**: Tracks `rework_count`. If the Reviewer requests more than 2 re-extractions, the Supervisor breaks the cycle and forces escalation to a human adjuster.
- **Fast-Path Circuit Breaker**: If the Investigator determines the policy is `Lapsed`, `Cancelled`, `Suspended`, or voided, the Supervisor immediately short-circuits to the `terminate` sink in **5 steps**, bypassing the Reviewer and saving LLM compute cost.
- **Cost & Token Ceiling Guards**:
  - Halts execution with `budget_terminated` if cumulative cost exceeds **\$2.00** or tokens exceed **50,000**.
  - Halts execution with `step_limit_terminated` if graph execution exceeds **15 supersteps**.

---

### 2. Extractor Agent (`extractor_node`)
*Multimodal Document Ingestion & Schema Normalization*

The Extractor parses unstructured, heterogeneous claim submissions into a clean, strongly typed Pydantic contract.

- **Heterogeneous Intake**: Normalizes varied body shop estimate formats (CCC ONE, Mitchell, Audatex, and independent shop itemizations) alongside call-center FNOL narratives and structured intake headers.
- **Dual Entity Disambiguation**: Specifically separates `insured_name` (filing contact on intake) from `driver_name` (individual operating the vehicle during the loss) to surface permissive use and identity variance.
- **Multi-Line Auxiliary Parsing**: Extracts itemized auxiliary claims when present:
  - *Rental Car Receipts*: Agency, billing duration (days), daily rate, and total charged.
  - *Medical Invoices*: Provider clinic, diagnosis code, patient name, date of service, and itemized billing.
  - *Third-Party Subrogation Demands*: Claimant details, property damage demands, and bodily injury claims.
- **Output Schema Contract**: Produces `ExtractionResult` containing parsed vehicle VIN/odometer, incident timeline, driver narrative, and itemized parts/labor lists.

---

### 3. Investigator Agent (`investigator_node`)
*Policy Law, Actuarial Fraud Scoring & Contract Auditing*

The Investigator is a hybrid engine pairing pure deterministic actuarial calculations with a calibrated machine learning fraud model and LLM-driven contract auditing.

- **Deterministic Multi-Line Coverage Audit**:
  - Cross-references accident facts against policy terms, deductible structures, and incident classification (*Collision* vs *Comprehensive / Other-Than-Collision*).
  - Evaluates status using strict keyword parsing (`not active`, `inactive`, `lapsed`, `cancelled`, `suspended`).
  - Implements financial limits for rental reimbursement (daily/total day caps) and MedPay (per-person limits).
- **Vehicle Valuation & Total Loss (Python Engine)**:
  - Calculates vehicle Actual Cash Value (ACV) based on vehicle year, make, model, and mileage depreciation curves.
  - Evaluates Total Loss candidates: triggers total loss protocol if $\frac{\text{Repair Cost}}{\text{ACV}} \ge 75\%$.
- **Actuarial ML Fraud Detection (LightGBM + SHAP)**:
  - Predicts a calibrated $0-100$ `fraud_risk_score` using feature engineering: loss history within 12/24 months, policy age/tenure, severe damage ratios, and unverified filing channels.
  - Generates human-readable SHAP risk signal contributions (e.g., `+18 pts: Claim filed within 60 days of policy inception`).
  - Recommends mandatory SIU (Special Investigation Unit) referral if fraud score exceeds threshold.
- **LLM-Driven Contract Clauses & Endorsement Auditing**:
  - Leverages the LLM to cross-examine the policy contract record against the extracted loss circumstances, vehicle state, and billed repair operations.
  - Validates active endorsement riders against claimed expenses and cites specific policy clauses and contractual findings into `applied_exclusions`, `endorsements_validated`, and `clause_audit_notes`.

---

### 4. Reviewer Agent (`reviewer_node`)
*Adversarial Cross-Examination & Settlement Synthesis (LLM Reasoning)*

The Reviewer operates as an adversarial auditor. It cross-examines the findings of the Extractor, Investigator, and raw documents to synthesize the final settlement proposal.
- **Physical Damage Consistency**: Compares itemized parts billed by the body shop against the driver's incident narrative (e.g., rear-end collision narrative vs front suspension billing).
- **Chronological & Invoice Auditing**:
  - Audits auxiliary medical bills and rental receipts for impossible dates (e.g. treatment dated in a future year or predating the crash).
  - Verifies body shop arithmetic (stated subtotal vs sum of line items).
- **Contractual Compliance Verification**: Cross-references the Investigator's clause audit notes and validates whether all billed operations comply with verified policy terms and active endorsements.
- **Adjudication Decisions**:
  - `approve`: All damage aligns, costs are within limits, and policy is in force.
  - `partial_approve`: Legitimate loss, but capped by policy limits or clause adjustments.
  - `rework`: Factual ambiguity between narrative and estimate (instructs Extractor to re-parse).
  - `escalate_siu`: Fraud risk critical or severe entity impersonation detected.
  - `deny`: Policy void, inactive, or loss outside covered terms.

---

### 5. Human Approval Gate (`human_gate_node`)
*Cryptographic LangGraph `interrupt()` Barrier*

CaseFile never allows an autonomous LLM to authorize financial disbursements directly.

- **Zero-Bypass Interrupt**: Utilizes LangGraph's `interrupt()` primitive. Execution physically stops before reaching settlement.
- **Comprehensive Briefing**: Surfaces the audited discrepancy list, contract clause citations, itemized payout table, and liability alerts to the adjuster.
- **Adjuster Override & Resume**: The adjuster can adjust dollar allocations line-by-line, append comments, and submit a signed `HumanDecision` (`approve`, `reject`, or `rework`) to resume the checkpointed thread.

---

## 🛡️ Code-Enforced Invariants (Never Left to Hope)

| Guard | Code Location | Enforced Limit | Behavior on Breach |
|---|---|---|---|
| **Cost Ceiling** | `casefile/agents/supervisor.py` | \$2.00 per claim | Halts graph with `budget_terminated` |
| **Token Budget** | `casefile/agents/supervisor.py` | 50,000 tokens | Halts graph with `budget_terminated` |
| **Max Steps** | `casefile/agents/supervisor.py` | 15 supersteps | Halts graph with `step_limit_terminated` |
| **Rework Limit** | `casefile/agents/supervisor.py` | Max 2 loops | Escalate to human rather than looping |
| **Human Gate** | `casefile/graph/human_gate.py` | Mandatory | Graph cannot reach payout without human resume |

---

## 💻 Full-Stack Architecture

In addition to the core LangGraph state machine, CaseFile includes a complete FastAPI backend and React frontend dashboard:

### FastAPI Backend (`casefile/server/`)
- **Port**: `8001` (configured to prevent collisions with host services)
- **Features**:
  - Real-time **Server-Sent Events (SSE)** endpoint streaming live graph node entries, token counters, and gate pause alerts.
  - `/api/v1/claims`: Claim package listing, detail inspection, and custom claim ingestion.
  - `/api/v1/approval-gate`: Endpoints for human adjuster review and thread resumption.
  - `/api/v1/snapshots`: Time-travel checkpoint inspection and state snapshot trees.
  - `/api/v1/traces`: Historical trace analytics.

### React + TypeScript Dashboard (`frontend/`)
- **Port**: `5173` (Vite dev server)
- **Features**:
  - **Live Pipeline Visualizer**: Animated graph stages showing pulsing execution and gate pauses.
  - **Real-Time Terminal Console**: Live SSE log streaming.
  - **Evidence Table**: Itemized parts, labor operations, and auxiliary receipts.
  - **ML Risk Card**: Visual LightGBM score gauge, ACV repair ratio, and SHAP factors.
  - **Interactive HITL Modal**: One-click adjuster signoff and payout adjudication.

---

## 🚀 Quickstart & Usage

### 1. Environment Setup
```bash
git clone https://github.com/your-org/casefile.git
cd casefile

# Set up Python virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Configure API Keys in .env
cp .env.example .env
# Set GEMINI_API_KEY or GOOGLE_API_KEY
```

### 2. Run Tests
```bash
# Run complete test suite (22 unit, integration, and API tests)
pytest tests/ -v
```

### 3. Run Claims CLI
```bash
# Run single claim with live Gemini LLM
python scripts/run_single_claim.py 002

# Run single claim interactively (waits for manual approval in terminal)
python scripts/run_single_claim.py 001 --interactive

# Run batch suite of 30 repository claims
python scripts/run_batch.py

# Replay execution deterministically from an SQLite checkpoint snapshot
python scripts/replay_from_snapshot.py --claim 001
```

### 4. Launch Full Dashboard & Backend
```bash
# Terminal 1: Launch FastAPI Backend Server
python scripts/run_server.py --port 8001 --reload

# Terminal 2: Launch React Frontend Dashboard
cd frontend
npm install
npm run dev
```
Open **`http://localhost:5173`** in your browser.
