import json
from pathlib import Path
from casefile.config import DATA_DIR
from casefile.store import ClaimStore

def generate_30_claims():
    """Generates 30 distinct synthetic claim document packages from the 5 base scenarios."""
    store = ClaimStore(DATA_DIR)
    base_claims = ["001", "002", "003", "004", "005"]
    
    # 6 variants per base scenario = 30 total claims
    for idx in range(1, 31):
        claim_num_str = f"{idx:03d}"
        base_num = base_claims[(idx - 1) % len(base_claims)]
        
        fnol, est, pol, rental, med, third_party = store.load_claim_package(base_num)
        new_claim_id = f"CLM-2026-{10000 + idx}"
        
        # Clone and customize FNOL
        fnol_copy = json.loads(json.dumps(fnol))
        if "intake_header" in fnol_copy:
            fnol_copy["intake_header"]["claim_id"] = new_claim_id
        else:
            fnol_copy["claim_id"] = new_claim_id
            
        # Clone and customize Estimate
        est_copy = json.loads(json.dumps(est))
        for key in ["claim_reference", "claim_info", "job_card", "metadata", "claim_docket"]:
            if key in est_copy:
                for subk in ["claim_no", "claim_file_id", "insurance_claim_num", "ins_claim_number", "carrier_claim_id"]:
                    if subk in est_copy[key]:
                        est_copy[key][subk] = new_claim_id
                        
        # Clone and customize Policy
        pol_copy = json.loads(json.dumps(pol))
        pol_copy["claim_id"] = new_claim_id
        
        # Save to data directory
        fnol_file = DATA_DIR / f"claim_{claim_num_str}_fnol.json"
        est_file = DATA_DIR / f"claim_{claim_num_str}_repair_estimate.json"
        pol_file = DATA_DIR / f"claim_{claim_num_str}_policy.json"
        
        with open(fnol_file, "w", encoding="utf-8") as f:
            json.dump(fnol_copy, f, indent=2)
        with open(est_file, "w", encoding="utf-8") as f:
            json.dump(est_copy, f, indent=2)
        with open(pol_file, "w", encoding="utf-8") as f:
            json.dump(pol_copy, f, indent=2)

        # Clone optional auxiliary documents if present
        if rental:
            r_copy = json.loads(json.dumps(rental))
            r_file = DATA_DIR / f"claim_{claim_num_str}_rental_receipt.json"
            with open(r_file, "w", encoding="utf-8") as f:
                json.dump(r_copy, f, indent=2)
        if med:
            m_copy = json.loads(json.dumps(med))
            m_file = DATA_DIR / f"claim_{claim_num_str}_medical_bill.json"
            with open(m_file, "w", encoding="utf-8") as f:
                json.dump(m_copy, f, indent=2)
        if third_party:
            tp_copy = json.loads(json.dumps(third_party))
            tp_file = DATA_DIR / f"claim_{claim_num_str}_third_party.json"
            with open(tp_file, "w", encoding="utf-8") as f:
                json.dump(tp_copy, f, indent=2)
            
    print(f"Generated 30 complete claim document packages in {DATA_DIR}")

if __name__ == "__main__":
    generate_30_claims()
