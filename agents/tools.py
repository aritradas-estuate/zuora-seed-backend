from strands import tool
from strands.types.tools import ToolContext
from typing import Optional, List, Dict, Any, Literal, Tuple
import datetime
import json
import logging
import uuid

import jellyfish

logger = logging.getLogger(__name__)
from .models import ProductSpec, ZuoraApiType
from .zuora_client import get_zuora_client
from .observability import trace_function
from .validation_schemas import (
    validate_payload,
    format_validation_questions,
    generate_placeholder_payload,
    format_placeholder_warning,
)
from .validation_utils import (
    validate_date_format as _validate_date_format_tuple,
    validate_date_range as _validate_date_range_tuple,
    validate_zuora_id as _validate_zuora_id_tuple,
    validate_sku_format as _validate_sku_format_tuple,
    format_error_message,
    is_object_reference,
    validate_name_length,
    validate_product_name_unique,
    validate_rate_plan_name_unique,
    validate_charge_name_unique,
)


def _find_existing_key(obj: Dict[str, Any], key: str) -> Optional[str]:
    """
    Find an existing key in a dict that matches case-insensitively.

    Zuora API uses PascalCase (e.g., BillingPeriod). This function finds the
    existing key even if the input uses snake_case (billing_period) or other variations.

    Args:
        obj: Dictionary to search
        key: Key to find (any casing)

    Returns:
        The actual existing key if found, None otherwise
    """
    if key in obj:
        return key  # Exact match

    # Normalize: lowercase and remove underscores
    key_normalized = key.lower().replace("_", "")

    for existing_key in obj.keys():
        existing_normalized = existing_key.lower().replace("_", "")
        if existing_normalized == key_normalized:
            return existing_key

    return None


# Field name mapping for Zuora CRUD API (lowercase -> PascalCase)
# The /v1/object/* endpoints require PascalCase field names
CRUD_FIELD_MAPPING = {
    "name": "Name",
    "sku": "SKU",
    "description": "Description",
    "effectivestartdate": "EffectiveStartDate",
    "effectiveenddate": "EffectiveEndDate",
}


def _to_crud_field_name(field: str) -> str:
    """
    Convert field name to PascalCase for Zuora CRUD API.

    The Zuora /v1/object/* endpoints require PascalCase field names
    (e.g., 'Name' not 'name', 'SKU' not 'sku').

    Args:
        field: Field name in any casing

    Returns:
        PascalCase field name for Zuora CRUD API
    """
    return CRUD_FIELD_MAPPING.get(field.lower(), field)


def _find_payload_by_name(
    matching: List[Tuple[int, Dict[str, Any]]], name: str
) -> Tuple[Optional[Tuple[int, Dict[str, Any]]], List[str]]:
    """
    Find a payload by name using case-insensitive substring matching.

    Args:
        matching: List of (index, payload) tuples to search
        name: Name to search for (case-insensitive substring match)

    Returns:
        Tuple of:
        - (index, payload) if exactly one match found, None otherwise
        - List of all matching names (for error messages)
    """
    name_lower = name.lower()
    matches = []

    for idx, p in matching:
        payload_name = p.get("payload", {}).get("Name") or p.get("payload", {}).get(
            "name", ""
        )
        if payload_name and name_lower in payload_name.lower():
            matches.append((idx, p, payload_name))

    if len(matches) == 1:
        idx, p, _ = matches[0]
        return ((idx, p), [m[2] for m in matches])
    else:
        return (None, [m[2] for m in matches])


# Wrapper functions that return just booleans for backward compatibility
def validate_date_format(date_str: str) -> bool:
    """Validate date is in YYYY-MM-DD format. Returns True if valid."""
    result, _ = _validate_date_format_tuple(date_str)
    return result


def validate_date_range(start_date: str, end_date: str) -> bool:
    """Validate end_date is after start_date. Returns True if valid."""
    result, _ = _validate_date_range_tuple(start_date, end_date)
    return result


def validate_zuora_id(id_str: str) -> bool:
    """Validate Zuora ID or object reference format. Returns True if valid."""
    result, _ = _validate_zuora_id_tuple(id_str)
    return result


def validate_sku_format(sku: str) -> bool:
    """Validate SKU format. Returns True if valid."""
    result, _ = _validate_sku_format_tuple(sku)
    return result


# Note: REQUIRED_FIELDS schema and validation functions moved to:
# - validation_schemas.py (schema and validation logic)
# - validation_utils.py (common validation utilities)
# All functions are imported at the top of this file


# ============ Object Reference Helpers ============


def _count_payloads_by_type(payloads: List[Dict[str, Any]], api_type: str) -> int:
    """Count the number of payloads of a specific type."""
    return len([p for p in payloads if p.get("zuora_api_type") == api_type])


def _get_product_object_reference(
    payloads: List[Dict[str, Any]], product_index: Optional[int] = None
) -> Optional[str]:
    """
    Generate a product object reference for batch execution.

    Args:
        payloads: Current list of payloads in state
        product_index: Specific product index to reference. If None, auto-determines based on count.

    Returns:
        Object reference string like "@{Product[0].Id}" or None if no products exist
    """
    product_count = _count_payloads_by_type(payloads, "product_create")

    if product_count == 0:
        return None

    if product_index is not None:
        if product_index < product_count:
            return f"@{{Product[{product_index}].Id}}"
        else:
            return None

    # Auto-determine: if only one product, use index 0
    if product_count == 1:
        return "@{Product[0].Id}"

    # Multiple products - cannot auto-determine, return None to trigger placeholder
    return None


def _get_rate_plan_object_reference(
    payloads: List[Dict[str, Any]], rate_plan_index: Optional[int] = None
) -> Optional[str]:
    """
    Generate a rate plan object reference for batch execution.

    Args:
        payloads: Current list of payloads in state
        rate_plan_index: Specific rate plan index to reference. If None, returns the next sequential index.

    Returns:
        Object reference string like "@{ProductRatePlan[0].Id}" or None if no rate plans exist
    """
    rate_plan_count = _count_payloads_by_type(payloads, "rate_plan_create")

    if rate_plan_index is not None:
        # Use specific index if provided
        return f"@{{ProductRatePlan[{rate_plan_index}].Id}}"

    if rate_plan_count == 0:
        return None

    # Return reference to the most recently created rate plan
    # (This is the common case: create rate plan, then create charge for it)
    return f"@{{ProductRatePlan[{rate_plan_count - 1}].Id}}"


# ============ Utility Tools ============


@tool
def get_current_date() -> str:
    """Get the current date in YYYY-MM-DD format. Useful for setting effective dates."""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    return f"Today's date is: {today}"


@tool
def get_zuora_environment_info() -> str:
    """Get information about the connected Zuora environment including available
    charge models, billing periods, currencies, and billing rules.

    Call this to understand what options are available in the current Zuora tenant
    before generating payloads.
    """
    from .zuora_settings import get_environment_summary

    # Check connection first
    client = get_zuora_client()
    connection = client.check_connection()

    if not connection.get("connected"):
        return f"Not connected to Zuora: {connection.get('message')}"

    env_info = f"**Connected to:** {connection.get('environment', 'unknown').upper()}\n"
    env_info += f"**Base URL:** {connection.get('base_url', 'N/A')}\n\n"
    env_info += get_environment_summary()

    return env_info


# ============ Payload State Keys ============
PAYLOADS_STATE_KEY = "zuora_api_payloads"


# ============ Payload Manipulation Tools ============


@tool(context=True)
def get_payloads(tool_context: ToolContext, api_type: Optional[str] = None) -> str:
    """Retrieve Zuora API payloads from state. Filter by api_type if provided."""
    payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []

    if api_type:
        api_type_lower = api_type.lower()
        payloads = [
            p for p in payloads if p.get("zuora_api_type", "").lower() == api_type_lower
        ]

    if not payloads:
        return f"No payloads found" + (f" for type '{api_type}'" if api_type else "")

    # Build human-readable table summary
    output = f"**Payloads ({len(payloads)} total):**\n\n"
    output += "| # | Type | Name | ID | Status |\n"
    output += "|---|------|------|----|---------|\n"

    for i, p in enumerate(payloads, 1):
        # Make type human-friendly (e.g., "charge_create" -> "Charge")
        raw_type = p.get("zuora_api_type", "unknown")
        friendly_type = (
            raw_type.replace("_create", "")
            .replace("_update", "")
            .replace("_", " ")
            .title()
        )

        # Get name from payload
        payload_data = p.get("payload", {})
        name = payload_data.get("Name", payload_data.get("name", "unnamed"))

        # Get payload ID
        pid = p.get("payload_id", "?")

        # Determine status
        placeholders = p.get("_placeholders", [])
        if placeholders:
            # Show first 2 placeholders, then "etc."
            placeholder_display = ", ".join(placeholders[:2])
            if len(placeholders) > 2:
                placeholder_display += f" (+{len(placeholders) - 2} more)"
            status = f"Needs: {placeholder_display}"
        else:
            status = "Ready"

        output += f"| {i} | {friendly_type} | {name} | {pid} | {status} |\n"

    # Summary of items needing attention
    payloads_with_placeholders = [p for p in payloads if p.get("_placeholders")]
    if payloads_with_placeholders:
        output += f"\n{len(payloads_with_placeholders)} payload(s) need more details before execution."
    else:
        output += "\nAll payloads ready for execution."

    return output


@tool(context=True)
def update_payload(
    tool_context: ToolContext,
    api_type: str,
    field_path: str,
    new_value: Any,
    payload_id: Optional[str] = None,
    payload_name: Optional[str] = None,
    payload_index: Optional[int] = None,
) -> str:
    """Update field in payload. Identify by payload_id, payload_name, or payload_index.

    Priority order: payload_id > payload_name > payload_index

    Args:
        api_type: Payload type (e.g., 'charge_create', 'product_create')
        field_path: Dot notation path to field (e.g., 'includedUnits', 'pricing.0.price')
        new_value: New value to set
        payload_id: Unique payload ID (from create response)
        payload_name: Name of the payload (case-insensitive substring match, e.g., 'API Calls' matches 'API Calls Usage')
        payload_index: Index among payloads of same type (0=first, 1=second)
    """
    payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []

    # Find matching payloads by api_type
    matching = [
        (i, p)
        for i, p in enumerate(payloads)
        if p.get("zuora_api_type", "").lower() == api_type.lower()
    ]

    if not matching:
        available_types = set(p.get("zuora_api_type", "") for p in payloads)
        return f"<p>❌ <strong>Error:</strong> No payload found with type '<code>{api_type}</code>'.</p><p>Available types: {', '.join(available_types) if available_types else 'none'}</p>"

    # Determine which payload to update
    target_idx = None
    target_entry = None

    if payload_id:
        # Find by payload_id (preferred)
        for idx, p in matching:
            if p.get("payload_id") == payload_id:
                target_idx = idx
                target_entry = p
                break

        if target_entry is None:
            # payload_id not found - provide helpful error
            error_msg = f"<p>❌ <strong>Error:</strong> No <code>{api_type}</code> payload found with payload_id '<code>{payload_id}</code>'.</p>"
            error_msg += f"<p><strong>Available {api_type} payloads:</strong></p><ul>"
            for _, p in matching:
                pid = p.get("payload_id", "?")
                name = p.get("payload", {}).get("name", "unnamed")
                error_msg += f"<li><code>payload_id='{pid}'</code> (name: {name})</li>"
            error_msg += "</ul>"
            error_msg += f"<p><em>Try:</em> <code>update_payload(api_type='{api_type}', payload_id='CORRECT_ID', ...)</code></p>"
            return error_msg

    elif payload_name:
        # Find by name (case-insensitive substring match)
        result, matched_names = _find_payload_by_name(matching, payload_name)

        if result:
            target_idx, target_entry = result
            matched_name = target_entry.get("payload", {}).get(
                "Name"
            ) or target_entry.get("payload", {}).get("name", "")
            # Log only when match is not exact
            if matched_name.lower() != payload_name.lower():
                logger.info(f"Fuzzy name match: '{payload_name}' -> '{matched_name}'")
        elif len(matched_names) > 1:
            # Multiple payloads match - ambiguous, fail with helpful error
            error_msg = f"<p>❌ <strong>Error:</strong> Multiple <code>{api_type}</code> payloads match '<code>{payload_name}</code>'.</p>"
            error_msg += f"<p><strong>Matching payloads:</strong></p><ul>"
            for name in matched_names:
                error_msg += f"<li><strong>{name}</strong></li>"
            error_msg += "</ul>"
            error_msg += (
                f"<p><em>Be more specific:</em> Use a more unique part of the name.</p>"
            )
            return error_msg
        else:
            # No match found
            error_msg = f"<p>❌ <strong>Error:</strong> No <code>{api_type}</code> payload found with name containing '<code>{payload_name}</code>'.</p>"
            error_msg += f"<p><strong>Available {api_type} payloads:</strong></p><ul>"
            for _, p in matching:
                pname = p.get("payload", {}).get("Name") or p.get("payload", {}).get(
                    "name", "unnamed"
                )
                error_msg += f"<li><strong>{pname}</strong></li>"
            error_msg += "</ul>"
            return error_msg

    elif payload_index is not None:
        # Find by index
        if payload_index >= len(matching):
            # Index out of range - provide helpful error
            error_msg = f"<p>❌ <strong>Error:</strong> payload_index {payload_index} is out of range.</p>"
            error_msg += f"<p><strong>Found {len(matching)} {api_type} payload(s):</strong></p><ul>"
            for i, (_, p) in enumerate(matching):
                pid = p.get("payload_id", "?")
                name = p.get("payload", {}).get("name", "unnamed")
                error_msg += f"<li>Index {i}: <code>payload_id='{pid}'</code> (name: {name})</li>"
            error_msg += "</ul>"
            error_msg += f"<p><em>Try:</em> <code>update_payload(api_type='{api_type}', payload_index={len(matching) - 1}, ...)</code></p>"
            return error_msg

        target_idx, target_entry = matching[payload_index]

    else:
        # Neither specified - auto-select if only one, else require specification
        if len(matching) == 1:
            # Only one payload, use it automatically
            target_idx, target_entry = matching[0]
        else:
            # Multiple payloads - need to specify which one
            error_msg = f"<p>❌ <strong>Error:</strong> Multiple <code>{api_type}</code> payloads found. Please specify which one to update.</p>"
            error_msg += f"<p><strong>Found {len(matching)} {api_type} payload(s):</strong></p><ul>"
            for i, (_, p) in enumerate(matching):
                pname = p.get("payload", {}).get("Name") or p.get("payload", {}).get(
                    "name", "unnamed"
                )
                error_msg += f"<li><strong>{pname}</strong> (index: {i})</li>"
            error_msg += "</ul>"
            error_msg += f"<p><strong>Use payload_name (recommended):</strong></p>"
            first_name = matching[0][1].get("payload", {}).get("Name") or matching[0][
                1
            ].get("payload", {}).get("name", "NAME")
            error_msg += f"<pre><code>update_payload(api_type='{api_type}', payload_name='{first_name}', field_path='{field_path}', new_value={repr(new_value)})</code></pre>"
            return error_msg

    payload_entry = target_entry
    payload = payload_entry["payload"]

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

    # Perform basic validation on the new value
    final_key = parts[-1]

    # Date validation
    if "date" in final_key.lower() and isinstance(new_value, str):
        if not validate_date_format(new_value):
            return format_error_message(
                "Invalid date format",
                f"'{final_key}' must be in YYYY-MM-DD format, got: {new_value}",
            )

    # ID validation
    if "id" in final_key.lower() and isinstance(new_value, str) and len(new_value) > 5:
        if not validate_zuora_id(new_value):
            return format_error_message(
                "Invalid ID format",
                f"'{final_key}' appears to be an invalid Zuora ID: {new_value}",
            )

    # Ensure arrays/objects aren't stored as strings (common when LLM passes JSON as string)
    if isinstance(new_value, str):
        stripped = new_value.strip()
        if (stripped.startswith("[") and stripped.endswith("]")) or (
            stripped.startswith("{") and stripped.endswith("}")
        ):
            try:
                new_value = json.loads(new_value)
                logger.debug(f"Parsed JSON string to object for field '{final_key}'")
            except json.JSONDecodeError:
                pass  # Keep as string if not valid JSON

    # Set the value - use existing key if one matches (case-insensitive)
    # This ensures we update BillingPeriod when field_path is "billing_period"
    if final_key.isdigit():
        current[int(final_key)] = new_value
        actual_key = final_key
    else:
        existing_key = _find_existing_key(current, final_key)
        if existing_key and existing_key != final_key:
            logger.info(f"Normalized field key: '{final_key}' -> '{existing_key}'")
        actual_key = existing_key if existing_key else final_key
        current[actual_key] = new_value

    # Remove from placeholder list if this field was a placeholder
    if "_placeholders" in payload_entry:
        placeholders = payload_entry["_placeholders"]

        # Build set of normalized keys to match against (field_path, final_key, actual_key)
        keys_to_match = {
            field_path.lower().replace("_", ""),
            final_key.lower().replace("_", ""),
            actual_key.lower().replace("_", ""),
        }

        # Find and remove matching placeholder
        for ph in list(placeholders):
            ph_normalized = ph.lower().replace("_", "")
            if ph_normalized in keys_to_match:
                placeholders.remove(ph)
                break

        # Remove the _placeholders key if empty
        if not placeholders:
            del payload_entry["_placeholders"]

    # Update state
    tool_context.agent.state.set(PAYLOADS_STATE_KEY, payloads)

    # Get human-friendly type and name for response
    friendly_type = (
        api_type.replace("_create", "").replace("_update", "").replace("_", " ")
    )
    payload_name = payload.get("Name", payload.get("name", "unnamed"))

    # Build concise response (no JSON) - show the actual key used, not the input field_path
    response = f'Updated {actual_key} to "{new_value}" in {friendly_type} "{payload_name}".\n\n'

    # Show remaining placeholders if any
    if payload_entry.get("_placeholders"):
        remaining = payload_entry["_placeholders"]
        response += f"Still needs: {', '.join(remaining)}"
    else:
        response += "All fields complete - ready to execute."

    return response


