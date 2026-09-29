# CaseFile: Multi-Agent Claims Orchestration

> *"You talk about termination conditions, loop guards and cost ceilings before you talk about agent personas. That is the line between an engineer and a prompt hobbyist."*

**CaseFile** is a production-grade multi-agent orchestration state machine designed for auto insurance claim processing. It decomposes end-to-end claim settlement across specialized worker agents with **strictly typed handoffs**, **externalized checkpoint persistence**, **deterministic loop guards**, **code-enforced cost ceilings**, and a **mandatory human approval gate** before any payout can be issued.

---

## Architecture Overview

```
                                  [ Raw Intake: FNOL + Estimate + Policy ]
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
         │ (Unstructured FNOL │            │ (Policy & Fraud   │ │(Cross-Doc     │
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
            [ Authorized Payout ]
```

### The 4 Agents and Their Strict Contracts

1. **Supervisor (`supervisor_node`)**:
   - **Not an LLM prompt**: 100% deterministic Python routing function.
   - Enforces the hard **\$2.00 cost ceiling** and **15 max supersteps**.
   - Enforces the **max 2 rework loops** guard to prevent infinite cycles.
   - Fast-paths denied claims (e.g., lapsed policy) in 5 steps without wasting reviewer tokens.
2. **Extractor Agent (`extractor_node`)**:
   - Reads raw, unstructured driver statements and heterogeneous repair shop estimates (CCC ONE, Mitchell, Audatex, Independent).
   - Produces a normalized, type-safe `ExtractionResult` Pydantic model.
3. **Investigator Agent (`investigator_node`)**:
   - Evaluates coverage against internal policy records and loss circumstances.
   - Independently calculates deductible and maximum eligible payout.
   - Analyzes raw loss history, policy tenure, and accident timing to calculate a 0–100 `fraud_risk_score`.
4. **Reviewer Agent (`reviewer_node`)**:
   - Cross-references damage narrative against repair line items.
   - Can issue a typed `rework` command back to Extractor if discrepancies exist.
   - Formulates the final recommendation: `approve`, `partial_approve`, `deny`, or `escalate_siu`.
5. **Human Approval Gate (`human_gate_node`)**:
   - Implements LangGraph's `interrupt()` primitive.
   - Payout recommendations are **physically blocked** until a human adjuster resumes the thread with a signed decision.

---

## Code-Enforced Invariants (Never Left to Hope)

| Guard | Code Location | Enforced Limit | Behavior on Breach |
|---|---|---|---|
| **Cost Ceiling** | `casefile/agents/supervisor.py` | \$2.00 per claim | Halts graph with `budget_terminated` |
| **Token Budget** | `casefile/agents/supervisor.py` | 50,000 tokens | Halts graph with `budget_terminated` |
| **Max Steps** | `casefile/agents/supervisor.py` | 15 supersteps | Halts graph with `step_limit_terminated` |
| **Rework Limit** | `casefile/agents/supervisor.py` | Max 2 loops | Escalate to human rather than looping |
| **Human Gate** | `casefile/graph/human_gate.py` | Mandatory | Graph cannot reach payout without human resume |

---

## Ship Gate Deliverables & Proof

### 1. 30 Recorded Claim Runs with Node-Path Traces
All 30 claims execute through the graph and output full JSON traces to `traces/`.
```bash
python scripts/run_batch.py
```
Each trace captures every superstep, exact node sequence, tokens, and dollar cost:
```json
{
  "claim_id": "CLM-2026-10001",
  "node_path": [
    "supervisor", "extractor", "supervisor", "investigator",
    "supervisor", "reviewer", "supervisor", "human_gate", "terminate"
  ],
  "total_steps": 8,
  "total_tokens": 4350,
  "total_cost_usd": 0.0008,
  "terminal_status": "approved",
  "final_payout_amount": 3517.79
}
```

### 2. Snapshot Replayability
A run can be interrupted or restored from any superstep snapshot and will reach the exact same terminal settlement:
```bash
python scripts/replay_from_snapshot.py --claim 001
```
Output:
```
Original Terminal Status: approved | Payout: $3,517.79
Midway Checkpoint ID: 1f1bb03d-704f-644c-8004-727ff14983d4
Replayed Terminal Status: approved | Payout: $3,517.79
SUCCESS: Snapshot replay proved 100% deterministic terminal parity!
```

### 3. Reviewer Rework Loop Guard
Proves that the Reviewer can reject work, send it back for extraction, and the graph still terminates cleanly:
```bash
python scripts/demo_rework_loop.py
```
Output:
```
Step 6 | Node: reviewer   | Phase: review    | Rework Count: 0
Step 7 | Node: supervisor | Phase: extractor | Rework Count: 1
SUCCESS: Graph looped through rework and cleanly terminated under guard rails.
```

### 4. Cost Per Claim Chart
Visualizes all 30 claim costs against the hard \$2.00 ceiling:
```bash
python scripts/generate_cost_chart.py
# Saves high-res plot to traces/cost_per_claim_chart.png
```

---

## Quickstart & Installation

```bash
cd /home/samyak/code/Projects/casefile

# Activate virtual environment
source .venv/bin/activate

# Run test suite
pytest tests/ -v

# Run single claim
python scripts/run_single_claim.py 001

# Run interactive claim with manual human approval
python scripts/run_single_claim.py 001 --interactive

# Run batch of 30 claims
python scripts/run_batch.py

# Replay from snapshot
python scripts/replay_from_snapshot.py

# Generate cost chart
python scripts/generate_cost_chart.py
```
