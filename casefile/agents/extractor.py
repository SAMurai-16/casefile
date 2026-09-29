import json
from datetime import datetime, timezone
from ..schema import ClaimState, ExtractionResult, HandoffPayload
from ..tracing.cost_tracker import calculate_call_cost
from .llm_factory import LLMFactory

def extractor_node(state: ClaimState) -> dict:
    """
    Extractor Agent:
    Reads raw FNOL narrative and body shop Repair Estimate,
    plus any optional auxiliary documents (Rental Receipts, Medical Bills, Third-Party Claims).
    Produces standardized, typed ExtractionResult.
    """
    fnol_str = json.dumps(state["fnol_raw"], indent=2)
    estimate_str = json.dumps(state["estimate_raw"], indent=2)
    
    # Check for optional auxiliary documents
    auxiliary_docs_text = ""
    if state.get("rental_raw"):
        auxiliary_docs_text += f"\n=== OPTIONAL DOCUMENT: RENTAL CAR RECEIPT ===\n{json.dumps(state['rental_raw'], indent=2)}\n"
    if state.get("medical_raw"):
        auxiliary_docs_text += f"\n=== OPTIONAL DOCUMENT: MEDICAL BILL ===\n{json.dumps(state['medical_raw'], indent=2)}\n"
    if state.get("third_party_raw"):
        auxiliary_docs_text += f"\n=== OPTIONAL DOCUMENT: THIRD-PARTY CLAIM DEMAND ===\n{json.dumps(state['third_party_raw'], indent=2)}\n"

    prompt = f"""
You are the expert Insurance Document Extractor Agent.
Analyze the following claim documentation.
Extract and normalize all required information into the target schema.

=== DOCUMENT 1: FNOL INTAKE ===
{fnol_str}

=== DOCUMENT 2: REPAIR ESTIMATE INVOICE ===
{estimate_str}
{auxiliary_docs_text}

Extraction Instructions:
- Extract incident date, time, location, and factual description from the narrative.
- Extract all vehicle identification information.
- Parse driver-reported damage areas, injury descriptions, and police report numbers from the narrative text.
- Standardize all repair operations, parts, labor hours, and bottom-line dollar totals from the estimate.
- If optional rental receipt is provided, extract agency name, dates, days billed, daily rate, and total charged.
- If optional medical bill is provided, extract provider name, patient name, treatment, and total billed.
- If optional third-party claim is provided, extract third-party claimant, property damage, and injury amounts.
- If any optional document is not provided, leave that extraction field as None.
"""
    structured_llm = LLMFactory.get_structured_llm(ExtractionResult)
    
    # Run structured extraction
    result: ExtractionResult = structured_llm.invoke(prompt)
    
    tokens_used, cost_usd = calculate_call_cost({
        "input_tokens": 1400,
        "output_tokens": 450,
        "total_tokens": 1850
    })
    
    # Build summary mentioning any optional docs extracted
    extras = []
    if result.rental_receipt:
        extras.append(f"Rental: {result.rental_receipt.days_billed}d @ ${result.rental_receipt.daily_rate}/d")
    if result.medical_bills:
        extras.append(f"Medical: {len(result.medical_bills)} bill(s)")
    if result.third_party_claim:
        extras.append(f"Third-Party: ${result.third_party_claim.property_damage_claimed + result.third_party_claim.bodily_injury_claimed:,.2f}")
    
    extra_summary = f" (+ {', '.join(extras)})" if extras else ""


    # for tracing
    handoff = HandoffPayload(
        source_node="extractor",
        target_node="supervisor",
        action="EXTRACT",
        claim_id=state["claim_id"],
        step_number=state["step_count"] + 1,
        timestamp=datetime.now(timezone.utc).isoformat(),
        summary=f"Extracted claim details: Repair total ${result.claimed_grand_total:,.2f} from {result.repair_facility_name}{extra_summary}"
    )
    
    return {
        "extraction": result,
        "step_count": state["step_count"] + 1,
        "total_tokens": state["total_tokens"] + tokens_used,
        "total_cost_usd": state["total_cost_usd"] + cost_usd,
        "handoff_history": state["handoff_history"] + [handoff],
        "current_phase": "extraction"
    }
