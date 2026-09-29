import json
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from ..config import BASE_DIR

class VehicleValuation(BaseModel):
    """Fair market vehicle valuation and repair-to-ACV ratio evaluation."""
    vin: Optional[str] = None
    vehicle_year: int
    vehicle_make: str
    vehicle_model: str
    odometer_mileage: int
    actual_cash_value: float = Field(description="Pre-accident Fair Market Value (ACV) in USD")
    repair_estimate_total: float
    repair_to_acv_ratio: float = Field(description="Repair Estimate divided by ACV (e.g. 0.895 = 89.5%)")
    is_total_loss_candidate: bool = Field(description="True if repair cost is >= 75% of vehicle value")
    state_total_loss_threshold: float = Field(default=0.75, description="Statutory threshold (typically 75% - 80%)")

class ValuationService:
    """
    Simulates industry-standard vehicle valuation lookups (CCC ONE / Kelley Blue Book).
    Provides pre-accident Actual Cash Value (ACV) and evaluates total-loss thresholds.
    """
    def __init__(self, data_path: Optional[Path] = None):
        self.data_path = data_path or (BASE_DIR / "data" / "vehicle_market_valuations.json")
        self._benchmarks: Dict[str, Any] = {}
        self._load_benchmarks()

    def _load_benchmarks(self):
        if self.data_path.exists():
            with open(self.data_path, "r", encoding="utf-8") as f:
                content = json.load(f)
                self._benchmarks = content.get("vehicles", {})

    def get_acv(self, year: int, make: str, model: str, mileage: int = 35000) -> float:
        """Computes mileage-adjusted Actual Cash Value (ACV)."""
        key = f"{make.strip().lower()}_{model.strip().lower()}"
        
        # Fuzzy match key
        matched_veh = None
        for k, data in self._benchmarks.items():
            if data["make"].lower() in make.lower() and (data["model"].lower() in model.lower() or model.lower() in data["model"].lower()):
                matched_veh = data
                break

        if not matched_veh:
            # Fallback baseline valuation formula: $28,000 base with 10% annual depreciation
            current_year = 2026
            age = max(1, current_year - year)
            base = 28000.0 * (0.88 ** age)
            mileage_adj = ((mileage - (12000 * age)) / 10000.0) * 800.0
            return max(3500.0, round(base - mileage_adj, 2))

        year_str = str(year)
        years_data = matched_veh.get("model_years", {})
        if year_str in years_data:
            base_acv = years_data[year_str]["fair_market_value_baseline"]
            dep_rate = years_data[year_str].get("depreciation_per_10k_miles", 750.0)
        else:
            # Pick closest year
            closest_yr = sorted(years_data.keys(), key=lambda y: abs(int(y) - year))[0]
            base_acv = years_data[closest_yr]["fair_market_value_baseline"]
            dep_rate = years_data[closest_yr].get("depreciation_per_10k_miles", 750.0)

        # Standard expected mileage is ~12,000 miles/year
        current_year = 2026
        age = max(1, current_year - year)
        expected_miles = 12000 * age
        excess_10k_blocks = (mileage - expected_miles) / 10000.0
        adjusted_acv = base_acv - (excess_10k_blocks * dep_rate)
        
        return max(3000.0, round(adjusted_acv, 2))

    def evaluate_claim_repair(
        self,
        repair_cost: float,
        year: int,
        make: str,
        model: str,
        mileage: int = 35000,
        vin: Optional[str] = None,
        threshold: float = 0.75
    ) -> VehicleValuation:
        """Evaluates repair cost against vehicle market value to calculate repair/ACV ratio."""
        acv = self.get_acv(year, make, model, mileage)
        ratio = round(repair_cost / acv, 4) if acv > 0 else 1.0
        is_total_loss = ratio >= threshold

        return VehicleValuation(
            vin=vin,
            vehicle_year=year,
            vehicle_make=make,
            vehicle_model=model,
            odometer_mileage=mileage,
            actual_cash_value=acv,
            repair_estimate_total=repair_cost,
            repair_to_acv_ratio=ratio,
            is_total_loss_candidate=is_total_loss,
            state_total_loss_threshold=threshold
        )
