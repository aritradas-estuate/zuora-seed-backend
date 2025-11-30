from strands import tool
from strands.types.tools import ToolContext
from typing import Optional, List, Dict, Any, Literal
import datetime
import json
import uuid
from .models import ProductSpec, ZuoraApiType
from .zuora_client import get_zuora_client

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


# ============ Zuora API Tools (Real API Integration) ============

@tool
def connect_to_zuora() -> str:
    """
    Connect to Zuora and verify OAuth authentication.
    Call this first before any other Zuora operations.

    Returns:
        Connection status with environment info.
    """
    client = get_zuora_client()
    result = client.check_connection()

    if result.get("connected"):
        return f"✅ {result['message']}\nEnvironment: {result['environment']}\nBase URL: {result['base_url']}\nWrite operations enabled."
    else:
        return f"❌ Not connected: {result['message']}\nPlease check your ZUORA_CLIENT_ID and ZUORA_CLIENT_SECRET credentials."


@tool
def list_zuora_products(page_size: int = 20) -> str:
    """
    List all products from the Zuora Product Catalog.

    Args:
        page_size: Number of products to retrieve (default: 20)

    Returns:
        List of products with ID, Name, SKU, and effective dates.
    """
    client = get_zuora_client()
    result = client.list_all_products(page_size=page_size)

    if not result.get("success"):
        return f"❌ Error listing products: {result.get('error', 'Unknown error')}"

    products = result.get("data", {}).get("products", [])

    if not products:
        return "No products found in the catalog."

    output = f"Found {len(products)} product(s) in the catalog:\n\n"
    for p in products:
        output += f"• **{p.get('name', 'N/A')}**\n"
        output += f"  - ID: {p.get('id', 'N/A')}\n"
        output += f"  - SKU: {p.get('sku', 'N/A')}\n"
        output += f"  - Effective: {p.get('effectiveStartDate', 'N/A')} to {p.get('effectiveEndDate', 'N/A')}\n\n"

    return output


@tool
def get_zuora_product(
    identifier: str,
    identifier_type: Literal["id", "name", "sku"] = "name"
) -> str:
    """
    Get details of a specific product from Zuora.

    Args:
        identifier: The product ID, name, or SKU to search for
        identifier_type: Type of identifier - "id", "name", or "sku" (default: "name")

    Returns:
        Product details including ID, name, SKU, description, dates, and rate plans.
    """
    client = get_zuora_client()

    if identifier_type == "id":
        result = client.get_product(identifier)
    else:
        # Search by name or SKU
        result = client.list_all_products(page_size=100)
        if result.get("success"):
            products = result.get("data", {}).get("products", [])
            search_field = "name" if identifier_type == "name" else "sku"
            matching = [p for p in products if p.get(search_field, "").lower() == identifier.lower()]
            if matching:
                # Get full product details
                result = client.get_product(matching[0]["id"])
            else:
                return f"❌ No product found with {identifier_type} = '{identifier}'"

    if not result.get("success"):
        return f"❌ Error retrieving product: {result.get('error', 'Unknown error')}"

    product = result.get("data", {})

    output = f"**Product: {product.get('name', 'N/A')}**\n\n"
    output += f"• Product ID: {product.get('id', 'N/A')}\n"
    output += f"• SKU: {product.get('sku', 'N/A')}\n"
    output += f"• Description: {product.get('description', 'N/A')}\n"
    output += f"• Effective Start: {product.get('effectiveStartDate', 'N/A')}\n"
    output += f"• Effective End: {product.get('effectiveEndDate', 'N/A')}\n"

    rate_plans = product.get("productRatePlans", [])
    if rate_plans:
        output += f"\n**Rate Plans ({len(rate_plans)}):**\n"
        for rp in rate_plans:
            output += f"\n  📋 **{rp.get('name', 'N/A')}** (ID: {rp.get('id', 'N/A')})\n"
            output += f"     Description: {rp.get('description', 'N/A')}\n"

            charges = rp.get("productRatePlanCharges", [])
            if charges:
                output += f"     Charges ({len(charges)}):\n"
                for ch in charges:
                    output += f"       • {ch.get('name', 'N/A')}\n"
                    output += f"         Type: {ch.get('type', 'N/A')}, Model: {ch.get('model', 'N/A')}\n"
                    pricing = ch.get("pricing", [])
                    if pricing:
                        price_info = pricing[0]
                        output += f"         Price: {price_info.get('currency', '')} {price_info.get('price', 'N/A')}\n"

    output += "\nWould you like to view more details or update any attribute?"
    return output


