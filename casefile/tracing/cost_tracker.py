from typing import Dict, Any, Tuple
from ..config import PRICING_TABLE, DEFAULT_MODEL

def calculate_call_cost(
    usage_metadata: Dict[str, Any],
    model_name: str = DEFAULT_MODEL
) -> Tuple[int, float]:
    """
    Computes token counts and dollar cost from LLM response usage metadata.
    
    Returns:
        (total_tokens, cost_in_usd)
    """
    if not usage_metadata:
        return 0, 0.0
    
    input_tokens = usage_metadata.get("input_tokens", 0)
    output_tokens = usage_metadata.get("output_tokens", 0)
    total_tokens = usage_metadata.get("total_tokens", input_tokens + output_tokens)
    
    rates = PRICING_TABLE.get(model_name, PRICING_TABLE.get("gemini-2.0-flash"))
    input_rate = rates["input"] / 1_000_000.0
    output_rate = rates["output"] / 1_000_000.0
    
    cost = (input_tokens * input_rate) + (output_tokens * output_rate)
    return total_tokens, round(cost, 6)
