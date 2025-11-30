from strands import tool
from strands.types.tools import ToolContext
from typing import Optional, List, Dict, Any
import datetime
import json
import uuid
from .models import ProductSpec, ZuoraApiType

# --- Mock Database ---
products_db = {}

def _generate_id(prefix: str) -> str:
    return f"{prefix}-{int(datetime.datetime.now().timestamp() * 1000) % 100000}"

# --- Tools ---

@tool
def preview_product_setup(spec: ProductSpec) -> str:
    """
    Analyzes the Product Specification and returns a validation summary.
    """
    issues = []
    prod = spec.product
    
    # Validation Logic
    for rp in prod.ratePlans:
        for charge in rp.charges:
            if charge.type == "Recurring" and not charge.billingPeriod:
                issues.append(f"Charge '{charge.name}': Recurring charge missing 'billingPeriod'.")
            
            if charge.model == "Prepaid with Drawdown":
                if (charge.autoTopupThreshold or 0) >= (charge.prepaidLoadAmount or 0):
                    issues.append(f"Charge '{charge.name}': Top-up threshold must be < load amount.")

    validation_msg = "✅ Validation Passed." if not issues else "❌ Validation Issues:\n" + "\n".join(issues)
    
    summary = f"Preview for '{prod.name}' (SKU: {prod.sku}):\n"
    summary += f"Structure: {len(prod.ratePlans)} Rate Plans.\n"
    for rp in prod.ratePlans:
        summary += f"- Plan '{rp.name}': {len(rp.charges)} charges.\n"
    
    return f"{summary}\n{validation_msg}"

@tool
def create_product_in_catalog(spec: ProductSpec) -> str:
    """
    Creates the Product in the Zuora Catalog.
    """
    prod = spec.product
    pid = _generate_id("P")
    products_db[pid] = prod.model_dump()
    return f"✅ Successfully created Product '{prod.name}' (ID: {pid})."

@tool
def check_sandbox_connection() -> str:
    return "✅ Connected to Zuora Sandbox."

@tool
def list_enabled_currencies() -> str:
    return "Enabled Currencies: USD, EUR, GBP, CAD."

@tool
def run_billing_simulation(product_sku: str, scenario: str) -> str:
    return f"Simulation '{scenario}' for {product_sku} completed successfully."


# ============ Payload State Keys ============
PAYLOADS_STATE_KEY = "zuora_api_payloads"


# ============ Payload Manipulation Tools ============

@tool(context=True)
def get_payloads(
    tool_context: ToolContext,
    api_type: Optional[str] = None
) -> str:
    """
    Retrieve the current Zuora API payloads from the conversation state.

    Args:
        api_type: Optional filter by API type (product, product_rate_plan, product_rate_plan_charge, product_rate_plan_charge_tier).
                  If not provided, returns all payloads.

    Returns:
        JSON representation of the payloads.
    """
    payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []

    if api_type:
        api_type_lower = api_type.lower()
        payloads = [p for p in payloads if p.get("zuora_api_type", "").lower() == api_type_lower]

    if not payloads:
        return f"No payloads found" + (f" for type '{api_type}'" if api_type else "")

    return json.dumps(payloads, indent=2)


@tool(context=True)
def update_payload(
    tool_context: ToolContext,
    api_type: str,
    field_path: str,
    new_value: Any,
    payload_index: int = 0
) -> str:
    """
    Update a specific field in a Zuora API payload.

    Args:
        api_type: The API type of the payload to update (product, product_rate_plan, etc.)
        field_path: Dot-notation path to the field (e.g., "name", "ratePlans.0.charges.0.price")
        new_value: The new value to set
        payload_index: Index of the payload if multiple exist for the same type (default: 0)

    Returns:
        Confirmation message with the updated payload.
    """
    payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []

    # Find matching payloads
    matching_indices = [
        i for i, p in enumerate(payloads)
        if p.get("zuora_api_type", "").lower() == api_type.lower()
    ]

    if not matching_indices:
        return f"Error: No payload found with type '{api_type}'"

    if payload_index >= len(matching_indices):
        return f"Error: payload_index {payload_index} is out of range. Found {len(matching_indices)} payloads of type '{api_type}'"

    target_idx = matching_indices[payload_index]
    payload = payloads[target_idx]["payload"]

    # Navigate to the field using dot notation
    parts = field_path.split(".")
    current = payload
    for part in parts[:-1]:
        if part.isdigit():
            current = current[int(part)]
        else:
            if part not in current:
                current[part] = {}
            current = current[part]

    # Set the value
    final_key = parts[-1]
    if final_key.isdigit():
        current[int(final_key)] = new_value
    else:
        current[final_key] = new_value

    # Update state
    tool_context.agent.state.set(PAYLOADS_STATE_KEY, payloads)

    return f"Successfully updated '{field_path}' to '{new_value}' in {api_type} payload.\n\nUpdated payload:\n{json.dumps(payloads[target_idx], indent=2)}"


@tool(context=True)
def create_payload(
    tool_context: ToolContext,
    api_type: str,
    payload_data: Dict[str, Any]
) -> str:
    """
    Create a new Zuora API payload and add it to the conversation state.

    Args:
        api_type: The API type for the new payload (product, product_rate_plan, product_rate_plan_charge, product_rate_plan_charge_tier)
        payload_data: The payload data as a dictionary

    Returns:
        Confirmation message with the created payload.
    """
    # Validate api_type
    valid_types = [t.value for t in ZuoraApiType]
    if api_type.lower() not in valid_types:
        return f"Error: Invalid api_type '{api_type}'. Valid types are: {', '.join(valid_types)}"

    payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []

    new_payload = {
        "payload": payload_data,
        "zuora_api_type": api_type.lower(),
        "payload_id": str(uuid.uuid4())[:8]
    }

    payloads.append(new_payload)
    tool_context.agent.state.set(PAYLOADS_STATE_KEY, payloads)

    return f"Successfully created new {api_type} payload:\n{json.dumps(new_payload, indent=2)}"


@tool(context=True)
def list_payload_structure(
    tool_context: ToolContext,
    api_type: str,
    payload_index: int = 0
) -> str:
    """
    List the structure and fields of a specific payload to help understand what can be modified.

    Args:
        api_type: The API type of the payload to inspect
        payload_index: Index if multiple payloads exist for the type (default: 0)

    Returns:
        A structured view of the payload's fields and their current values.
    """
    payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []

    matching = [p for p in payloads if p.get("zuora_api_type", "").lower() == api_type.lower()]

    if not matching:
        return f"No payload found with type '{api_type}'"

    if payload_index >= len(matching):
        return f"payload_index {payload_index} is out of range. Found {len(matching)} payloads."

    payload = matching[payload_index]["payload"]

    def describe_structure(obj, prefix=""):
        lines = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                path = f"{prefix}.{key}" if prefix else key
                if isinstance(value, (dict, list)):
                    lines.append(f"  {path}: {type(value).__name__}")
                    lines.extend(describe_structure(value, path))
                else:
                    lines.append(f"  {path}: {repr(value)}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                path = f"{prefix}.{i}"
                if isinstance(item, (dict, list)):
                    lines.append(f"  {path}: {type(item).__name__}")
                    lines.extend(describe_structure(item, path))
                else:
                    lines.append(f"  {path}: {repr(item)}")
        return lines

    structure = describe_structure(payload)
    return f"Structure of {api_type} payload (index {payload_index}):\n" + "\n".join(structure)