@tool
def get_zuora_rate_plan_details(product_id: str, rate_plan_name: Optional[str] = None) -> str:
    """
    Get detailed rate plan information for a product.

    Args:
        product_id: The product ID
        rate_plan_name: Optional - specific rate plan name to filter

    Returns:
        Detailed rate plan information including charges.
    """
    client = get_zuora_client()
    result = client.get_product(product_id)

    if not result.get("success"):
        return f"❌ Error retrieving product: {result.get('error', 'Unknown error')}"

    product = result.get("data", {})
    rate_plans = product.get("productRatePlans", [])

    if rate_plan_name:
        rate_plans = [rp for rp in rate_plans if rp.get("name", "").lower() == rate_plan_name.lower()]
        if not rate_plans:
            return f"❌ No rate plan found with name '{rate_plan_name}'"

    output = f"**Rate Plans for {product.get('name', 'N/A')}:**\n\n"

    for rp in rate_plans:
        output += f"📋 **{rp.get('name', 'N/A')}**\n"
        output += f"   ID: {rp.get('id', 'N/A')}\n"
        output += f"   Description: {rp.get('description', 'N/A')}\n"
        output += f"   Effective Start: {rp.get('effectiveStartDate', 'N/A')}\n"
        output += f"   Effective End: {rp.get('effectiveEndDate', 'N/A')}\n"

        charges = rp.get("productRatePlanCharges", [])
        if charges:
            output += f"\n   **Charges ({len(charges)}):**\n"
            for ch in charges:
                output += f"\n   💰 {ch.get('name', 'N/A')} (ID: {ch.get('id', 'N/A')})\n"
                output += f"      Type: {ch.get('type', 'N/A')}\n"
                output += f"      Model: {ch.get('model', 'N/A')}\n"
                output += f"      Billing Period: {ch.get('billingPeriod', 'N/A')}\n"
                output += f"      Billing Timing: {ch.get('billingTiming', 'N/A')}\n"
                output += f"      Trigger Event: {ch.get('triggerEvent', 'N/A')}\n"

                pricing = ch.get("pricing", [])
                if pricing:
                    output += f"      Pricing:\n"
                    for price in pricing:
                        output += f"        - {price.get('currency', 'N/A')}: {price.get('price', 'N/A')}\n"

        output += "\n"

    return output


@tool
def update_zuora_product(
    product_id: str,
    attribute: Literal["name", "sku", "description", "effectiveStartDate", "effectiveEndDate"],
    new_value: str
) -> str:
    """
    Update a product attribute in Zuora.

    ⚠️ IMPORTANT: Updates only affect NEW subscriptions. Existing subscriptions keep the old values.

    Args:
        product_id: The product ID to update
        attribute: The attribute to update (name, sku, description, effectiveStartDate, effectiveEndDate)
        new_value: The new value for the attribute

    Returns:
        Confirmation of the update with warning about subscription impact.
    """
    client = get_zuora_client()

    # First get current product to show what's changing
    current = client.get_product(product_id)
    if not current.get("success"):
        return f"❌ Error retrieving product: {current.get('error', 'Unknown error')}"

    product = current.get("data", {})
    old_value = product.get(attribute, "N/A")

    # Perform update
    result = client.update_product(product_id, {attribute: new_value})

    if not result.get("success"):
        return f"❌ Error updating product: {result.get('error', 'Unknown error')}"

    return f"""✅ Successfully updated product '{product.get('name', 'N/A')}'

**Change:**
• {attribute}: '{old_value}' → '{new_value}'

⚠️ **Please note:** This update will be effective only for NEW subscriptions created after this change. Existing subscriptions will continue to use the previous {attribute}.

Would you like to update another attribute?"""


