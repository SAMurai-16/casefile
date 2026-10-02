import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from ..config import DATA_DIR

class ClaimStore:
    """Manages raw claim file loading from disk, including optional auxiliary documents."""
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir

    def list_available_claims(self) -> List[str]:
        """Finds all distinct claim IDs present in the data directory."""
        claims = set()
        prefix = "claim_"
        suffix = "_fnol.json"
        for f in self.data_dir.glob("claim_*_fnol.json"):
            if f.name.startswith(prefix) and f.name.endswith(suffix):
                claims.add(f.name[len(prefix):-len(suffix)])
        return sorted(list(claims))

    def save_claim_package(
        self,
        claim_num: str,
        fnol_raw: Dict[str, Any],
        estimate_raw: Dict[str, Any],
        policy_raw: Dict[str, Any],
        rental_raw: Optional[Dict[str, Any]] = None,
        medical_raw: Optional[Dict[str, Any]] = None,
        third_party_raw: Optional[Dict[str, Any]] = None,
    ) -> str:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        fnol_path = self.data_dir / f"claim_{claim_num}_fnol.json"
        est_path = self.data_dir / f"claim_{claim_num}_repair_estimate.json"
        pol_path = self.data_dir / f"claim_{claim_num}_policy.json"

        with open(fnol_path, "w", encoding="utf-8") as f:
            json.dump(fnol_raw, f, indent=2)
        with open(est_path, "w", encoding="utf-8") as f:
            json.dump(estimate_raw, f, indent=2)
        with open(pol_path, "w", encoding="utf-8") as f:
            json.dump(policy_raw, f, indent=2)

        if rental_raw:
            with open(self.data_dir / f"claim_{claim_num}_rental_receipt.json", "w", encoding="utf-8") as f:
                json.dump(rental_raw, f, indent=2)
        if medical_raw:
            with open(self.data_dir / f"claim_{claim_num}_medical_bill.json", "w", encoding="utf-8") as f:
                json.dump(medical_raw, f, indent=2)
        if third_party_raw:
            with open(self.data_dir / f"claim_{claim_num}_third_party.json", "w", encoding="utf-8") as f:
                json.dump(third_party_raw, f, indent=2)

        return claim_num

    def load_claim_package(
        self, claim_num: str
    ) -> Tuple[
        Dict[str, Any],
        Dict[str, Any],
        Dict[str, Any],
        Optional[Dict[str, Any]],
        Optional[Dict[str, Any]],
        Optional[Dict[str, Any]],
    ]:
        """
        Loads the claim package:
        - 3 Core Documents (Required): FNOL, Repair Estimate, Policy Record
        - 3 Auxiliary Documents (Optional): Rental Receipt, Medical Bill, Third-Party Claim
        
        Returns:
            (fnol_raw, estimate_raw, policy_raw, rental_raw, medical_raw, third_party_raw)
        """
        fnol_path = self.data_dir / f"claim_{claim_num}_fnol.json"
        est_path = self.data_dir / f"claim_{claim_num}_repair_estimate.json"
        pol_path = self.data_dir / f"claim_{claim_num}_policy.json"

        if not fnol_path.exists():
            raise FileNotFoundError(f"Missing required FNOL document at: {fnol_path}")
        if not est_path.exists():
            raise FileNotFoundError(f"Missing required Repair Estimate at: {est_path}")
        if not pol_path.exists():
            raise FileNotFoundError(f"Missing required Policy Record at: {pol_path}")

        with open(fnol_path, "r", encoding="utf-8") as f:
            fnol_data = json.load(f)
        with open(est_path, "r", encoding="utf-8") as f:
            est_data = json.load(f)
        with open(pol_path, "r", encoding="utf-8") as f:
            pol_data = json.load(f)

        # Check for optional auxiliary documents
        rental_path = self.data_dir / f"claim_{claim_num}_rental_receipt.json"
        medical_path = self.data_dir / f"claim_{claim_num}_medical_bill.json"
        third_party_path = self.data_dir / f"claim_{claim_num}_third_party.json"

        rental_data = None
        if rental_path.exists():
            with open(rental_path, "r", encoding="utf-8") as f:
                rental_data = json.load(f)

        medical_data = None
        if medical_path.exists():
            with open(medical_path, "r", encoding="utf-8") as f:
                medical_data = json.load(f)

        third_party_data = None
        if third_party_path.exists():
            with open(third_party_path, "r", encoding="utf-8") as f:
                third_party_data = json.load(f)

        return fnol_data, est_data, pol_data, rental_data, medical_data, third_party_data
