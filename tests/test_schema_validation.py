import pytest
from casefile.store import ClaimStore
from casefile.schema import (
    RepairLineItem,
    RentalReceiptExtraction,
    MedicalBillExtraction,
    ThirdPartyClaimExtraction,
    ExtractionResult,
    InvestigationResult,
    ReviewResult,
    HandoffPayload,
)

def test_claim_store_loads_all_packages():
    store = ClaimStore()
    available = store.list_available_claims()
    assert len(available) >= 5, "Expected at least 5 claims in data store"
    
    for c_id in ["001", "002", "003", "004", "005"]:
        fnol, est, pol, rental, med, tp = store.load_claim_package(c_id)
        assert isinstance(fnol, dict)
        assert isinstance(est, dict)
        assert isinstance(pol, dict)
        # Optional documents
        if c_id == "001":
            assert rental is not None
            assert med is not None
        elif c_id == "005":
            assert tp is not None

def test_handoff_payload_schema():
    payload = HandoffPayload(
        source_node="supervisor",
        target_node="extractor",
        action="EXTRACT",
        claim_id="CLM-TEST-001",
        step_number=1,
        timestamp="2026-09-28T00:00:00Z",
        summary="Test handoff payload validation"
    )
    assert payload.source_node == "supervisor"
    assert payload.action == "EXTRACT"

def test_decision_schemas():
    ext = ExtractionResult(
        claim_id="CLM-001",
        incident_date="2026-09-14",
        incident_location="Austin, TX",
        incident_summary="Test accident",
        vehicle_vin="2HGFE2F59PH512847",
        vehicle_year=2023,
        vehicle_make="Honda",
        vehicle_model="Civic",
        is_drivable=True,
        reported_damage_areas=["rear"],
        injuries_reported=False,
        police_report_filed=True,
        other_party_involved=True,
        repair_facility_name="Lone Star Collision",
        estimate_date="2026-09-16",
        total_parts_cost=1000.0,
        total_labor_cost=500.0,
        claimed_grand_total=1500.0,
        rental_receipt=RentalReceiptExtraction(
            rental_agency="Enterprise",
            start_date="2026-09-16",
            end_date="2026-09-20",
            days_billed=4,
            daily_rate=35.0,
            total_charged=140.0
        )
    )
    assert ext.claimed_grand_total == 1500.0
    assert ext.rental_receipt.days_billed == 4