@tool(context=True)
def create_payload(
    tool_context: ToolContext,
    api_type: str,
    payload_data: Dict[str, Any],
    defaults_applied: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Create new Zuora payload with validation. Generates placeholders for missing required fields.

    Args:
        tool_context: Tool context for accessing agent state
        api_type: Type of Zuora API payload (e.g., 'product_create', 'charge_create')
        payload_data: Dictionary of payload fields and values
        defaults_applied: Optional list of defaults that were applied, each with 'field' and 'value' keys.
                         This is used internally by create_product/create_rate_plan/create_charge.

    Returns:
        HTML-formatted string with creation result and any defaults that were applied
    """
    from .html_formatter import (
        generate_reference_documentation,
        format_payload_with_references,
        format_defaults_applied_html,
    )
    from .validation_schemas import (
        generate_placeholder_payload,
        format_placeholder_warning,
    )

    # Validate api_type
    valid_types = [t.value for t in ZuoraApiType]
    if api_type.lower() not in valid_types:
        return f"<p>Error: Invalid api_type '{api_type}'. Valid types are: {', '.join(valid_types)}</p>"

    # Validate required fields
    is_valid, missing_fields = validate_payload(api_type, payload_data)

    # Prepare the payload (with or without placeholders)
    if not is_valid:
        # Generate payload WITH placeholders for missing fields
        complete_payload, placeholder_list = generate_placeholder_payload(
            api_type, payload_data, missing_fields
        )
    else:
        # All required fields present
        complete_payload = payload_data
        placeholder_list = []

    # Create the payload entry
    payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []

    new_payload = {
        "payload": complete_payload,
        "zuora_api_type": api_type.lower(),
        "payload_id": str(uuid.uuid4())[:8],
    }

    # Add placeholder tracking if present
    if placeholder_list:
        new_payload["_placeholders"] = placeholder_list

    payloads.append(new_payload)
    tool_context.agent.state.set(PAYLOADS_STATE_KEY, payloads)

    # Count payloads of same type for index info
    same_type_count = len(
        [p for p in payloads if p.get("zuora_api_type", "").lower() == api_type.lower()]
    )
    current_index = same_type_count - 1  # 0-based index of this payload

    # Generate output
    if placeholder_list:
        # Return warning about placeholders (with index info)
        # Include defaults table if any defaults were applied
        output = ""
        if defaults_applied:
            output += format_defaults_applied_html(defaults_applied)
        output += format_placeholder_warning(
            api_type, placeholder_list, new_payload, current_index, same_type_count
        )
        return output
    else:
        # Generate concise success output (no JSON)
        friendly_type = (
            api_type.replace("_create", "")
            .replace("_update", "")
            .replace("_", " ")
            .title()
        )
        payload_name = complete_payload.get(
            "Name", complete_payload.get("name", "unnamed")
        )

        output = f'Created <strong>{friendly_type}</strong>: "{payload_name}"<br><br>'

        # Add defaults table if any defaults were applied
        if defaults_applied:
            output += format_defaults_applied_html(defaults_applied)

        output += "All required fields are set.<br>"

        return output


@tool(context=True)
def list_payload_structure(
    tool_context: ToolContext, api_type: str, payload_index: int = 0
) -> str:
    """List payload structure and fields."""
    payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []

    matching = [
        p for p in payloads if p.get("zuora_api_type", "").lower() == api_type.lower()
    ]

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
    return f"Structure of {api_type} payload (index {payload_index}):\n" + "\n".join(
        structure
    )


# ============ Zuora API Tools (Real API Integration) ============


@tool
def connect_to_zuora() -> str:
    """Connect to Zuora and verify OAuth. Returns connection status and environment."""
    client = get_zuora_client()
    result = client.check_connection()

    if result.get("connected"):
        return f"✅ {result['message']}\nEnvironment: {result['environment']}\nBase URL: {result['base_url']}\nWrite operations enabled."
    else:
        return f"❌ Not connected: {result['message']}\nPlease check your ZUORA_CLIENT_ID and ZUORA_CLIENT_SECRET credentials."


@tool
def list_zuora_products() -> str:
    """List the last 20 products from Zuora Catalog (sorted by most recently updated)."""
    client = get_zuora_client()
    result = client.list_all_products(page_size=20)

    if not result.get("success"):
        return f"❌ Error listing products: {result.get('error', 'Unknown error')}"

    products = result.get("data", {}).get("products", [])

    if not products:
        return "No products found in the catalog."

    output = f"**Last {len(products)} product(s) in the catalog** (most recently updated first):\n\n"
    for p in products:
        output += f"• **{p.get('name', 'N/A')}**\n"
        output += f"  - ID: {p.get('id', 'N/A')}\n"
        output += f"  - SKU: {p.get('sku', 'N/A')}\n"
        output += f"  - Effective: {p.get('effectiveStartDate', 'N/A')} to {p.get('effectiveEndDate', 'N/A')}\n\n"

    return output


def _find_best_product_match(
    products: List[Dict[str, Any]], search_term: str, search_field: str
) -> Dict[str, Any]:
    """
    Find best matching product using Damerau-Levenshtein distance.

    Args:
        products: List of product dictionaries
        search_term: The term to search for
        search_field: Field to search in ('name' or 'sku')

    Returns:
        Dict with 'type' ('exact', 'fuzzy', or 'none'), 'matches' list,
        and 'distances' dict mapping product IDs to their distances
    """
    search_lower = search_term.lower()

    # First check for exact match (case-insensitive)
    for p in products:
        if p.get(search_field, "").lower() == search_lower:
            return {"type": "exact", "matches": [p], "distances": {p.get("id"): 0}}

    # No exact match - find closest using Damerau-Levenshtein distance
    matches_with_distance: List[Tuple[Dict[str, Any], int]] = []
    for p in products:
        field_value = p.get(search_field, "")
        if not field_value:
            continue
        distance = jellyfish.damerau_levenshtein_distance(
            search_lower, field_value.lower()
        )
        matches_with_distance.append((p, distance))

    if not matches_with_distance:
        return {"type": "none", "matches": [], "distances": {}}

    # Sort by distance (ascending)
    matches_with_distance.sort(key=lambda x: x[1])

    # Get best distance
    best_distance = matches_with_distance[0][1]

    # Get all products with the best distance, plus close alternatives (within +1)
    close_matches = [
        (m, d) for m, d in matches_with_distance if d <= best_distance + 1
    ][:3]

    return {
        "type": "fuzzy",
        "matches": [m for m, d in close_matches],
        "distances": {m.get("id"): d for m, d in close_matches},
    }


def _format_product_details(product: Dict[str, Any], match_info: str = "") -> str:
    """
    Format product details for display.

    Args:
        product: Product dictionary from Zuora API
        match_info: Optional match info string (e.g., "(exact match)" or "(distance: 1)")

    Returns:
        Formatted product details string
    """
    header = f"**Product: {product.get('name', 'N/A')}**"
    if match_info:
        header += f" {match_info}"
    header += "\n\n"

    output = header
    output += f"• Product ID: {product.get('id', 'N/A')}\n"
    output += f"• SKU: {product.get('sku', 'N/A')}\n"
    output += f"• Description: {product.get('description', 'N/A')}\n"
    output += f"• Effective Start: {product.get('effectiveStartDate', 'N/A')}\n"
    output += f"• Effective End: {product.get('effectiveEndDate', 'N/A')}\n"

    rate_plans = product.get("productRatePlans", [])
    if rate_plans:
        output += f"\n**Rate Plans ({len(rate_plans)}):**\n"
        for rp in rate_plans:
            output += (
                f"\n  📋 **{rp.get('name', 'N/A')}** (ID: {rp.get('id', 'N/A')})\n"
            )
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

    return output


@tool
def get_zuora_product(
    identifier: str, identifier_type: Literal["id", "name", "sku"] = "name"
) -> str:
    """
    Get product details by ID, name, or SKU.

    Uses fuzzy matching (Damerau-Levenshtein distance) for name/SKU searches
    to find the closest match even with typos or partial names.
    """
    client = get_zuora_client()

    if identifier_type == "id":
        # Direct lookup by ID - no fuzzy matching needed
        result = client.get_product(identifier)
        if not result.get("success"):
            return (
                f"❌ Error retrieving product: {result.get('error', 'Unknown error')}"
            )

        product = result.get("data", {})
        output = _format_product_details(product)
        output += "\nWould you like to view more details or update any attribute?"
        return output

    # Search by name or SKU with fuzzy matching
    result = client.list_all_products(page_size=100)
    if not result.get("success"):
        return f"❌ Error listing products: {result.get('error', 'Unknown error')}"

    products = result.get("data", {}).get("products", [])
    if not products:
        return "❌ No products found in the catalog."

    search_field = "name" if identifier_type == "name" else "sku"
    match_result = _find_best_product_match(products, identifier, search_field)

    if match_result["type"] == "none":
        return f"❌ No products found matching {identifier_type} = '{identifier}'"

    if match_result["type"] == "exact":
        # Exact match found - get full product details
        matched_product = match_result["matches"][0]
        full_result = client.get_product(matched_product["id"])
        if not full_result.get("success"):
            return f"❌ Error retrieving product: {full_result.get('error', 'Unknown error')}"

        product = full_result.get("data", {})
        output = _format_product_details(product)
        output += "\nWould you like to view more details or update any attribute?"
        return output

    # Fuzzy match - show best match with confirmation question
    matches = match_result["matches"]
    distances = match_result["distances"]

    if len(matches) == 1:
        # Single best match
        matched_product = matches[0]
        distance = distances.get(matched_product.get("id"), "?")
        full_result = client.get_product(matched_product["id"])

        if not full_result.get("success"):
            return f"❌ Error retrieving product: {full_result.get('error', 'Unknown error')}"

        product = full_result.get("data", {})
        output = f"No exact match for '{identifier}'. Closest match found:\n\n"
        output += _format_product_details(product, f"(distance: {distance})")
        output += "\nIs this the product you were looking for?"
        return output

    # Multiple matches with similar distances - show options
    output = f"No exact match for '{identifier}'. Multiple similar products found:\n\n"
    for i, match in enumerate(matches, 1):
        distance = distances.get(match.get("id"), "?")
        output += f"{i}. **{match.get('name', 'N/A')}** (SKU: {match.get('sku', 'N/A')}, distance: {distance})\n"

    output += (
        "\nPlease specify which product you'd like to view, or provide more details."
    )
    return output


@tool
def get_zuora_rate_plan_details(
    product_id: str, rate_plan_name: Optional[str] = None
) -> str:
    """Get rate plan details and charges for a product."""
    client = get_zuora_client()
    result = client.get_product(product_id)

    if not result.get("success"):
        return f"❌ Error retrieving product: {result.get('error', 'Unknown error')}"

    product = result.get("data", {})
    rate_plans = product.get("productRatePlans", [])

    if rate_plan_name:
        rate_plans = [
            rp
            for rp in rate_plans
            if rp.get("name", "").lower() == rate_plan_name.lower()
        ]
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
                output += (
                    f"\n   💰 {ch.get('name', 'N/A')} (ID: {ch.get('id', 'N/A')})\n"
                )
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


@tool(context=True)
def update_zuora_product(
    tool_context: ToolContext,
    product_id: str,
    attribute: Literal[
        "name", "sku", "description", "effectiveStartDate", "effectiveEndDate"
    ],
    new_value: str,
) -> str:
    """Generate payload to update product attribute."""
    payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []

    # Convert to PascalCase for Zuora CRUD API
    crud_field_name = _to_crud_field_name(attribute)

    update_payload = {
        "payload": {
            "method": "PUT",
            "endpoint": f"/v1/object/product/{product_id}",
            "body": {crud_field_name: new_value},
        },
        "zuora_api_type": "product_update",
        "payload_id": str(uuid.uuid4())[:8],
    }

    payloads.append(update_payload)
    tool_context.agent.state.set(PAYLOADS_STATE_KEY, payloads)

    return f"""Generated product update payload:

**Endpoint:** PUT /v1/object/product/{product_id}
**Body:** {{"{crud_field_name}": "{new_value}"}}

This payload has been added to the response. Execute it via the Zuora API to apply the update.

⚠️ Note: Updates only affect NEW subscriptions. Existing subscriptions keep the old values."""


@tool(context=True)
def update_zuora_rate_plan(
    tool_context: ToolContext,
    rate_plan_id: str,
    attribute: Literal["name", "description", "effectiveStartDate", "effectiveEndDate"],
    new_value: str,
) -> str:
    """Generate payload to update rate plan attribute."""
    payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []

    # Convert to PascalCase for Zuora CRUD API
    crud_field_name = _to_crud_field_name(attribute)

    update_payload = {
        "payload": {
            "method": "PUT",
            "endpoint": f"/v1/object/product-rate-plan/{rate_plan_id}",
            "body": {crud_field_name: new_value},
        },
        "zuora_api_type": "rate_plan_update",
        "payload_id": str(uuid.uuid4())[:8],
    }

    payloads.append(update_payload)
    tool_context.agent.state.set(PAYLOADS_STATE_KEY, payloads)

    return f"""Generated rate plan update payload:

**Endpoint:** PUT /v1/object/product-rate-plan/{rate_plan_id}
**Body:** {{"{crud_field_name}": "{new_value}"}}

This payload has been added to the response. Execute it via the Zuora API to apply the update.

⚠️ Note: Updates only affect NEW subscriptions. Existing subscriptions keep the old values.
⚠️ Note: Rate plan end date must be within the product's effective date range."""


@tool(context=True)
def update_zuora_charge(
    tool_context: ToolContext, charge_id: str, attribute: str, new_value: Any
) -> str:
    """Generate payload to update charge attribute."""
    # Check for restricted attributes
    restricted_attrs = ["model", "type", "chargeModel", "chargeType"]
    if attribute.lower() in [a.lower() for a in restricted_attrs]:
        return f"""⚠️ **Cannot update {attribute}**

Charge Model and Charge Type cannot be changed if this charge is used in any existing subscriptions, as it impacts active billing calculations.

👉 **Alternative:** Create a new Rate Plan Charge with the desired model and retire this old charge at a future date."""

    payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []

    # Convert to PascalCase for Zuora CRUD API
    crud_field_name = _to_crud_field_name(attribute)

    update_payload = {
        "payload": {
            "method": "PUT",
            "endpoint": f"/v1/object/product-rate-plan-charge/{charge_id}",
            "body": {crud_field_name: new_value},
        },
        "zuora_api_type": "charge_update",
        "payload_id": str(uuid.uuid4())[:8],
    }

    payloads.append(update_payload)
    tool_context.agent.state.set(PAYLOADS_STATE_KEY, payloads)

    return f"""Generated charge update payload:

**Endpoint:** PUT /v1/object/product-rate-plan-charge/{charge_id}
**Body:** {{"{crud_field_name}": {json.dumps(new_value)}}}

This payload has been added to the response. Execute it via the Zuora API to apply the update.

⚠️ Note: Updates only affect NEW subscriptions. Existing subscriptions keep the old values.
⚠️ Note: Charge Model and Charge Type CANNOT be changed if used in existing subscriptions."""


# ============ Product/Rate Plan/Charge Creation Tools (Payload Generation) ============


@tool(context=True)
def create_product(
    tool_context: ToolContext,
    name: str,
    sku: Optional[str] = None,
    effective_start_date: Optional[str] = None,
    description: Optional[str] = None,
    effective_end_date: Optional[str] = None,
) -> str:
    """Generate payload to create new product. Missing fields will use smart defaults.

    Per Zuora v1 API, both EffectiveStartDate and EffectiveEndDate are required.
    Smart defaults:
    - EffectiveStartDate: today's date if not provided
    - EffectiveEndDate: 10 years from start date if not provided

    Uses PascalCase field names to match Zuora v1 CRUD API.
    """
    from datetime import datetime
    from dateutil.relativedelta import relativedelta

    # Build product payload with provided values - use PascalCase for Zuora v1 CRUD API
    payload_data = {"Name": name}

    # Track defaults applied for transparency
    defaults_applied: List[Dict[str, str]] = []

    # Apply smart defaults for common fields
    if not effective_start_date:
        # Default to today if not provided
        effective_start_date = datetime.now().strftime("%Y-%m-%d")
        defaults_applied.append(
            {
                "field": "EffectiveStartDate",
                "value": f"{effective_start_date} (today)",
            }
        )

    # Validate date format if provided
    if effective_start_date:
        if not validate_date_format(effective_start_date):
            return format_error_message(
                "Invalid date format",
                f"effective_start_date must be YYYY-MM-DD format (e.g., 2024-01-01), got: {effective_start_date}",
            )
        payload_data["EffectiveStartDate"] = effective_start_date

    # EffectiveEndDate is required by Zuora v1 API - apply smart default
    if not effective_end_date:
        # Default to 10 years from start date
        start_dt = datetime.strptime(effective_start_date, "%Y-%m-%d")
        end_dt = start_dt + relativedelta(years=10)
        effective_end_date = end_dt.strftime("%Y-%m-%d")
        defaults_applied.append(
            {
                "field": "EffectiveEndDate",
                "value": f"{effective_end_date} (10 years from start)",
            }
        )

    if effective_end_date:
        if not validate_date_format(effective_end_date):
            return format_error_message(
                "Invalid date format",
                f"effective_end_date must be YYYY-MM-DD format (e.g., 2024-12-31), got: {effective_end_date}",
            )
        # Validate end date is after start date
        if not validate_date_range(effective_start_date, effective_end_date):
            return format_error_message(
                "Invalid date range",
                "effective_end_date must be after effective_start_date",
            )
        payload_data["EffectiveEndDate"] = effective_end_date

    if sku:
        if not validate_sku_format(sku):
            return format_error_message(
                "Invalid SKU format",
                "Use only alphanumeric characters, hyphens, and underscores",
            )
        payload_data["SKU"] = sku

    if description:
        payload_data["Description"] = description

    # Collect warnings for name validation
    warnings = []

    # Validate name length
    is_valid_len, len_warning = validate_name_length(name, "Product name")
    if not is_valid_len:
        warnings.append(len_warning)

    # Validate name uniqueness
    payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []
    is_unique, unique_warning = validate_product_name_unique(name, payloads)
    if not is_unique:
        warnings.append(unique_warning)

    # Delegate to create_payload which handles placeholders and validation
    result = create_payload(
        tool_context, "product_create", payload_data, defaults_applied=defaults_applied
    )

    # Prepend warnings if any
    if warnings:
        warning_html = "<div class='warnings'><p>⚠️ <strong>Warnings:</strong></p><ul>"
        for w in warnings:
            warning_html += f"<li>{w}</li>"
        warning_html += "</ul></div>"
        result = warning_html + result

    return result


@tool(context=True)
def create_rate_plan(
    tool_context: ToolContext,
    product_id: Optional[str] = None,
    product_index: Optional[int] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    effective_start_date: Optional[str] = None,
    effective_end_date: Optional[str] = None,
) -> str:
    """Generate payload to create rate plan for a product.

    For batch creation (creating product and rate plan together), use object references:
    - If product_index is provided, generates @{Product[index].Id}
    - If neither product_id nor product_index provided, auto-generates reference if single product in batch
    - For existing Zuora products, use product_id with the actual Zuora ID

    Args:
        product_id: Zuora product ID OR object reference (e.g., '@{Product[0].Id}')
        product_index: Index of product in current batch (0-based) to auto-generate object reference
        name: Rate plan name
        description: Rate plan description
        effective_start_date: Start date (YYYY-MM-DD)
        effective_end_date: End date (YYYY-MM-DD)
    """
    # Build rate plan payload with provided values
    payload_data = {}

    # Track defaults applied for transparency
    defaults_applied: List[Dict[str, str]] = []

    # Handle ProductId - use PascalCase for Zuora v1 CRUD API
    if product_id:
        # Validate if it's a real Zuora ID or object reference
        if not validate_zuora_id(product_id):
            return format_error_message(
                "Invalid product_id",
                "Provide a valid Zuora product ID (e.g., '8a1234567890abcd') or object reference (e.g., '@{Product[0].Id}')",
            )
        payload_data["ProductId"] = product_id
    elif product_index is not None:
        # Generate object reference from explicit index
        payload_data["ProductId"] = f"@{{Product[{product_index}].Id}}"
    else:
        # Try to auto-generate object reference based on products in current batch
        payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []
        object_ref = _get_product_object_reference(payloads)
        if object_ref:
            payload_data["ProductId"] = object_ref
            defaults_applied.append(
                {
                    "field": "ProductId",
                    "value": f"{object_ref} (auto-linked to product in batch)",
                }
            )
        # If no object_ref, ProductId will be missing and create_payload will add a placeholder

    if name:
        payload_data["Name"] = name

    if description:
        payload_data["Description"] = description

    if effective_start_date:
        if not validate_date_format(effective_start_date):
            return format_error_message(
                "Invalid date format",
                f"effective_start_date must be YYYY-MM-DD format, got: {effective_start_date}",
            )
        payload_data["EffectiveStartDate"] = effective_start_date

    if effective_end_date:
        if not validate_date_format(effective_end_date):
            return format_error_message(
                "Invalid date format",
                f"effective_end_date must be YYYY-MM-DD format, got: {effective_end_date}",
            )
        # Validate end date is after start date if both provided
        if effective_start_date and not validate_date_range(
            effective_start_date, effective_end_date
        ):
            return format_error_message(
                "Invalid date range",
                "effective_end_date must be after effective_start_date",
            )
        payload_data["EffectiveEndDate"] = effective_end_date

    # Collect warnings for name validation
    warnings = []

    if name:
        # Validate name length
        is_valid_len, len_warning = validate_name_length(name, "Rate plan name")
        if not is_valid_len:
            warnings.append(len_warning)

        # Validate name uniqueness within product
        payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []
        product_ref = payload_data.get("ProductId", "")
        is_unique, unique_warning = validate_rate_plan_name_unique(
            name, product_ref, payloads
        )
        if not is_unique:
            warnings.append(unique_warning)

    # Delegate to create_payload which handles placeholders and validation
    result = create_payload(
        tool_context,
        "rate_plan_create",
        payload_data,
        defaults_applied=defaults_applied,
    )

    # Prepend warnings if any
    if warnings:
        warning_html = "<div class='warnings'><p>⚠️ <strong>Warnings:</strong></p><ul>"
        for w in warnings:
            warning_html += f"<li>{w}</li>"
        warning_html += "</ul></div>"
        result = warning_html + result

    return result


# Mapping from simplified charge model names to Zuora API values
CHARGE_MODEL_MAPPING = {
    "flatfee": "Flat Fee Pricing",
    "flat fee": "Flat Fee Pricing",
    "flat fee pricing": "Flat Fee Pricing",
    "perunit": "Per Unit Pricing",
    "per unit": "Per Unit Pricing",
    "per unit pricing": "Per Unit Pricing",
    "tiered": "Tiered Pricing",
    "tiered pricing": "Tiered Pricing",
    "volume": "Volume Pricing",
    "volume pricing": "Volume Pricing",
    "overage": "Overage Pricing",
    "overage pricing": "Overage Pricing",
    "tiered with overage": "Tiered with Overage Pricing",
    "tiered with overage pricing": "Tiered with Overage Pricing",
    "discount-fixed": "Discount-Fixed Amount",
    "discount-fixed amount": "Discount-Fixed Amount",
    "discount-percentage": "Discount-Percentage",
    "discount-pct": "Discount-Percentage",
}


def _normalize_charge_model(model: str) -> str:
    """Convert simplified charge model name to Zuora API value."""
    if not model:
        return model
    normalized = model.lower().strip()
    return CHARGE_MODEL_MAPPING.get(normalized, model)


def _validate_tier_boundaries(tiers: List[Dict[str, Any]]) -> List[str]:
    """
    Validate tier boundaries for gaps and overlaps.

    Checks that tier boundaries are contiguous (no gaps or overlaps).
    For tiered/volume pricing to work correctly, each tier should start
    exactly where the previous tier ended + 1.

    Args:
        tiers: List of normalized tier dictionaries with StartingUnit/EndingUnit

    Returns:
        List of warning messages (empty if no issues found)
    """
    warnings = []

    for i in range(1, len(tiers)):
        prev_tier = tiers[i - 1]
        curr_tier = tiers[i]

        prev_ending = prev_tier.get("EndingUnit")
        curr_starting = curr_tier.get("StartingUnit")

        if prev_ending is None:
            # Previous tier is unlimited - no subsequent tiers should exist
            warnings.append(
                f"Tier {i} has no EndingUnit (unlimited), but Tier {i + 1} exists. "
                f"Units after {prev_tier.get('StartingUnit', 0)} will be priced by Tier {i}, not Tier {i + 1}."
            )
        elif curr_starting is not None:
            expected_start = prev_ending + 1
            if curr_starting < expected_start:
                # Overlap
                warnings.append(
                    f"Tier overlap: Tier {i + 1} starts at {curr_starting} but Tier {i} ends at {prev_ending}. "
                    f"Units {curr_starting}-{prev_ending} have overlapping pricing."
                )
            elif curr_starting > expected_start:
                # Gap
                warnings.append(
                    f"Tier gap: No pricing for units {expected_start}-{curr_starting - 1} "
                    f"(between Tier {i} ending at {prev_ending} and Tier {i + 1} starting at {curr_starting})."
                )

    return warnings


def _normalize_tiers(
    tiers: List[Dict[str, Any]],
    currency: str = "USD",
    default_price_format: str = "Per Unit",
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Normalize tier input to Zuora API format and validate tier structure.

    Supports two input formats:
    1. Simplified: [{"units": 1000, "price": 0.10}, {"units": 10000, "price": 0.08}, {"price": 0.05}]
       - "units" = EndingUnit for that tier
       - StartingUnit is auto-calculated (1 for first tier, prev_ending+1 for rest)
       - Omitting "units" or setting it to None means unlimited (last tier)

    2. Explicit: [{"StartingUnit": 1, "EndingUnit": 1000, "Price": 0.10}, ...]
       - Full control over tier boundaries
       - Missing StartingUnit is auto-calculated

    Args:
        tiers: List of tier dictionaries (simplified or explicit format)
        currency: Default currency code (default: USD)
        default_price_format: Default price format (default: "Per Unit")

    Returns:
        Tuple of (normalized_tiers, warnings)
        - normalized_tiers: List of tier dicts in Zuora API format
        - warnings: List of validation warning messages
    """
    if not tiers:
        return [], []

    normalized = []
    warnings = []
    prev_ending = None

    for i, tier in enumerate(tiers):
        # Determine price (support both "Price" and "price" keys)
        tier_price = tier.get("Price", tier.get("price", 0))

        # Determine StartingUnit and EndingUnit
        if "units" in tier:
            # Simplified format: {"units": 1000, "price": 0.10}
            # StartingUnit starts from 1 (not 0) per Zuora convention
            starting = (
                1 if i == 0 else (prev_ending + 1 if prev_ending is not None else 1)
            )
            ending = tier.get("units")  # None means unlimited
        else:
            # Explicit format: {"StartingUnit": 1, "EndingUnit": 1000, "Price": 0.10}
            if "StartingUnit" in tier:
                starting = tier["StartingUnit"]
            else:
                # Auto-calculate: 1 for first tier, prev_ending + 1 for subsequent
                starting = (
                    1 if i == 0 else (prev_ending + 1 if prev_ending is not None else 1)
                )

            ending = tier.get("EndingUnit")  # None means unlimited

        # Build normalized tier entry with ALL required fields
        tier_entry = {
            "Currency": tier.get("Currency", currency),
            "Price": tier_price,
            "Tier": tier.get("Tier", i + 1),
            "StartingUnit": starting,
            "PriceFormat": tier.get("PriceFormat", default_price_format),
        }

        # Only include EndingUnit if it's not the unlimited tier
        if ending is not None:
            tier_entry["EndingUnit"] = ending

        normalized.append(tier_entry)
        prev_ending = ending

    # Validate tier boundaries (gaps/overlaps)
    boundary_warnings = _validate_tier_boundaries(normalized)
    warnings.extend(boundary_warnings)

    return normalized, warnings


def _infer_charge_model_conservative(
    charge_type: Optional[str],
    price: Optional[float],
    uom: Optional[str],
    name: Optional[str] = None,
    tiers: Optional[List[Dict[str, Any]]] = None,
    included_units: Optional[float] = None,
) -> Optional[str]:
    """
    Conservatively infer charge model from context.

    Only infers when the context is very clear and unambiguous.
    Returns None if inference is not confident enough.

    Rules (in order of priority):
    1. If multiple tiers provided → Tiered Pricing
    2. If included_units AND tiers → Tiered with Overage Pricing
    3. If included_units (no tiers) → Overage Pricing
    4. If UOM is provided AND charge_type is Usage (no tiers) → Per Unit Pricing
    5. If price is provided AND NO UOM AND charge_type is Recurring/OneTime → Flat Fee Pricing

    Does NOT infer in ambiguous cases - returns None so a placeholder is created.
    """
    # Rule 1: If multiple tiers provided → Tiered Pricing
    if tiers and len(tiers) > 1:
        if included_units is not None:
            # Rule 2: Tiers + included_units → Tiered with Overage Pricing
            return "Tiered with Overage Pricing"
        return "Tiered Pricing"

    # Rule 3: If included_units provided (no tiers or single tier) → Overage Pricing
    if included_units is not None and (not tiers or len(tiers) <= 1):
        return "Overage Pricing"

    # Rule 4: Usage charge with UOM (and no tiers) → Per Unit Pricing
    # This is a very clear signal - usage charges with a unit of measure are per-unit
    if charge_type == "Usage" and uom and not tiers:
        return "Per Unit Pricing"

    # Rule 5: Recurring/OneTime with price but NO UOM → Flat Fee Pricing
    # A fixed price without a unit of measure strongly suggests flat fee
    if charge_type in ("Recurring", "OneTime") and price is not None and not uom:
        return "Flat Fee Pricing"

    # All other cases are ambiguous - don't infer, let placeholder be created
    return None


# Common UOM aliases mapped to valid Zuora UOM names
# Used to auto-correct user input to valid tenant UOMs
UOM_ALIASES: Dict[str, str] = {
    # API/Calls
    "calls": "APICalls",
    "call": "APICalls",
    "api calls": "APICalls",
    "api call": "APICalls",
    "apicall": "APICalls",
    # SMS/Messages
    "messages": "sms",
    "message": "sms",
    "texts": "sms",
    "text": "sms",
    # Storage
    "gigabytes": "GB",
    "gigabyte": "GB",
    "megabytes": "MB",
    "megabyte": "MB",
    # Time
    "hours": "Hour",
    "hour": "Hour",
    "minutes": "Minutes",
    "minute": "Minutes",
    # Entities
    "users": "User",
    "user": "User",
    "licenses": "License",
    "license": "License",
    "units": "Unit",
    "unit": "Unit",
    # Generic
    "each": "each",
    "item": "each",
    "items": "each",
}


def _normalize_uom(uom: str, available_uoms: List[str]) -> Tuple[str, bool]:
    """
    Normalize UOM to a valid Zuora UOM name.

    Args:
        uom: User-provided UOM string
        available_uoms: List of valid UOMs from tenant

    Returns:
        Tuple of (normalized_uom, was_corrected)
    """
    # Exact match - use as-is
    if uom in available_uoms:
        return uom, False

    # Case-insensitive match against available UOMs
    uom_lower = uom.lower()
    for valid_uom in available_uoms:
        if valid_uom.lower() == uom_lower:
            return valid_uom, True

    # Check aliases and find matching available UOM
    if uom_lower in UOM_ALIASES:
        alias_target = UOM_ALIASES[uom_lower]
        # Verify alias target exists in tenant (case-insensitive)
        for valid_uom in available_uoms:
            if valid_uom.lower() == alias_target.lower():
                return valid_uom, True

    # Default to "each" if available
    for valid_uom in available_uoms:
        if valid_uom.lower() == "each":
            return valid_uom, True

    # Last resort - return "each" even if not in available (Zuora usually has it)
    return "each", True


def _get_charge_model_inference_reason(
    charge_type: Optional[str],
    price: Optional[float],
    uom: Optional[str],
    tiers: Optional[List[Dict[str, Any]]],
    included_units: Optional[float],
) -> Optional[str]:
    """
    Get human-readable reason for charge model inference.

    Returns a description of why the charge model was inferred,
    or None if the model was not inferred (was explicitly provided).
    """
    if tiers and len(tiers) > 1:
        if included_units is not None:
            return "inferred: multiple tiers + included units"
        return "inferred: multiple tiers provided"

    if included_units is not None and (not tiers or len(tiers) <= 1):
        return "inferred: included units without tiers"

    if charge_type == "Usage" and uom and not tiers:
        return "inferred: usage charge with UOM"

    if charge_type in ("Recurring", "OneTime") and price is not None and not uom:
        return "inferred: fixed price, no UOM"

    return None


@tool(context=True)
def create_charge(
    tool_context: ToolContext,
    rate_plan_id: Optional[str] = None,
    rate_plan_index: Optional[int] = None,
    name: Optional[str] = None,
    charge_type: Optional[Literal["Recurring", "OneTime", "Usage"]] = None,
    charge_model: Optional[str] = None,
    price: Optional[float] = None,
    tiers: Optional[List[Dict[str, Any]]] = None,
    included_units: Optional[float] = None,
    overage_price: Optional[float] = None,
    billing_period: Optional[
        Literal["Month", "Quarter", "Annual", "Semi-Annual", "Week", "Specific Months"]
    ] = None,
    billing_timing: Optional[Literal["In Advance", "In Arrears"]] = None,
    bill_cycle_type: Literal[
        "DefaultFromCustomer",
        "SpecificDayofMonth",
        "SubscriptionStartDay",
        "ChargeTriggerDay",
    ] = "DefaultFromCustomer",
    trigger_event: Literal[
        "ContractEffective", "ServiceActivation", "CustomerAcceptance"
    ] = "ContractEffective",
    uom: Optional[str] = None,
    description: Optional[str] = None,
    currency: str = "USD",
    rating_group: Optional[
        Literal[
            "ByBillingPeriod",
            "ByUsageStartDate",
            "ByUsageRecord",
            "ByUsageUpload",
            "ByGroupId",
        ]
    ] = None,
) -> str:
    """Generate charge creation payload per Zuora v1 API schema.

    For batch creation (creating rate plan and charge together), use object references:
    - If rate_plan_index is provided, generates @{ProductRatePlan[index].Id}
    - If neither rate_plan_id nor rate_plan_index provided, auto-generates reference to most recent rate plan
    - For existing Zuora rate plans, use rate_plan_id with the actual Zuora ID

    Required fields per Zuora API:
    - Name, ProductRatePlanId, ChargeModel, ChargeType
    - BillCycleType, BillingPeriod, TriggerEvent
    - ProductRatePlanChargeTierData (pricing container)

    Smart defaults applied:
    - BillCycleType: DefaultFromCustomer
    - TriggerEvent: ContractEffective
    - BillingTiming: In Arrears for Usage charges, In Advance for others
    - BillingPeriod: Month (for Recurring charges)
    - Currency: USD
    - RatingGroup: ByBillingPeriod for tiered/volume Usage charges

    Pricing Models Supported:
    - Flat Fee Pricing: Single flat price (use 'price' parameter)
    - Per Unit Pricing: Price per unit (use 'price' parameter)
    - Tiered Pricing: Graduated pricing - each tier has its own rate (use 'tiers' parameter)
    - Volume Pricing: All-units pricing - entire qty priced at one tier's rate (use 'tiers' parameter)
    - Overage Pricing: X units included, then $Y per unit (use 'included_units' + 'overage_price')
    - Tiered with Overage: Tiered pricing + overage (use 'tiers' + 'included_units' + 'overage_price')

    Args:
        rate_plan_id: Zuora rate plan ID OR object reference (e.g., '@{ProductRatePlan[0].Id}')
        rate_plan_index: Index of rate plan in current batch (0-based) to auto-generate object reference
        name: Charge name
        charge_type: OneTime, Recurring, or Usage
        charge_model: Pricing model (accepts simplified names like 'FlatFee' or full names like 'Flat Fee Pricing')
        price: Price amount (for single-tier pricing: Flat Fee, Per Unit, or overage rate)
        tiers: List of pricing tiers for Tiered/Volume pricing. Supports two formats:
               Explicit format (full control):
               - Price (required): Price for this tier
               - StartingUnit: Unit where tier starts (default: 1 for first tier, auto-calculated for rest)
               - EndingUnit: Unit where tier ends (omit for unlimited/last tier)
               - PriceFormat: "Per Unit" or "Flat Fee" (default: "Per Unit")
               - Currency: Override currency for this tier (default: uses charge currency)
               Simplified format (auto-calculates boundaries):
               - units: EndingUnit for this tier (omit or None for unlimited)
               - price: Price for this tier
        included_units: Number of units included before overage pricing kicks in.
                       Used with Overage Pricing and Tiered with Overage Pricing.
        overage_price: Price per unit after included units are consumed.
                      Used with Overage Pricing and Tiered with Overage Pricing.
        billing_period: Month, Quarter, Annual, etc.
        billing_timing: In Advance or In Arrears (defaults to In Arrears for Usage, In Advance otherwise)
        bill_cycle_type: When to bill
        trigger_event: When to start billing
        uom: Unit of measure for usage charges
        description: Charge description
        currency: Currency code (default: USD)
        rating_group: How to aggregate usage for rating (ByBillingPeriod, ByUsageStartDate, etc.)
                     Auto-set to ByBillingPeriod for tiered/volume Usage charges

    Examples:
        # Flat Fee Pricing (single price)
        create_charge(name="Monthly Fee", charge_type="Recurring", charge_model="Flat Fee Pricing", price=99.00)

        # Per Unit Pricing
        create_charge(name="API Calls", charge_type="Usage", charge_model="Per Unit Pricing", price=0.01, uom="Calls")

        # Tiered Pricing - Explicit format (full control over boundaries)
        create_charge(
            name="API Calls",
            charge_type="Usage",
            charge_model="Tiered Pricing",
            uom="Calls",
            tiers=[
                {"StartingUnit": 1, "EndingUnit": 1000, "Price": 0.10, "PriceFormat": "Per Unit"},
                {"StartingUnit": 1001, "EndingUnit": 10000, "Price": 0.08, "PriceFormat": "Per Unit"},
                {"StartingUnit": 10001, "Price": 0.05, "PriceFormat": "Per Unit"},  # No EndingUnit = unlimited
            ]
        )

        # Tiered Pricing - Simplified format (auto-calculates boundaries)
        create_charge(
            name="API Calls",
            charge_type="Usage",
            charge_model="Tiered Pricing",
            uom="Calls",
            tiers=[
                {"units": 1000, "price": 0.10},   # 1-1000 @ $0.10/unit
                {"units": 10000, "price": 0.08},  # 1001-10000 @ $0.08/unit
                {"price": 0.05},                   # 10001+ @ $0.05/unit (unlimited)
            ]
        )

        # Volume Pricing (entire quantity priced at one tier's rate)
        create_charge(
            name="Storage",
            charge_type="Usage",
            charge_model="Volume Pricing",
            uom="GB",
            tiers=[
                {"units": 100, "price": 1.00},
                {"units": 1000, "price": 0.80},
                {"price": 0.50},
            ]
        )

        # Overage Pricing (X units included, then $Y per unit after)
        create_charge(
            name="API Usage",
            charge_type="Usage",
            charge_model="Overage Pricing",
            uom="Calls",
            included_units=10000,   # 10,000 calls included
            overage_price=0.003,    # $0.003 per call after included units
        )

        # Tiered with Overage Pricing (tiered pricing + overage after all tiers)
        create_charge(
            name="Data Transfer",
            charge_type="Usage",
            charge_model="Tiered with Overage Pricing",
            uom="GB",
            included_units=100,     # 100 GB included in base
            tiers=[
                {"units": 500, "price": 0.10},   # 0-500 GB @ $0.10/GB
                {"units": 1000, "price": 0.08},  # 501-1000 GB @ $0.08/GB
            ],
            overage_price=0.05,     # $0.05/GB after 1000 GB
        )
    """
    # Build charge payload with provided values - use PascalCase for Zuora v1 CRUD API
    payload_data = {}

    # Track defaults applied for transparency
    defaults_applied: List[Dict[str, str]] = []

    # Track if user provided currency explicitly (vs using default parameter)
    # We check if currency differs from default "USD" - if same, it might be defaulted
    user_provided_currency = currency != "USD"

    # Handle ProductRatePlanId
    if rate_plan_id:
        if not validate_zuora_id(rate_plan_id):
            return format_error_message(
                "Invalid rate_plan_id",
                "Provide a valid Zuora rate plan ID (e.g., '8a1234567890abcd') or object reference (e.g., '@{ProductRatePlan[0].Id}')",
            )
        payload_data["ProductRatePlanId"] = rate_plan_id
    elif rate_plan_index is not None:
        # Generate object reference from explicit index
        payload_data["ProductRatePlanId"] = (
            f"@{{ProductRatePlan[{rate_plan_index}].Id}}"
        )
    else:
        # Try to auto-generate object reference based on rate plans in current batch
        payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []
        object_ref = _get_rate_plan_object_reference(payloads)
        if object_ref:
            payload_data["ProductRatePlanId"] = object_ref
            defaults_applied.append(
                {
                    "field": "ProductRatePlanId",
                    "value": f"{object_ref} (auto-linked to rate plan in batch)",
                }
            )
        # If no object_ref, ProductRatePlanId will be missing and create_payload will add a placeholder

    if name:
        payload_data["Name"] = name

    if charge_type:
        payload_data["ChargeType"] = charge_type

    if charge_model:
        # Normalize charge model to Zuora API value
        payload_data["ChargeModel"] = _normalize_charge_model(charge_model)
    else:
        # Try conservative inference when charge_model is not explicitly provided
        inferred_model = _infer_charge_model_conservative(
            charge_type=charge_type,
            price=price,
            uom=uom,
            name=name,
            tiers=tiers,
            included_units=included_units,
        )
        if inferred_model:
            payload_data["ChargeModel"] = inferred_model
            # Get inference reason for transparency
            reason = _get_charge_model_inference_reason(
                charge_type=charge_type,
                price=price,
                uom=uom,
                tiers=tiers,
                included_units=included_units,
            )
            defaults_applied.append(
                {
                    "field": "ChargeModel",
                    "value": f"{inferred_model} ({reason})"
                    if reason
                    else inferred_model,
                }
            )

    # Required fields with smart defaults (per Zuora v1 API)
    payload_data["BillCycleType"] = bill_cycle_type
    payload_data["TriggerEvent"] = trigger_event

    # Determine if this is a tiered/volume charge model
    # Tiered/Volume usage charges do NOT use BillingTiming per Zuora API
    current_charge_model = payload_data.get("ChargeModel", "")
    is_tiered_model = current_charge_model in (
        "Tiered Pricing",
        "Volume Pricing",
        "Tiered with Overage Pricing",
    )

    # Smart default for BillingTiming based on charge type
    # Note: Tiered/Volume usage charges should NOT have BillingTiming
    if billing_timing is not None:
        payload_data["BillingTiming"] = billing_timing
    elif charge_type == "Usage" and is_tiered_model:
        # Do NOT add BillingTiming for tiered/volume usage charges
        pass
    elif charge_type == "Usage":
        payload_data["BillingTiming"] = "In Arrears"
        defaults_applied.append(
            {
                "field": "BillingTiming",
                "value": "In Arrears (usage charges billed after consumption)",
            }
        )
    else:
        payload_data["BillingTiming"] = "In Advance"
        defaults_applied.append(
            {
                "field": "BillingTiming",
                "value": "In Advance",
            }
        )

    if description:
        payload_data["Description"] = description

    # Billing period - only set if explicitly provided
    # If not provided for Recurring charges, validation will create a placeholder
    if billing_period:
        payload_data["BillingPeriod"] = billing_period

    if uom:
        # Auto-correct UOM to valid tenant UOM
        from .zuora_settings import get_available_uom_names

        available_uoms = get_available_uom_names()
        if available_uoms:
            normalized_uom, was_corrected = _normalize_uom(uom, available_uoms)
            if was_corrected:
                defaults_applied.append(
                    {
                        "field": "UOM",
                        "value": f"{normalized_uom} (corrected from '{uom}')",
                    }
                )
            payload_data["UOM"] = normalized_uom
        else:
            # No tenant UOMs available - use as-is
            payload_data["UOM"] = uom

    # Determine charge model type for special handling
    normalized_charge_model = payload_data.get("ChargeModel", "")
    is_tiered_or_volume = normalized_charge_model in (
        "Tiered Pricing",
        "Volume Pricing",
    )
    is_tiered_with_overage = normalized_charge_model == "Tiered with Overage Pricing"
    is_overage = normalized_charge_model == "Overage Pricing"

    # RatingGroup - required for tiered/volume Usage charges to properly aggregate usage
    # Without this, Zuora may not display tiered pricing correctly
    if rating_group:
        payload_data["RatingGroup"] = rating_group
    elif charge_type == "Usage" and (
        is_tiered_or_volume or is_tiered_with_overage or is_overage
    ):
        # Auto-set RatingGroup for tiered/volume/overage usage charges
        payload_data["RatingGroup"] = "ByBillingPeriod"
        defaults_applied.append(
            {
                "field": "RatingGroup",
                "value": "ByBillingPeriod (auto-set for tiered/volume usage)",
            }
        )

    # Track currency default if user didn't explicitly provide it
    if not user_provided_currency:
        from .zuora_settings import get_default_currency

        tenant_default = get_default_currency()
        if currency == tenant_default:
            defaults_applied.append(
                {
                    "field": "Currency",
                    "value": f"{currency} (tenant default)",
                }
            )
        else:
            defaults_applied.append(
                {
                    "field": "Currency",
                    "value": currency,
                }
            )

    # Collect warnings (tier validation warnings will be added here)
    warnings = []

    # Handle IncludedUnits (for Overage and Tiered with Overage pricing)
    if included_units is not None:
        payload_data["IncludedUnits"] = included_units

    # Build ProductRatePlanChargeTierData (required per Zuora API)
    # This is the container for pricing information
    if tiers:
        # Tiered, Volume, or Tiered with Overage pricing
        # Use _normalize_tiers to ensure all required fields are present
        normalized_tiers, tier_warnings = _normalize_tiers(tiers, currency)
        warnings.extend(tier_warnings)

        # For Tiered with Overage, add an overage tier at the end if overage_price is provided
        if is_tiered_with_overage and overage_price is not None:
            last_tier_num = len(normalized_tiers)
            last_ending = (
                normalized_tiers[-1].get("EndingUnit") if normalized_tiers else None
            )

            # Calculate overage tier starting unit
            if last_ending is not None:
                overage_start = last_ending + 1
            else:
                # Last tier is already unlimited - warn user
                warnings.append(
                    "Last tier has no EndingUnit (unlimited). Overage tier will not be added. "
                    "Set EndingUnit on the last tier to enable overage pricing after that tier."
                )
                overage_start = None

            if overage_start is not None:
                normalized_tiers.append(
                    {
                        "Currency": currency,
                        "Price": overage_price,
                        "Tier": last_tier_num + 1,
                        "StartingUnit": overage_start,
                        "PriceFormat": "Per Unit",
                        # No EndingUnit = unlimited overage tier
                    }
                )

        payload_data["ProductRatePlanChargeTierData"] = {
            "ProductRatePlanChargeTier": normalized_tiers
        }

    elif is_overage:
        # Pure Overage Pricing: included units + single overage tier
        overage_tier_price = overage_price if overage_price is not None else price
        if overage_tier_price is not None:
            payload_data["ProductRatePlanChargeTierData"] = {
                "ProductRatePlanChargeTier": [
                    {
                        "Currency": currency,
                        "Price": overage_tier_price,
                        "PriceFormat": "Per Unit",
                        "StartingUnit": 1,
                        "Tier": 1,
                    }
                ]
            }
        else:
            warnings.append(
                "Overage Pricing requires a price for overage units. "
                "Please specify 'overage_price' or 'price' parameter."
            )

    elif price is not None:
        # Single tier pricing - structure differs by charge model
        if normalized_charge_model == "Flat Fee Pricing":
            # Flat Fee: minimal tier structure per Zuora docs
            # No StartingUnit, Tier, or PriceFormat needed
            payload_data["ProductRatePlanChargeTierData"] = {
                "ProductRatePlanChargeTier": [
                    {
                        "Currency": currency,
                        "Price": price,
                    }
                ]
            }
        else:
            # Per Unit and other unit-based models need full tier structure
            payload_data["ProductRatePlanChargeTierData"] = {
                "ProductRatePlanChargeTier": [
                    {
                        "Currency": currency,
                        "Price": price,
                        "StartingUnit": 1,
                        "PriceFormat": "Per Unit",
                        "Tier": 1,
                    }
                ]
            }

    if name:
        # Validate name length
        is_valid_len, len_warning = validate_name_length(name, "Charge name")
        if not is_valid_len:
            warnings.append(len_warning)

        # Validate name uniqueness within rate plan
        payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []
        rp_ref = payload_data.get("ProductRatePlanId", "")
        is_unique, unique_warning = validate_charge_name_unique(name, rp_ref, payloads)
        if not is_unique:
            warnings.append(unique_warning)

    # Delegate to create_payload which handles placeholders and validation
    # It will add placeholders for conditionally required fields based on ChargeType
    result = create_payload(
        tool_context, "charge_create", payload_data, defaults_applied=defaults_applied
    )

    # Prepend warnings if any
    if warnings:
        warning_html = "<div class='warnings'><p>⚠️ <strong>Warnings:</strong></p><ul>"
        for w in warnings:
            warning_html += f"<li>{w}</li>"
        warning_html += "</ul></div>"
        result = warning_html + result

    return result


# ============ Billing Architect Advisory Tools ============

ADVISORY_PAYLOADS_STATE_KEY = "advisory_payloads"


@tool(context=True)
def generate_prepaid_config(
    tool_context: ToolContext,
    product_name: str,
    rate_plan_name: str,
    prepaid_uom: str,
    prepaid_amount: float,
    prepaid_quantity: float,
    enable_auto_topup: bool = True,
    topup_threshold_pct: float = 20.0,
    use_field_lookup_for_topup: bool = False,
    account_field_name: Optional[str] = None,
) -> str:
    """
    Generate Prepaid with Drawdown configuration with optional auto top-up.

    ADVISORY ONLY - provides configuration guidance and payloads without executing.

    Args:
        product_name: Name of the product
        rate_plan_name: Name of the rate plan
        prepaid_uom: Unit of measure for prepaid balance (e.g., "API_CALL", "SMS", "CREDIT")
        prepaid_amount: Dollar amount for the prepaid charge
        prepaid_quantity: Number of units included in prepaid
        enable_auto_topup: Whether to configure auto top-up workflow
        topup_threshold_pct: Percentage threshold for triggering top-up (default: 20%)
        use_field_lookup_for_topup: Use fieldLookup() for dynamic top-up amounts
        account_field_name: Account custom field for fieldLookup (e.g., "TopUpAmount__c")

    Returns:
        Complete configuration guide for Prepaid with Drawdown setup.
    """
    # Prepaid charge configuration
    prepaid_charge_config = {
        "name": f"{rate_plan_name} - Prepaid {prepaid_uom}",
        "type": "Recurring",
        "model": "Prepaid with Drawdown",
        "billingPeriod": "Month",
        "billingTiming": "In Advance",
        "prepaidUOM": prepaid_uom,
        "prepaidQuantity": prepaid_quantity,
        "pricing": [{"currency": "USD", "price": prepaid_amount}],
        "validityPeriodType": "SUBSCRIPTION_TERM",
        "rollover": {"enabled": True, "percentage": 100, "cap": None},
    }

    # Drawdown charge configuration
    drawdown_charge_config = {
        "name": f"{rate_plan_name} - {prepaid_uom} Usage",
        "type": "Usage",
        "model": "Per Unit Pricing",
        "uom": prepaid_uom,
        "usageType": "DRAWDOWN",
        "pricing": [{"currency": "USD", "price": 0}],
    }

    # Field lookup expression
    field_lookup_expr = ""
    if use_field_lookup_for_topup and account_field_name:
        field_lookup_expr = f"fieldLookup('Account.{account_field_name}')"

    guide = f"""
## Prepaid with Drawdown Configuration

### Product: {product_name}
### Rate Plan: {rate_plan_name}

---

### Step 1: Create the Prepaid Charge

This charge creates the prepaid balance (wallet) for the customer.

**API Endpoint:** POST /v1/object/product-rate-plan-charge

```json
{json.dumps(prepaid_charge_config, indent=2)}
```

**Key Settings:**
- `prepaidUOM`: {prepaid_uom} - The unit type tracked in the balance
- `prepaidQuantity`: {prepaid_quantity:,.0f} - Units loaded per billing period
- `price`: ${prepaid_amount:,.2f} - Cost to the customer
- `rollover`: Enabled - unused units carry forward

---

### Step 2: Create the Drawdown Charge

This usage charge draws from the prepaid balance.

**API Endpoint:** POST /v1/object/product-rate-plan-charge

```json
{json.dumps(drawdown_charge_config, indent=2)}
```

**Key Settings:**
- `usageType`: DRAWDOWN - Links to prepaid balance
- `price`: $0 - Usage is "free" because it draws from prepaid

---

### Step 3: Configure Auto Top-Up {"(Using fieldLookup)" if use_field_lookup_for_topup else ""}
"""

    if enable_auto_topup:
        threshold_units = prepaid_quantity * (topup_threshold_pct / 100)
        guide += f"""
**Threshold-Based Top-Up Configuration:**

Top-up triggers when balance falls below {topup_threshold_pct}% of original quantity.
- Threshold: {threshold_units:,.0f} {prepaid_uom}

**Required Components:**

1. **Account Custom Field** (for threshold):
```json
{{
    "name": "MinimumThreshold__c",
    "label": "Minimum Balance Threshold",
    "type": "Number",
    "description": "Balance threshold that triggers auto top-up"
}}
```
"""

        if use_field_lookup_for_topup and account_field_name:
            guide += f"""
2. **Account Custom Field** (for top-up amount):
```json
{{
    "name": "{account_field_name}",
    "label": "Custom Top-Up Amount",
    "type": "Number",
    "description": "Customer-specific top-up amount"
}}
```

**Using fieldLookup() for Dynamic Top-Up Amount:**

The top-up amount is read from: `{field_lookup_expr}`

In the top-up charge pricing configuration:
```json
{{
    "pricing": [{{
        "currency": "USD",
        "price": "{field_lookup_expr}"
    }}]
}}
```
"""
        else:
            guide += f"""
**Fixed Top-Up Amount:**
Standard top-up of ${prepaid_amount:,.2f} and {prepaid_quantity:,.0f} {prepaid_uom}.
"""

        guide += f"""
3. **Notification Rule** (trigger for workflow):
   - Event: "Usage Record Creation" or "PrepaidBalanceLow"
   - Action: Trigger workflow to check balance

4. **Workflow** (auto top-up logic):
   - Trigger: Notification callout
   - Logic: Compare balance vs threshold
   - Action: Create Order to add prepaid balance

See `generate_workflow_config` and `generate_notification_rule` tools for detailed configurations.
"""

    guide += f"""
---

### Step 4: Handle Overage (Optional)

When prepaid balance is depleted, you have options:

**Option A: Block Usage**
- Set `overageHandling`: "Block"
- Usage above balance is rejected

**Option B: Allow Overage at Per-Unit Price**
- Set `overageHandling`: "AllowOverage"
- Configure overage price per unit

**Option C: Auto Top-Up on Depletion**
- Workflow triggers on "PrepaidBalanceDepleted" event
- Creates order to add more prepaid balance

---

### Implementation Checklist

- [ ] Create Product: {product_name}
- [ ] Create Rate Plan: {rate_plan_name}
- [ ] Add Prepaid Charge with configuration above
- [ ] Add Drawdown Charge linked to prepaid
{"- [ ] Create Account custom field: " + account_field_name if use_field_lookup_for_topup and account_field_name else ""}
{"- [ ] Set up notification rule for usage events" if enable_auto_topup else ""}
{"- [ ] Create auto top-up workflow" if enable_auto_topup else ""}
- [ ] Test with sample subscription
- [ ] Verify balance tracking works correctly
- [ ] Test top-up triggering (if enabled)

---

### Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| Balance not tracking | Ensure drawdown charge has `usageType: DRAWDOWN` |
| fieldLookup errors | Verify custom field exists and API name is correct |
| Top-up not triggering | Check workflow event filter conditions |
| Wrong currency | Ensure all charges use the same currency |
"""

    # Store advisory payload
    payloads = tool_context.agent.state.get(ADVISORY_PAYLOADS_STATE_KEY) or []
    payloads.append(
        {
            "type": "prepaid_config",
            "name": f"{product_name} - {rate_plan_name}",
            "prepaid_charge": prepaid_charge_config,
            "drawdown_charge": drawdown_charge_config,
            "endpoint": "POST /v1/object/product-rate-plan-charge",
        }
    )
    tool_context.agent.state.set(ADVISORY_PAYLOADS_STATE_KEY, payloads)

    return guide


@tool(context=True)
def generate_workflow_config(
    tool_context: ToolContext,
    workflow_name: str,
    trigger_type: Literal["Scheduled", "Callout", "Event"],
    description: str,
    schedule: Optional[str] = None,
    event_type: Optional[str] = None,
) -> str:
    """
    Generate a Zuora Workflow configuration payload.

    ADVISORY ONLY - does NOT execute the workflow creation.

    Args:
        workflow_name: Name for the workflow
        trigger_type: How the workflow is triggered (Scheduled, Callout, Event)
        description: Description of what the workflow does
        schedule: Cron expression for scheduled triggers (e.g., "0 0 1 5 *" for May 1st)
        event_type: Event type for event triggers (e.g., "UsageRecordCreation", "PrepaidBalanceLow")

    Returns:
        Complete workflow configuration with implementation instructions.
    """
    workflow_config: Dict[str, Any] = {
        "name": workflow_name,
        "description": description,
        "type": trigger_type,
        "status": "Active",
        "timezone": "UTC",
    }

    if trigger_type == "Scheduled" and schedule:
        workflow_config["schedule"] = {
            "cronExpression": schedule,
            "startDate": "{{REPLACE_WITH_START_DATE}}",
        }
    elif trigger_type == "Event" and event_type:
        workflow_config["event"] = {"eventType": event_type, "filters": []}
    elif trigger_type == "Callout":
        workflow_config["callout"] = {
            "endpoint": "{{WORKFLOW_WILL_GENERATE_ENDPOINT}}",
            "authentication": "OAuth",
        }

    # Build example workflow tasks based on common use cases
    example_tasks = []
    if "top-up" in description.lower() or "topup" in description.lower():
        example_tasks = [
            {
                "name": "Get Account Info",
                "type": "API",
                "description": "Retrieve account and subscription details",
                "api_call": "GET /v1/accounts/{{accountId}}",
            },
            {
                "name": "Check Prepaid Balance",
                "type": "API",
                "description": "Get current prepaid balance",
                "api_call": "GET /v1/prepaid-balances?accountId={{accountId}}",
            },
            {
                "name": "Compare Balance vs Threshold",
                "type": "Condition",
                "description": "Check if balance < threshold",
                "condition": "{{prepaidBalance}} < {{account.MinimumThreshold__c}}",
            },
            {
                "name": "Create Top-Up Order",
                "type": "API",
                "description": "Create order to add prepaid balance",
                "api_call": "POST /v1/orders",
            },
        ]
    elif "transition" in description.lower():
        example_tasks = [
            {
                "name": "Get Subscription",
                "type": "API",
                "description": "Retrieve subscription details",
                "api_call": "GET /v1/subscriptions/{{subscriptionId}}",
            },
            {
                "name": "Check Product Type",
                "type": "Condition",
                "description": "Verify current product is Pay-as-you-go",
                "condition": "{{subscription.ratePlanName}} == 'Pay-as-you-go'",
            },
            {
                "name": "Create Transition Order",
                "type": "API",
                "description": "Remove old plan, add new plan",
                "api_call": "POST /v1/orders",
            },
        ]

    guide = f"""
## Workflow Configuration: {workflow_name}

### Overview
{description}

### Trigger Configuration
- **Type:** {trigger_type}
{"- **Schedule:** " + schedule + " (cron expression)" if schedule else ""}
{"- **Event:** " + event_type if event_type else ""}

---

### Workflow API Configuration

**API Endpoint:** POST /workflows

```json
{json.dumps(workflow_config, indent=2)}
```

---

### Recommended Workflow Tasks

"""

    if example_tasks:
        for i, task in enumerate(example_tasks, 1):
            guide += f"""
**Task {i}: {task["name"]}**
- Type: {task["type"]}
- Description: {task["description"]}
{"- API Call: `" + task.get("api_call", "") + "`" if task.get("api_call") else ""}
{"- Condition: `" + task.get("condition", "") + "`" if task.get("condition") else ""}
"""

    guide += f"""
---

### Implementation Steps (Zuora UI)

1. Navigate to **Settings > Workflows**
2. Click **"Create Workflow"**
3. Enter Name: `{workflow_name}`
4. Select Trigger Type: `{trigger_type}`
{"5. Configure Schedule: `" + schedule + "`" if schedule else ""}
{"5. Configure Event Type: `" + event_type + "`" if event_type else ""}
6. Add workflow tasks as outlined above
7. Configure error handling (retry logic, failure notifications)
8. Test in sandbox before enabling in production
9. Set status to **Active**

---

### Cron Expression Reference

| Expression | Meaning |
|------------|---------|
| `0 0 1 * *` | 1st of every month at midnight |
| `0 0 1 5 *` | May 1st at midnight |
| `0 0 * * *` | Every day at midnight |
| `0 */6 * * *` | Every 6 hours |

---

### Available Event Types

| Event | Description |
|-------|-------------|
| `UsageRecordCreation` | When usage records are created |
| `PrepaidBalanceLow` | When prepaid balance falls below threshold |
| `PrepaidBalanceDepleted` | When prepaid balance reaches zero |
| `PaymentSuccess` | Successful payment processed |
| `InvoicePosted` | Invoice is posted |

---

### Prerequisites

- [ ] Zuora Admin access with Workflow permissions
- [ ] Workflow feature enabled on your tenant
{"- [ ] Events enabled for: " + event_type if event_type else ""}
{"- [ ] Cron schedule validated" if schedule else ""}

---

### Validation Checklist

- [ ] Workflow appears in Settings > Workflows
- [ ] Trigger configuration matches requirements
- [ ] Test execution completes successfully
- [ ] Error handling tasks configured
- [ ] Production activation after testing
"""

    # Store advisory payload
    payloads = tool_context.agent.state.get(ADVISORY_PAYLOADS_STATE_KEY) or []
    payloads.append(
        {
            "type": "workflow",
            "name": workflow_name,
            "config": workflow_config,
            "endpoint": "POST /workflows",
        }
    )
    tool_context.agent.state.set(ADVISORY_PAYLOADS_STATE_KEY, payloads)

    return guide


@tool
def generate_notification_rule(
    rule_name: str,
    event_type: str,
    description: str,
    channel_type: Literal["Email", "Callout", "Webhook"] = "Callout",
    endpoint_url: Optional[str] = None,
) -> str:
    """
    Generate a Zuora Notification Rule configuration.

    ADVISORY ONLY - does not create the notification rule.

    Args:
        rule_name: Name for the notification rule
        event_type: Zuora event type (e.g., "UsageRecordCreation", "PrepaidBalanceLow")
        description: Description of the notification purpose
        channel_type: Delivery channel (Email, Callout, Webhook)
        endpoint_url: URL for Callout/Webhook channels (optional - workflow can auto-generate)

    Returns:
        Complete notification rule configuration with implementation guide.
    """
    notification_config = {
        "name": rule_name,
        "description": description,
        "eventType": event_type,
        "active": True,
        "channel": {"type": channel_type},
    }

    if channel_type in ["Callout", "Webhook"]:
        notification_config["channel"]["endpoint"] = (
            endpoint_url or "{{WORKFLOW_CALLOUT_URL}}"
        )
        notification_config["channel"]["retryCount"] = 3
        notification_config["channel"]["retryInterval"] = 60

    guide = f"""
## Notification Rule Configuration: {rule_name}

### Overview
{description}

### Event Type: `{event_type}`
This notification triggers when the specified event occurs in Zuora.

---

### Configuration Payload

**API Endpoint:** POST /notifications/notification-definitions

```json
{json.dumps(notification_config, indent=2)}
```

---

### Available Event Types Reference

| Event Type | Description | Common Use |
|------------|-------------|------------|
| `UsageRecordCreation` | Usage records uploaded | Trigger balance check |
| `PrepaidBalanceLow` | Balance below threshold | Auto top-up trigger |
| `PrepaidBalanceDepleted` | Balance reaches zero | Urgent top-up or block |
| `PaymentSuccess` | Payment processed | Confirmation |
| `PaymentFailure` | Payment failed | Retry or alert |
| `InvoicePosted` | Invoice posted | Billing notification |
| `SubscriptionCreated` | New subscription | Welcome workflow |
| `SubscriptionCancelled` | Subscription ended | Retention workflow |

---

### Implementation Steps (Zuora UI)

1. Go to **Settings > Notifications > Notification Definitions**
2. Click **"Add Notification"**
3. Select Event Type: `{event_type}`
4. Enter Name: `{rule_name}`
5. Configure delivery channel: `{channel_type}`
"""

    if channel_type in ["Callout", "Webhook"]:
        guide += f"""
6. For Callout/Webhook:
   - Endpoint URL: `{endpoint_url or "{{Will be generated by workflow}}"}`
   - Authentication: Configure as needed
   - Retry Count: 3
   - Retry Interval: 60 seconds
"""
    elif channel_type == "Email":
        guide += """
6. For Email:
   - Select or create email template
   - Configure recipient list
   - Set merge fields for personalization
"""

    guide += f"""
7. Set up filters if needed (e.g., specific accounts only)
8. Activate the notification

---

### Connecting to Workflow

To trigger a workflow from this notification:

1. Create the workflow first (see `generate_workflow_config`)
2. Set workflow trigger type to **"Callout"**
3. Copy the workflow's callout URL
4. Use that URL as this notification's endpoint

**Workflow Callout URL Format:**
```
https://workflows.zuora.com/api/v1/workflows/{{workflow_id}}/trigger
```

---

### Event Payload Example

When `{event_type}` triggers, Zuora sends data like:

```json
{{
    "eventType": "{event_type}",
    "accountId": "2c92c0f...",
    "accountNumber": "A-00001",
    "subscriptionId": "2c92c0f...",
    "timestamp": "2024-01-15T10:30:00Z",
    // Event-specific fields...
}}
```

---

### Prerequisites

- [ ] Notifications feature enabled
- [ ] `{channel_type}` channel configured
{"- [ ] Endpoint accessible: " + endpoint_url if endpoint_url else "- [ ] Workflow created and callout URL obtained"}
- [ ] Admin permissions for notification setup

---

### Validation Checklist

- [ ] Notification appears in Settings > Notifications
- [ ] Test event triggers notification
- [ ] Delivery channel receives notification
- [ ] Workflow executes (if configured)
- [ ] Error handling configured (retry logic)
"""

    return guide


@tool
def generate_order_payload(
    action_type: Literal["AddProduct", "RemoveProduct", "Transition", "TopUp"],
    subscription_number: Optional[str] = None,
    add_rate_plan_id: Optional[str] = None,
    remove_rate_plan_id: Optional[str] = None,
    effective_date: Optional[str] = None,
    charge_overrides: Optional[Dict[str, Any]] = None,
    use_field_lookup_for_price: bool = False,
    field_lookup_expression: Optional[str] = None,
) -> str:
    """
    Generate a Zuora Orders API payload for subscription modifications.

    ADVISORY ONLY - does not execute the order.

    Args:
        action_type: Type of order action (AddProduct, RemoveProduct, Transition, TopUp)
        subscription_number: Existing subscription to modify
        add_rate_plan_id: Product Rate Plan ID to add
        remove_rate_plan_id: Product Rate Plan ID to remove
        effective_date: When the change takes effect (YYYY-MM-DD)
        charge_overrides: Optional charge-level overrides (price, quantity, etc.)
        use_field_lookup_for_price: Use fieldLookup for dynamic pricing
        field_lookup_expression: The fieldLookup expression (e.g., "Account.DepositAmount__c")

    Returns:
        Complete Orders API payload with implementation guide.
    """
    order_payload = {
        "orderDate": effective_date or "{{REPLACE_WITH_DATE}}",
        "existingAccountNumber": "{{REPLACE_WITH_ACCOUNT_NUMBER}}",
        "subscriptions": [],
    }

    subscription_action = {
        "subscriptionNumber": subscription_number
        or "{{REPLACE_WITH_SUBSCRIPTION_NUMBER}}",
        "orderActions": [],
    }

    # Build charge override if using fieldLookup
    actual_charge_overrides = charge_overrides
    if use_field_lookup_for_price and field_lookup_expression:
        actual_charge_overrides = actual_charge_overrides or {}
        actual_charge_overrides["pricing"] = [
            {"currency": "USD", "price": f"fieldLookup('{field_lookup_expression}')"}
        ]

    if action_type == "AddProduct" and add_rate_plan_id:
        add_action = {
            "type": "AddProduct",
            "triggerDates": [
                {
                    "name": "ContractEffective",
                    "triggerDate": effective_date or "{{DATE}}",
                },
                {
                    "name": "ServiceActivation",
                    "triggerDate": effective_date or "{{DATE}}",
                },
            ],
            "addProduct": {"productRatePlanId": add_rate_plan_id},
        }
        if actual_charge_overrides:
            add_action["addProduct"]["chargeOverrides"] = [actual_charge_overrides]
        subscription_action["orderActions"].append(add_action)

    elif action_type == "RemoveProduct" and remove_rate_plan_id:
        subscription_action["orderActions"].append(
            {
                "type": "RemoveProduct",
                "triggerDates": [
                    {
                        "name": "ContractEffective",
                        "triggerDate": effective_date or "{{DATE}}",
                    }
                ],
                "removeProduct": {"ratePlanId": remove_rate_plan_id},
            }
        )

    elif action_type == "Transition":
        # Remove old, add new in single order
        if remove_rate_plan_id:
            subscription_action["orderActions"].append(
                {
                    "type": "RemoveProduct",
                    "triggerDates": [
                        {
                            "name": "ContractEffective",
                            "triggerDate": effective_date or "{{DATE}}",
                        }
                    ],
                    "removeProduct": {"ratePlanId": remove_rate_plan_id},
                }
            )
        if add_rate_plan_id:
            add_action = {
                "type": "AddProduct",
                "triggerDates": [
                    {
                        "name": "ContractEffective",
                        "triggerDate": effective_date or "{{DATE}}",
                    },
                    {
                        "name": "ServiceActivation",
                        "triggerDate": effective_date or "{{DATE}}",
                    },
                ],
                "addProduct": {"productRatePlanId": add_rate_plan_id},
            }
            if actual_charge_overrides:
                add_action["addProduct"]["chargeOverrides"] = [actual_charge_overrides]
            subscription_action["orderActions"].append(add_action)

    elif action_type == "TopUp":
        # Add prepaid balance via order
        add_action = {
            "type": "AddProduct",
            "triggerDates": [
                {
                    "name": "ContractEffective",
                    "triggerDate": effective_date or "{{DATE}}",
                },
                {
                    "name": "ServiceActivation",
                    "triggerDate": effective_date or "{{DATE}}",
                },
            ],
            "addProduct": {
                "productRatePlanId": add_rate_plan_id or "{{PREPAID_RATE_PLAN_ID}}"
            },
        }
        if actual_charge_overrides:
            add_action["addProduct"]["chargeOverrides"] = [actual_charge_overrides]
        subscription_action["orderActions"].append(add_action)

    order_payload["subscriptions"].append(subscription_action)

    # Build action description
    action_desc = {
        "AddProduct": "add a new rate plan",
        "RemoveProduct": "remove an existing rate plan",
        "Transition": "transition between rate plans (remove old, add new)",
        "TopUp": "add prepaid balance to subscription",
    }.get(action_type, action_type)

    guide = f"""
## Orders API Payload: {action_type}

### Overview
This order will {action_desc}.

---

### API Endpoint
**POST /v1/orders**

### Request Payload
```json
{json.dumps(order_payload, indent=2)}
```

---

### Placeholders to Replace

| Placeholder | Description |
|-------------|-------------|
| `{{{{REPLACE_WITH_ACCOUNT_NUMBER}}}}` | Target account number (e.g., A-00001) |
| `{{{{REPLACE_WITH_SUBSCRIPTION_NUMBER}}}}` | Subscription to modify (e.g., S-00001) |
| `{{{{DATE}}}}` | Effective date in YYYY-MM-DD format |
{"| `{{{{PREPAID_RATE_PLAN_ID}}}}` | Rate plan ID for prepaid charge |" if action_type == "TopUp" else ""}

---
"""

    if use_field_lookup_for_price:
        guide += f"""
### Dynamic Pricing with fieldLookup

This order uses `fieldLookup('{field_lookup_expression}')` for dynamic pricing.

**How it works:**
1. Zuora reads the value from `{field_lookup_expression}` at order execution time
2. The value is used as the price for the charge
3. Each customer can have different amounts stored in their Account

**Prerequisite:** Ensure the custom field exists on the Account object:
```json
{{
    "name": "{field_lookup_expression.split(".")[-1] if field_lookup_expression else "FIELD_NAME"}",
    "label": "Dynamic Amount Field",
    "type": "Number"
}}
```

---
"""

    guide += f"""
### Implementation Steps

1. **Identify the subscription and account**
   - Get account number from Zuora
   - Get subscription number for the target subscription

2. **Get the Product Rate Plan ID(s)**
   - Use `list_zuora_products` to find products
   - Use `get_zuora_product` to get rate plan IDs

3. **Replace all placeholders** in the payload

4. **Preview the order** (recommended):
   ```
   POST /v1/orders/preview
   ```
   This shows the impact without executing.

5. **Execute the order**:
   ```
   POST /v1/orders
   ```

6. **Verify order status** and subscription changes

---

### For Scheduled {action_type}

To execute this order on a specific date automatically:

1. Create a **Scheduled Workflow** for the target date
2. Add an **API task** with this order payload
3. The workflow executes the order automatically

Example: Transition on May 1st
- Workflow schedule: `0 0 1 5 *` (cron for May 1st midnight)
- API task: POST /v1/orders with this payload

---

### Order Action Types Reference

| Action | Use Case |
|--------|----------|
| `AddProduct` | Add new rate plan to subscription |
| `RemoveProduct` | Remove rate plan from subscription |
| `UpdateProduct` | Change existing rate plan attributes |
| `Suspend` | Temporarily suspend subscription |
| `Resume` | Resume suspended subscription |
| `OwnerTransfer` | Transfer subscription to new account |

---

### Charge Overrides
{"**Configured overrides:**" if actual_charge_overrides else "No charge overrides configured."}
{json.dumps(actual_charge_overrides, indent=2) if actual_charge_overrides else "Add overrides to customize pricing, quantity, or custom fields."}

---

### Validation Checklist

- [ ] Order preview shows expected changes
- [ ] Account number is valid
- [ ] Subscription number is valid
- [ ] Rate plan IDs exist in catalog
- [ ] Effective date is valid (not in the past for most actions)
- [ ] Order status is "Completed" after execution
- [ ] Subscription shows correct rate plans
- [ ] Billing preview matches expectations
"""

    return guide


@tool
def explain_field_lookup(
    object_type: Literal["Account", "Subscription", "RatePlan", "Charge"],
    field_name: str,
    use_case: str,
) -> str:
    """
    Explain how to use Zuora's fieldLookup() function for dynamic pricing.

    Args:
        object_type: The Zuora object containing the field (Account, Subscription, etc.)
        field_name: Name of the custom field to look up (e.g., "TopUpAmount__c")
        use_case: Description of the pricing scenario

    Returns:
        Complete guide on implementing fieldLookup() for the scenario.
    """
    expression = f"fieldLookup('{object_type.lower()}', '{field_name}')"
    alt_expression = f"fieldLookup('{object_type}.{field_name}')"

    guide = f"""
## fieldLookup() Implementation Guide

### Use Case
{use_case}

### Expression Syntax

**Standard Syntax:**
```
{expression}
```

**Alternative Syntax:**
```
{alt_expression}
```

Both syntaxes work - use whichever your Zuora version supports.

---

### How fieldLookup() Works

The `fieldLookup()` function retrieves a value from a related object at **runtime**.
This enables dynamic, customer-specific pricing without creating multiple rate plans.

**Key Benefits:**
- One rate plan, many prices
- Customer-specific pricing
- No rate plan proliferation
- Easy updates via Account/Subscription fields

---

### Supported Objects and Common Fields

| Object | Common Fields | Use Case |
|--------|---------------|----------|
| `Account` | `TopUpAmount__c`, `DiscountPct__c`, `NegotiatedPrice__c` | Customer-specific pricing |
| `Subscription` | `PricingTier__c`, `ContractedRate__c` | Subscription-level pricing |
| `RatePlan` | Custom fields on rate plan | Plan-specific values |
| `Charge` | Custom fields on charge | Charge-specific values |

---

### Step-by-Step Implementation

**Step 1: Create the Custom Field**

Navigate to **Settings > Custom Fields > {object_type}**

**API Endpoint:** POST /v1/settings/custom-fields

```json
{{
    "name": "{field_name}",
    "label": "{field_name.replace("__c", "").replace("_", " ")}",
    "type": "Number",
    "description": "Custom field for {use_case}"
}}
```

**Via Zuora UI:**
1. Go to Settings > Billing Settings > Custom Fields
2. Select object: {object_type}
3. Click "Add Custom Field"
4. Name: `{field_name}`
5. Type: Number (for prices)
6. Save

---

**Step 2: Use in Charge Pricing**

When creating or updating a Product Rate Plan Charge:

```json
{{
    "name": "Dynamic Price Charge",
    "type": "Recurring",
    "model": "Flat Fee Pricing",
    "billingPeriod": "Month",
    "pricing": [
        {{
            "currency": "USD",
            "price": "{expression}"
        }}
    ]
}}
```

---

**Step 3: Populate the Field Value**

**Via API (Update {object_type}):**

```json
PUT /v1/accounts/{{accountId}}

{{
    "{field_name}": 500.00
}}
```

**Via Zuora UI:**
1. Navigate to the {object_type} record
2. Click Edit
3. Find field: {field_name}
4. Enter value
5. Save

---

### Examples for Your Use Case

**Example 1: Customer-Specific Top-Up Amount**
```
fieldLookup('account', 'TopUpAmount__c')
```
- Each customer has their own top-up amount
- Set on account creation or update anytime
- Billing uses this amount automatically

**Example 2: Negotiated Pricing**
```
fieldLookup('account', 'NegotiatedPrice__c')
```
- Store contracted price per customer
- Charge uses this instead of list price
- Update field to change customer's price

**Example 3: Deposit Amount for Prepaid**
```
fieldLookup('account', 'DepositAmount__c')
```
- Customer's deposit stored on account
- When adding Prepaid charge, use deposit as initial balance
- Order reads from this field at execution time

---

### Using in Multi-Attribute Pricing

Combine with conditions for complex pricing:

```json
{{
    "pricing": [
        {{
            "currency": "USD",
            "price": "fieldLookup('account', 'Region__c') == 'US' ? fieldLookup('account', 'US_Price__c') : fieldLookup('account', 'Intl_Price__c')"
        }}
    ]
}}
```

**Note:** Complex expressions may require Workflow or external calculation.

---

### Validation Checklist

- [ ] Custom field created on {object_type}
- [ ] Field API name matches exactly: `{field_name}`
- [ ] Field type is appropriate (Number for prices)
- [ ] Field is populated with test value
- [ ] Charge uses fieldLookup() in pricing
- [ ] Test subscription created
- [ ] Invoice shows correct dynamic price

---

### Troubleshooting

| Issue | Solution |
|-------|----------|
| "Field not found" error | Check field API name matches exactly (case-sensitive) |
| Price is $0 | Field value is null or 0; set a default value |
| Wrong value used | Verify object type (Account vs Subscription) |
| Calculation error | Validate expression syntax |
| Field not updating | Check if field is on correct object |

---

### Best Practices

1. **Naming Convention**: Use `__c` suffix for custom fields
2. **Default Values**: Set defaults to avoid null pricing
3. **Documentation**: Document which fields affect pricing
4. **Testing**: Always test with sample subscriptions first
5. **Audit Trail**: Track field changes for billing accuracy
"""

    return guide


@tool
def generate_multi_attribute_pricing(
    charge_name: str,
    attributes: List[Dict[str, Any]],
    base_price: float,
) -> str:
    """
    Generate Multi-Attribute Pricing (MAP) configuration.

    ADVISORY ONLY - provides configuration guidance.

    Args:
        charge_name: Name of the charge
        attributes: List of pricing attributes with their values
                   Example: [{"name": "Region", "values": ["US", "EU", "APAC"]}]
        base_price: Base price before attribute adjustments

    Returns:
        Complete MAP configuration guide.
    """
    # Build price matrix example
    price_matrix = {}
    for i, attr in enumerate(attributes):
        for j, val in enumerate(attr.get("values", [])):
            key = f"{attr['name']}:{val}"
            # Simple example multipliers
            multiplier = 1.0 + (0.1 * i) + (0.05 * j)
            price_matrix[key] = round(base_price * multiplier, 2)

    # Build combined matrix if multiple attributes
    combined_matrix = {}
    if len(attributes) >= 2:
        for val1 in attributes[0].get("values", []):
            for val2 in attributes[1].get("values", []):
                key = f"{attributes[0]['name']}:{val1}|{attributes[1]['name']}:{val2}"
                idx1 = attributes[0]["values"].index(val1)
                idx2 = attributes[1]["values"].index(val2)
                multiplier = 1.0 + (0.1 * idx1) + (0.15 * idx2)
                combined_matrix[key] = round(base_price * multiplier, 2)

    guide = f"""
## Multi-Attribute Pricing Configuration

### Charge: {charge_name}
### Base Price: ${base_price:,.2f}

---

### Pricing Attributes

"""
    for attr in attributes:
        guide += f"**{attr['name']}**: {', '.join(attr.get('values', []))}\n"

    guide += f"""
---

### Single-Attribute Price Matrix

| Attribute Value | Price |
|-----------------|-------|
"""
    for key, price in price_matrix.items():
        guide += f"| {key} | ${price:,.2f} |\n"

    if combined_matrix:
        guide += f"""
---

### Combined Price Matrix (Example)

| Combination | Price |
|-------------|-------|
"""
        for key, price in list(combined_matrix.items())[:8]:  # Show first 8
            guide += f"| {key} | ${price:,.2f} |\n"

        if len(combined_matrix) > 8:
            guide += f"| ... | ({len(combined_matrix) - 8} more combinations) |\n"

    guide += f"""
---

### Implementation Option 1: Zuora UI (Native MAP)

**Best for:** Simple matrices with 2-3 attributes

1. Navigate to **Product Catalog**
2. Select or create the charge: `{charge_name}`
3. Choose pricing model: **"Multi-Attribute Pricing"**
4. Define attributes:
"""
    for attr in attributes:
        guide += f"   - {attr['name']}: {', '.join(attr.get('values', []))}\n"

    guide += f"""
5. Enter prices in the matrix grid
6. Set default price for unmatched combinations: ${base_price:,.2f}
7. Save and verify

---

### Implementation Option 2: fieldLookup() + Custom Fields

**Best for:** Dynamic pricing, customer-specific values

**Step 1: Create Account Custom Fields**
"""
    for attr in attributes:
        guide += f"""
```json
{{
    "name": "{attr["name"]}__c",
    "label": "Customer {attr["name"]}",
    "type": "Picklist",
    "picklistValues": {json.dumps(attr.get("values", []))}
}}
```
"""

    guide += f"""
**Step 2: Create Price Lookup Field**
```json
{{
    "name": "CalculatedPrice__c",
    "label": "Calculated Price",
    "type": "Number",
    "description": "Pre-calculated price based on attributes"
}}
```

**Step 3: Use in Charge Pricing**
```json
{{
    "pricing": [{{
        "currency": "USD",
        "price": "fieldLookup('account', 'CalculatedPrice__c')"
    }}]
}}
```

**Note:** You'll need a workflow or external process to calculate and update `CalculatedPrice__c` based on the attribute combination.

---

### Implementation Option 3: Separate Rate Plans

**Best for:** Clear separation, simple management

Create separate rate plans for each combination:
"""
    if combined_matrix:
        for i, (key, price) in enumerate(list(combined_matrix.items())[:4]):
            guide += f"- `{charge_name} - {key.replace('|', ' / ')}`: ${price:,.2f}\n"
        if len(combined_matrix) > 4:
            guide += f"- ... ({len(combined_matrix) - 4} more rate plans)\n"
    else:
        for key, price in price_matrix.items():
            guide += f"- `{charge_name} - {key}`: ${price:,.2f}\n"

    guide += f"""
**Pros:**
- Simple, explicit pricing
- Easy to understand
- No formula complexity

**Cons:**
- Many rate plans to manage ({len(combined_matrix) if combined_matrix else len(price_matrix)} in this case)
- Updates require changing each plan
- Can become unwieldy with many combinations

---

### Recommended Approach

Based on {len(attributes)} attribute(s) with {sum(len(a.get("values", [])) for a in attributes)} total values:

"""
    total_combinations = 1
    for attr in attributes:
        total_combinations *= len(attr.get("values", [1]))

    if total_combinations <= 9:
        guide += """**Recommendation: Use Native Multi-Attribute Pricing in Zuora UI**
- Native support for matrix pricing
- Easy to manage and update
- Built-in validation
"""
    elif total_combinations <= 25:
        guide += """**Recommendation: Use fieldLookup() with a price lookup table**
- More flexible than native MAP
- Can handle more combinations
- Requires workflow for price calculation
"""
    else:
        guide += """**Recommendation: Consider external pricing engine**
- Too many combinations for manual management
- Integrate with external CPQ or pricing service
- Use API to calculate and pass price at subscription time
"""

    guide += f"""
---

### Validation Checklist

- [ ] Attributes defined correctly
- [ ] All price combinations entered
- [ ] Default price set for unmatched
- [ ] Test subscription with each combination
- [ ] Invoices show correct prices
- [ ] Price changes apply to new subscriptions only
"""

    return guide


@tool
def generate_custom_field_definition(
    field_name: str,
    field_label: str,
    field_type: Literal["Text", "Number", "Date", "Picklist", "Checkbox"],
    object_type: Literal["Account", "Subscription", "RatePlan", "Charge"] = "Account",
    description: Optional[str] = None,
    required: bool = False,
    default_value: Optional[str] = None,
    picklist_values: Optional[List[str]] = None,
) -> str:
    """
    Generate a custom field definition for Zuora objects.

    ADVISORY ONLY - provides configuration guidance.

    Args:
        field_name: API name for the field (e.g., "TopUpAmount__c")
        field_label: Display label for the field
        field_type: Data type (Text, Number, Date, Picklist, Checkbox)
        object_type: Object to add the field to (Account, Subscription, etc.)
        description: Field description
        required: Whether the field is required
        default_value: Default value for the field
        picklist_values: List of values for Picklist type

    Returns:
        Complete custom field definition with implementation guide.
    """
    # Ensure field name has __c suffix
    api_name = field_name if field_name.endswith("__c") else f"{field_name}__c"

    field_config = {
        "name": api_name,
        "label": field_label,
        "type": field_type,
        "object": object_type,
        "description": description or f"Custom field for {field_label}",
        "required": required,
    }

    if default_value is not None:
        field_config["defaultValue"] = default_value

    if field_type == "Picklist" and picklist_values:
        field_config["picklistValues"] = picklist_values

    guide = f"""
## Custom Field Definition: {api_name}

### Overview
Adding custom field `{api_name}` to the `{object_type}` object.

---

### Field Configuration

```json
{json.dumps(field_config, indent=2)}
```

---

### Implementation Steps (Zuora UI)

1. Navigate to **Settings > Billing Settings > Custom Fields**
2. Select object: **{object_type}**
3. Click **"Add Custom Field"**
4. Configure:
   - **Label:** {field_label}
   - **API Name:** {api_name}
   - **Type:** {field_type}
   - **Required:** {"Yes" if required else "No"}
{"   - **Default Value:** " + str(default_value) if default_value else ""}
{"   - **Picklist Values:** " + ", ".join(picklist_values) if picklist_values else ""}
5. Add description: {description or "N/A"}
6. Click **Save**

---

### API Creation (Alternative)

**Endpoint:** POST /v1/settings/custom-fields

```json
{json.dumps(field_config, indent=2)}
```

---

### Using the Custom Field

**1. In API Calls:**

When creating or updating a {object_type}:
```json
{{
    "{api_name}": {'"value"' if field_type == "Text" else "500.00" if field_type == "Number" else '"2024-01-01"' if field_type == "Date" else "true" if field_type == "Checkbox" else '"Option1"'}
}}
```

**2. In fieldLookup():**

Reference this field in charge pricing:
```
fieldLookup('{object_type.lower()}', '{api_name}')
```

Or alternative syntax:
```
fieldLookup('{object_type}.{api_name}')
```

**3. In Workflows:**

Access via merge fields:
```
{{{{{object_type.lower()}.{api_name}}}}}
```

---

### Field Type Guidelines

| Type | Use For | Example Values |
|------|---------|----------------|
| `Text` | Names, codes, descriptions | "Premium", "A-123" |
| `Number` | Prices, quantities, thresholds | 500.00, 1000 |
| `Date` | Start dates, end dates | "2024-01-01" |
| `Picklist` | Fixed set of options | "US", "EU", "APAC" |
| `Checkbox` | Yes/No flags | true, false |

---

### Common Custom Fields for Billing

| Field Name | Type | Object | Purpose |
|------------|------|--------|---------|
| `TopUpAmount__c` | Number | Account | Customer-specific top-up amount |
| `MinimumThreshold__c` | Number | Account | Balance threshold for auto top-up |
| `DepositAmount__c` | Number | Account | Initial deposit for prepaid |
| `NegotiatedPrice__c` | Number | Account | Contracted price |
| `PricingTier__c` | Picklist | Account | Customer pricing tier |
| `Region__c` | Picklist | Account | Geographic region for pricing |

---

### Validation Checklist

- [ ] Field created in Zuora UI or via API
- [ ] API name is exactly: `{api_name}`
- [ ] Field type is: `{field_type}`
- [ ] Field appears on {object_type} records
- [ ] Can set/update value via UI
- [ ] Can set/update value via API
- [ ] fieldLookup() returns correct value (if used in pricing)
"""

    return guide


@tool(context=True)
def validate_billing_configuration(
    tool_context: ToolContext,
    config_type: Literal["prepaid", "workflow", "notification", "order", "all"] = "all",
) -> str:
    """
    Validate advisory payloads generated during the session.

    Args:
        config_type: Type of configuration to validate (prepaid, workflow, notification, order, all)

    Returns:
        Validation results and recommendations.
    """
    payloads = tool_context.agent.state.get(ADVISORY_PAYLOADS_STATE_KEY) or []

    if not payloads:
        return """## Validation Results

No advisory configurations have been generated in this session yet.

**Available configuration tools:**
- `generate_prepaid_config` - Prepaid with Drawdown setup
- `generate_workflow_config` - Workflow automation
- `generate_notification_rule` - Event notifications
- `generate_order_payload` - Orders API payloads
- `generate_custom_field_definition` - Custom fields
- `explain_field_lookup` - Dynamic pricing with fieldLookup()
- `generate_multi_attribute_pricing` - Multi-attribute pricing

Generate configurations first, then run validation to check for issues."""

    if config_type != "all":
        matching = [p for p in payloads if p.get("type") == config_type]
    else:
        matching = payloads

    if not matching:
        return f"No {config_type} configurations found in this session. Generate a configuration first using the appropriate tool."

    validation_results = []

    for payload in matching:
        result = {
            "name": payload.get("name", "Unknown"),
            "type": payload.get("type", "unknown"),
            "status": "Valid",
            "issues": [],
            "recommendations": [],
        }

        config = payload.get("config", {})
        p_type = payload.get("type", "")

        # Validation rules by type
        if p_type == "workflow":
            if not config.get("name"):
                result["issues"].append("Missing workflow name")
                result["status"] = "Has Issues"
            if config.get("type") == "Scheduled" and not config.get("schedule", {}).get(
                "cronExpression"
            ):
                result["issues"].append("Scheduled workflow missing cron expression")
                result["status"] = "Has Issues"
            if config.get("type") == "Event" and not config.get("event", {}).get(
                "eventType"
            ):
                result["issues"].append("Event workflow missing event type")
                result["status"] = "Has Issues"
            if result["status"] == "Valid":
                result["recommendations"].append(
                    "Test workflow in sandbox before production"
                )

        elif p_type == "notification":
            if not config.get("eventType"):
                result["issues"].append("Missing event type")
                result["status"] = "Has Issues"
            if config.get("channel", {}).get("type") in ["Callout", "Webhook"]:
                endpoint = config.get("channel", {}).get("endpoint", "")
                if "{{" in endpoint:
                    result["recommendations"].append(
                        "Replace placeholder endpoint URL before creating"
                    )

        elif p_type == "prepaid_config":
            prepaid = payload.get("prepaid_charge", {})
            if not prepaid.get("prepaidUOM"):
                result["issues"].append("Missing prepaid UOM")
                result["status"] = "Has Issues"
            if not prepaid.get("prepaidQuantity"):
                result["issues"].append("Missing prepaid quantity")
                result["status"] = "Has Issues"
            drawdown = payload.get("drawdown_charge", {})
            if drawdown.get("usageType") != "DRAWDOWN":
                result["recommendations"].append(
                    "Ensure drawdown charge has usageType: DRAWDOWN"
                )

        elif p_type == "order":
            if not config.get("subscriptions"):
                result["issues"].append("Missing subscription actions")
                result["status"] = "Has Issues"

        validation_results.append(result)

    # Build output
    output = f"""## Validation Results

**Configurations Validated:** {len(validation_results)}
**Status Summary:**
- Valid: {sum(1 for r in validation_results if r["status"] == "Valid")}
- Has Issues: {sum(1 for r in validation_results if r["status"] == "Has Issues")}

---

"""

    for r in validation_results:
        status_icon = "OK" if r["status"] == "Valid" else "ISSUES"
        output += f"### {r['name']} ({r['type']}) - [{status_icon}]\n\n"

        if r["issues"]:
            output += "**Issues:**\n"
            for issue in r["issues"]:
                output += f"- {issue}\n"
            output += "\n"

        if r["recommendations"]:
            output += "**Recommendations:**\n"
            for rec in r["recommendations"]:
                output += f"- {rec}\n"
            output += "\n"

        if not r["issues"] and not r["recommendations"]:
            output += "Configuration looks good!\n\n"

    output += """---

### Next Steps

1. Review any issues identified above
2. Use the appropriate generation tool to fix issues
3. Follow implementation steps in each configuration guide
4. Test in sandbox before production deployment
"""

    return output


@tool
def get_zuora_documentation(
    topic: Literal[
        "prepaid",
        "workflow",
        "notification",
        "orders",
        "fieldLookup",
        "multiAttributePricing",
        "customFields",
    ],
) -> str:
    """
    Get Zuora documentation links and quick reference for a topic.

    Args:
        topic: The Zuora feature to get documentation for

    Returns:
        Documentation links and quick reference guide.
    """
    docs = {
        "prepaid": {
            "title": "Prepaid with Drawdown",
            "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/Prepaid_with_Drawdown",
            "summary": "Wallet-based billing where customers prepay for usage credits that are drawn down over time.",
            "key_concepts": [
                "Prepaid Balance: The wallet containing credits/units",
                "Drawdown: Usage that depletes the prepaid balance",
                "Overage: Handling when balance is depleted (block, allow, or auto top-up)",
                "Rollover: Carrying unused credits forward to next period",
                "Top-Up: Adding more credits to the prepaid balance",
            ],
            "api_endpoints": [
                "POST /v1/object/product-rate-plan-charge (create prepaid charge)",
                "GET /v1/prepaid-balances?accountId={id} (check balance)",
                "POST /v1/usage (record drawdown usage)",
                "POST /v1/orders (add top-up)",
            ],
        },
        "workflow": {
            "title": "Zuora Workflows",
            "url": "https://knowledgecenter.zuora.com/Zuora_Central_Platform/Workflow",
            "summary": "Automation engine for business processes in Zuora. Supports scheduled, event-driven, and callout triggers.",
            "key_concepts": [
                "Triggers: Scheduled (cron), Event-based, or Callout (webhook)",
                "Tasks: API calls, conditions, delays, iterations, custom code",
                "Error Handling: Retry logic, failure notifications, fallback paths",
                "Testing: Sandbox execution before production activation",
            ],
            "api_endpoints": [
                "POST /workflows (create workflow)",
                "GET /workflows (list workflows)",
                "POST /workflows/{id}/run (manual trigger)",
                "GET /workflows/{id}/runs (execution history)",
            ],
        },
        "notification": {
            "title": "Notifications",
            "url": "https://knowledgecenter.zuora.com/Zuora_Central_Platform/Notifications",
            "summary": "Event-driven notifications via email, callout, or webhook when specific events occur in Zuora.",
            "key_concepts": [
                "Event Types: System events that trigger notifications",
                "Email Templates: Customizable notification content with merge fields",
                "Callouts: Webhook-style HTTP notifications to external systems",
                "Filters: Conditional notification triggering based on criteria",
            ],
            "api_endpoints": [
                "POST /notifications/notification-definitions (create rule)",
                "GET /notifications/notification-definitions (list rules)",
                "GET /notifications/notification-history (view history)",
            ],
        },
        "orders": {
            "title": "Orders API",
            "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Manage_subscription_transactions/Orders",
            "summary": "Unified API for subscription lifecycle management including add, remove, update, suspend, and resume.",
            "key_concepts": [
                "Order Actions: AddProduct, RemoveProduct, UpdateProduct, Suspend, Resume",
                "Trigger Dates: ContractEffective, ServiceActivation, CustomerAcceptance",
                "Charge Overrides: Custom pricing, quantity, custom fields on add",
                "Preview: Test orders before execution to see impact",
            ],
            "api_endpoints": [
                "POST /v1/orders (create order)",
                "POST /v1/orders/preview (preview order impact)",
                "GET /v1/orders/{order-number} (get order details)",
                "GET /v1/orders (list orders)",
            ],
        },
        "fieldLookup": {
            "title": "fieldLookup() Function",
            "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/Pricing_formulas",
            "summary": "Dynamic pricing function that retrieves values from related objects at runtime.",
            "key_concepts": [
                "Syntax: fieldLookup('object', 'fieldName') or fieldLookup('Object.FieldName')",
                "Supported Objects: Account, Subscription, RatePlan, Charge",
                "Use Cases: Customer-specific pricing, regional pricing, contracted rates",
                "Custom Fields: Required on target object for dynamic values",
            ],
            "api_endpoints": [
                "POST /v1/settings/custom-fields (create custom field)",
                "PUT /v1/accounts/{id} (update account with field value)",
                "Pricing configuration in Product Rate Plan Charge",
            ],
        },
        "multiAttributePricing": {
            "title": "Multi-Attribute Pricing",
            "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/Multi-Attribute_Pricing",
            "summary": "Matrix-based pricing with multiple dimensions (e.g., region, tier, volume).",
            "key_concepts": [
                "Attributes: Pricing dimensions like Region, Tier, Size",
                "Price Matrix: Combinations of attribute values mapped to prices",
                "Default Pricing: Fallback when no exact match found",
                "Override: Subscription-level price changes",
            ],
            "api_endpoints": [
                "Product Rate Plan Charge configuration",
                "Charge override in Orders API",
            ],
        },
        "customFields": {
            "title": "Custom Fields",
            "url": "https://knowledgecenter.zuora.com/Zuora_Central_Platform/Custom_Fields",
            "summary": "Extend Zuora objects with custom data fields for your business needs.",
            "key_concepts": [
                "Objects: Account, Subscription, RatePlan, Charge, Invoice, etc.",
                "Field Types: Text, Number, Date, Picklist, Checkbox",
                "Naming: API names end with __c suffix",
                "Usage: Available in API, UI, Reports, fieldLookup()",
            ],
            "api_endpoints": [
                "POST /v1/settings/custom-fields (create field)",
                "GET /v1/settings/custom-fields (list fields)",
                "Include in object CRUD operations",
            ],
        },
    }

    doc = docs.get(topic, {})

    output = f"""
## Zuora Documentation: {doc.get("title", topic)}

### Official Documentation
**URL:** {doc.get("url", "URL not available")}

---

### Summary
{doc.get("summary", "No summary available")}

---

### Key Concepts

"""
    for concept in doc.get("key_concepts", []):
        output += f"- **{concept.split(':')[0]}**: {':'.join(concept.split(':')[1:]).strip() if ':' in concept else concept}\n"

    output += """
---

### Related API Endpoints

"""
    for endpoint in doc.get("api_endpoints", []):
        output += f"- `{endpoint}`\n"

    output += f"""
---

### Related Tools in Billing Architect

"""
    tool_mapping = {
        "prepaid": [
            "generate_prepaid_config",
            "generate_workflow_config",
            "generate_order_payload",
        ],
        "workflow": ["generate_workflow_config", "generate_notification_rule"],
        "notification": ["generate_notification_rule", "generate_workflow_config"],
        "orders": ["generate_order_payload", "generate_workflow_config"],
        "fieldLookup": [
            "explain_field_lookup",
            "generate_prepaid_config",
            "generate_order_payload",
        ],
        "multiAttributePricing": [
            "generate_multi_attribute_pricing",
            "explain_field_lookup",
        ],
        "customFields": ["generate_custom_field_definition", "explain_field_lookup"],
    }

    for tool_name in tool_mapping.get(topic, []):
        output += f"- `{tool_name}`\n"

    output += """
---

### Getting Help

For more detailed information:
1. Visit the Zuora Knowledge Center link above
2. Check Zuora API Reference: https://developer.zuora.com/api-references/
3. Contact Zuora Support for account-specific questions
"""

    return output
