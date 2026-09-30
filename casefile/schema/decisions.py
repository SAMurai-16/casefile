from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, Field

class RepairLineItem(BaseModel):
    """Standardized representation of a single line item on an auto repair invoice."""
    description: str = Field(description="Normalized component or service description")
    category: Literal["parts", "body_labor", "paint_labor", "paint_materials", "mechanical_labor", "sublet", "structural", "towing_storage", "misc"] = Field(
        description="Standardized category of the repair cost"
    )
    part_type: Optional[str] = Field(default=None, description="OEM, Aftermarket, Used, or None if labor")
    amount: float = Field(description="Total cost for this item in USD")
    labor_hours: Optional[float] = Field(default=None, description="Labor hours if applicable")

class RentalReceiptExtraction(BaseModel):
    """Extracted data from an optional rental car agency invoice."""
    rental_agency: str = Field(description="Name of rental car agency (e.g. Enterprise, Hertz)")
    invoice_number: Optional[str] = None
    start_date: str = Field(description="Rental start date (YYYY-MM-DD)")
    end_date: str = Field(description="Rental return date (YYYY-MM-DD)")
    days_billed: int = Field(description="Number of calendar days rented")
    daily_rate: float = Field(description="Daily rental charge before tax/fees")
    total_charged: float = Field(description="Total invoice amount billed for rental vehicle")

class MedicalBillExtraction(BaseModel):
    """Extracted data from an optional doctor, clinic, or hospital medical bill."""
    provider_name: str = Field(description="Hospital, physician, or clinic name")
    patient_name: str
    date_of_service: str = Field(description="Date medical treatment was administered")
    diagnosis_or_treatment: str = Field(description="Treatment summary, e.g. cervical strain exam, X-rays, meds")
    total_billed: float = Field(description="Total dollar amount billed for medical services")

class ThirdPartyClaimExtraction(BaseModel):
    """Extracted data from an optional third-party damage or injury claim demand."""
    claimant_name: str = Field(description="Name of the other driver or injured party")
    vehicle_damaged: Optional[str] = None
    property_damage_claimed: float = Field(default=0.0, description="Cost to repair other party vehicle/property")
    bodily_injury_claimed: float = Field(default=0.0, description="Medical costs / trauma claimed by third party")
    demand_summary: str = Field(description="Factual summary of third-party demand against the insured")

class ExtractionResult(BaseModel):
    """Normalized structured claim payload produced by the Extractor Agent."""
    claim_id: str
    incident_date: str = Field(description="ISO or YYYY-MM-DD date of incident")
    incident_time: Optional[str] = Field(default=None, description="Approximate time of day")
    incident_location: str = Field(description="Intersection, street, or city of accident")
    incident_summary: str = Field(description="Clear factual summary of how the accident happened")
    
    # Damaged vehicle facts
    vehicle_vin: str
    vehicle_year: int
    vehicle_make: str
    vehicle_model: str
    vehicle_license_plate: Optional[str] = None
    vehicle_mileage: Optional[int] = None
    is_drivable: bool = Field(description="Whether vehicle could be driven from the scene")
    
    # Damage & injury findings from narrative
    reported_damage_areas: List[str] = Field(description="Specific vehicle areas reported damaged by driver")
    injuries_reported: bool = Field(description="True if driver or passengers suffered injuries")
    injuries_summary: Optional[str] = Field(default=None, description="Description of injuries and medical care")
    
    # Authority & other party
    police_report_filed: bool
    police_report_number: Optional[str] = None
    police_agency_or_officer: Optional[str] = None
    other_party_involved: bool
    other_party_details: Optional[str] = None
    
    # Core repair estimate extraction
    repair_facility_name: str
    repair_facility_tax_id: Optional[str] = None
    estimate_date: str
    itemized_repairs: List[RepairLineItem] = Field(default_factory=list)
    total_parts_cost: float
    total_labor_cost: float
    total_additional_costs: float = Field(default=0.0, description="Materials, sublets, towing, tax")
    claimed_grand_total: float = Field(description="Final bottom-line dollar amount requested by the body shop")

    # OPTIONAL AUXILIARY EXTRACTIONS
    rental_receipt: Optional[RentalReceiptExtraction] = Field(
        default=None,
        description="Extracted rental car receipt if provided by policyholder, else None"
    )
    medical_bills: Optional[List[MedicalBillExtraction]] = Field(
        default=None,
        description="Extracted medical treatment bills for insured/passengers if provided, else None"
    )
    third_party_claim: Optional[ThirdPartyClaimExtraction] = Field(
        default=None,
        description="Extracted third-party damages/injuries claimed against policyholder if provided, else None"
    )