@tool
def update_zuora_rate_plan(
    rate_plan_id: str,
    attribute: Literal["name", "description", "effectiveStartDate", "effectiveEndDate"],
    new_value: str
) -> str:
    """
    Update a rate plan attribute in Zuora.

    ⚠️ IMPORTANT: Updates only affect NEW subscriptions. Existing subscriptions keep the old values.
    ⚠️ Note: Rate plan end date must be within the product's effective date range.

    Args:
        rate_plan_id: The rate plan ID to update
        attribute: The attribute to update (name, description, effectiveStartDate, effectiveEndDate)
        new_value: The new value for the attribute

    Returns:
        Confirmation of the update with warning about subscription impact.
    """
    client = get_zuora_client()

    # Get current rate plan
    current = client.get_rate_plan(rate_plan_id)
    if not current.get("success"):
        return f"❌ Error retrieving rate plan: {current.get('error', 'Unknown error')}"

    rate_plan = current.get("data", {})
    old_value = rate_plan.get(attribute, "N/A")

    # Perform update
    result = client.update_rate_plan(rate_plan_id, {attribute: new_value})

    if not result.get("success"):
        return f"❌ Error updating rate plan: {result.get('error', 'Unknown error')}"

    return f"""✅ Successfully updated rate plan '{rate_plan.get('name', 'N/A')}'

**Change:**
• {attribute}: '{old_value}' → '{new_value}'

⚠️ **Please note:** This update will be effective only for NEW subscriptions created after this change. Existing subscriptions will continue to use the previous {attribute}.

Would you like to update another attribute?"""


@tool
def update_zuora_charge(
    charge_id: str,
    attribute: str,
    new_value: Any
) -> str:
    """
    Update a charge attribute in Zuora.

    ⚠️ IMPORTANT: Updates only affect NEW subscriptions. Existing subscriptions keep the old values.
    ⚠️ RESTRICTION: Charge Model and Charge Type CANNOT be changed if used in existing subscriptions.

    Args:
        charge_id: The charge ID to update
        attribute: The attribute to update (name, description, price, billingPeriod, triggerEvent, etc.)
        new_value: The new value for the attribute

    Returns:
        Confirmation of the update with warning about subscription impact.
    """
    client = get_zuora_client()

    # Check for restricted attributes
    restricted_attrs = ["model", "type", "chargeModel", "chargeType"]
    if attribute.lower() in [a.lower() for a in restricted_attrs]:
        return f"""⚠️ **Cannot update {attribute}**

Charge Model and Charge Type cannot be changed if this charge is used in any existing subscriptions, as it impacts active billing calculations.

👉 **Alternative:** Create a new Rate Plan Charge with the desired model and retire this old charge at a future date.

Would you like me to help create a new charge instead?"""

    # Get current charge
    current = client.get_charge(charge_id)
    if not current.get("success"):
        return f"❌ Error retrieving charge: {current.get('error', 'Unknown error')}"

    charge = current.get("data", {})
    old_value = charge.get(attribute, "N/A")

    # Perform update
    result = client.update_charge(charge_id, {attribute: new_value})

    if not result.get("success"):
        return f"❌ Error updating charge: {result.get('error', 'Unknown error')}"

    return f"""✅ Successfully updated charge '{charge.get('name', 'N/A')}'

**Change:**
• {attribute}: '{old_value}' → '{new_value}'

⚠️ **Please note:** This update will be effective only for NEW subscriptions created after this change. Existing subscriptions will continue to use the previous {attribute}.

Would you like to update another attribute?"""