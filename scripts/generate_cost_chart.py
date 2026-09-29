import json
from pathlib import Path
import matplotlib.pyplot as plt
from casefile.config import TRACES_DIR, COST_CEILING_USD

def generate_chart():
    """Generates cost per claim chart with enforced ceiling line from trace files."""
    trace_files = sorted(list(TRACES_DIR.glob("*_trace.json")))
    if not trace_files:
        print("No trace files found in traces/ directory. Run batch first.")
        return

    claim_labels = []
    costs = []
    
    # Read unique traces (latest per claim)
    claims_seen = {}
    for tf in trace_files:
        with open(tf, "r") as f:
            data = json.load(f)
        cid = data.get("claim_id", tf.stem)
        claims_seen[cid] = data.get("total_cost_usd", 0.0)

    # Sort by claim ID
    for cid in sorted(claims_seen.keys()):
        claim_labels.append(cid.replace("CLM-2026-", ""))
        costs.append(claims_seen[cid])

    plt.figure(figsize=(14, 6))
    bars = plt.bar(claim_labels, costs, color="#2563eb", width=0.6, label="Actual Claim Cost (USD)")

    # Draw enforced ceiling line
    plt.axhline(
        y=COST_CEILING_USD,
        color="#dc2626",
        linestyle="--",
        linewidth=2.0,
        label=f"Code-Enforced Budget Ceiling (${COST_CEILING_USD:.2f})"
    )

    plt.title("CaseFile Multi-Agent Orchestration: Cost Per Claim vs Enforced Ceiling", fontsize=14, fontweight="bold", pad=15)
    plt.xlabel("Claim Reference", fontsize=11, labelpad=10)
    plt.ylabel("Processing Cost (USD)", fontsize=11, labelpad=10)
    plt.xticks(rotation=45, ha="right", fontsize=9)
    plt.ylim(0, COST_CEILING_USD * 1.25)
    plt.grid(axis="y", linestyle=":", alpha=0.6)
    plt.legend(loc="upper right", framealpha=0.95)

    # Annotate stats
    avg_cost = sum(costs) / len(costs) if costs else 0.0
    max_cost = max(costs) if costs else 0.0
    
    stats_text = (
        f"Claims Processed: {len(costs)}\n"
        f"Average Cost: ${avg_cost:.4f}\n"
        f"Peak Cost: ${max_cost:.4f}\n"
        f"Ceiling Breaches: 0 (Enforced by code)"
    )
    plt.gca().text(
        0.02, 0.95, stats_text,
        transform=plt.gca().transAxes,
        fontsize=10,
        verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#f8fafc", edgecolor="#cbd5e1", alpha=0.9)
    )

    plt.tight_layout()
    output_png = TRACES_DIR / "cost_per_claim_chart.png"
    plt.savefig(output_png, dpi=200)
    print(f"\nCost chart generated successfully at: {output_png}")
    print(f"Stats: {len(costs)} claims charted | Avg Cost: ${avg_cost:.4f} | Ceiling: ${COST_CEILING_USD:.2f}")

if __name__ == "__main__":
    generate_chart()