class InvestigationResult(BaseModel):
    """Coverage and fraud evaluation produced by the Investigator Agent."""
    claim_id: str
    policy_number: str
    policy_status: Literal["Active", "Lapsed", "Cancelled", "Suspended"]
    policy_effective_date: str
    policy_expiration_date: str
    incident_classification: Literal["collision", "comprehensive", "liability_only"] = Field(
        description="Classification of incident: collision vs non-collision OTC (animal/weather/theft)"
    )
    
    # 1. Collision Coverage Analysis
    collision_covered: bool
    collision_limit_per_incident: Optional[float] = None
    collision_deductible: Optional[float] = None
    max_eligible_collision_payout: Optional[float] = Field(
        default=None,
        description="Limit minus deductible (or vehicle repair payout ceiling)"
    )
    
    # 2. Rental Reimbursement Analysis
    rental_reimbursement_covered: bool = Field(default=False)
    rental_daily_limit: Optional[float] = None
    rental_max_days: Optional[int] = None
    rental_eligible_payout: float = Field(default=0.0, description="Eligible rental reimbursement based on days & daily rate")
    rental_notes: Optional[str] = None
    
    # 3. Medical Payments (MedPay) Analysis
    medpay_covered: bool = Field(default=False)
    medpay_per_person_limit: Optional[float] = None
    medpay_eligible_payout: float = Field(default=0.0, description="Eligible policyholder medical payout based on bills & limit")
    medpay_notes: Optional[str] = None
    
    # 4. Third-Party Liability Exposure Analysis
    liability_exposure_flag: bool = Field(default=False, description="True if insured was at fault with third-party damage/injuries")
    property_damage_liability_limit: Optional[float] = None
    bodily_injury_per_person_limit: Optional[float] = None
    liability_exposure_summary: Optional[str] = None
    
    # 5. Vehicle Valuation & Total Loss Evaluation
    actual_cash_value: Optional[float] = Field(default=None, description="Pre-accident Fair Market Value (ACV)")
    repair_to_acv_ratio: Optional[float] = Field(default=None, description="Repair cost divided by ACV")
    is_total_loss_candidate: bool = Field(default=False, description="True if repair cost >= 75% of vehicle value")

    # 6. Overall Coverage Verdict & LightGBM Fraud Risk Scoring
    coverage_verdict: Literal["covered", "not_covered", "partial_coverage"]
    coverage_denial_reason: Optional[str] = None
    prior_claims_count_12mo: int
    prior_claims_count_24mo: int
    policy_tenure_months: Optional[int] = None
    fraud_risk_level: Literal["low", "medium", "high", "critical"]
    fraud_risk_score: int = Field(description="Calibrated LightGBM risk score from 0 (safest) to 100 (extreme risk)")
    detected_fraud_signals: List[str] = Field(default_factory=list, description="Specific risk indicators and SHAP feature impacts")
    siu_referral_recommended: bool = Field(description="Whether Special Investigation Unit should review")

    # 7. Policy Contract Clauses & Endorsement Auditing
    applied_exclusions: List[str] = Field(
        default_factory=list,
        description="Policy exclusions triggered by loss facts (e.g. Commercial Rideshare Exclusion)"
    )
    endorsements_validated: List[str] = Field(
        default_factory=list,
        description="Active policy endorsement riders verified in force (e.g. OEM Parts Replacement Rider)"
    )
    clause_audit_notes: List[str] = Field(
        default_factory=list,
        description="Contractual compliance observations on LKQ parts rules, custom equipment caps, or permissive drivers"
    )

class ReviewResult(BaseModel):
    """Cross-document sanity check and recommendation produced by the Reviewer Agent."""
    claim_id: str
    damage_narrative_alignment: bool = Field(description="Do parts on the estimate match damage described in narrative?")
    discrepancy_details: List[str] = Field(default_factory=list, description="Any items on estimate not supported by narrative")
    
    repair_cost_vs_limit_check: Literal["within_limits", "exceeds_limits", "policy_void"]
    
    # Multi-Line Itemized Payout Breakdown
    payout_breakdown: Dict[str, float] = Field(
        default_factory=dict,
        description="Itemized approved amounts e.g. {'vehicle_repair': 3517.79, 'rental_car': 336.00, 'medical': 380.00}"
    )
    proposed_payout_amount: float = Field(description="Total cumulative settlement payout authorized across all lines")
    
    liability_warning: Optional[str] = Field(
        default=None,
        description="Alert for claims examiner regarding third-party injury/property exposures"
    )
    
    recommendation: Literal["approve", "partial_approve", "deny", "rework", "escalate_siu"]
    rework_target: Optional[Literal["extractor", "investigator"]] = None
    rework_instructions: Optional[str] = None
    
    justification: str = Field(description="Comprehensive technical explanation for the recommendation")

class HumanDecision(BaseModel):
    """Decision submitted by human claims adjuster at the approval gate."""
    approver_id: str
    action: Literal["approve", "reject", "rework"]
    final_payout_authorized: float
    comments: str
    timestamp: str
