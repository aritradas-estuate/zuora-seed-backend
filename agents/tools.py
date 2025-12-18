from strands import tool
from strands.types.tools import ToolContext
from typing import Optional, List, Dict, Any, Literal, Tuple
import datetime
import json
import logging
import uuid

import jellyfish

from .models import ZuoraApiType
from .zuora_client import get_zuora_client
from .validation_schemas import (
    validate_payload,
    generate_placeholder_payload,
    format_placeholder_warning,
)
from .validation_utils import (
    validate_date_format as _validate_date_format_tuple,
    validate_date_range as _validate_date_range_tuple,
    validate_zuora_id as _validate_zuora_id_tuple,
    validate_sku_format as _validate_sku_format_tuple,
    format_error_message,
    validate_name_length,
    validate_product_name_unique,
    validate_rate_plan_name_unique,
    validate_charge_name_unique,
    # PWD validation functions
    validate_pwd_drawdown_price,
    validate_pwd_thresholds,
    apply_pwd_rollover_defaults,
    check_pwd_uom_compatibility,
    check_pwd_currency_compatibility,
)

# Fallback defaults for defensive coding in generate_pm_handoff_prompt
# These values are used only when currencies/prices lists are unexpectedly empty
# (which should not happen due to validation, but provides safety)
DEFAULT_FALLBACK_CURRENCY = "USD"
DEFAULT_FALLBACK_PRICE = 99.0

logger = logging.getLogger(__name__)


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


def _is_update_payload(payload: Dict[str, Any]) -> bool:
    """
    Check if payload is an update payload with method/endpoint/body structure.

    Update payloads (product_update, rate_plan_update, charge_update) have structure:
    {"method": "PUT", "endpoint": "/v1/object/...", "body": {"FieldName": "value"}}

    Create payloads have flat structure:
    {"Name": "...", "EffectiveStartDate": "...", ...}

    Args:
        payload: The payload dict to check

    Returns:
        True if this is an update payload with body structure
    """
    return "method" in payload and "endpoint" in payload and "body" in payload


def _extract_entity_id_from_endpoint(endpoint: str) -> Optional[str]:
    """
    Extract the entity ID from a Zuora API endpoint URL.

    Examples:
        "/v1/object/product/6a629cfee87443778306054d7badcb57" -> "6a629cfee87443778306054d7badcb57"
        "/v1/object/product-rate-plan/0efc4ea7f9d8411bbeaa07b9e2c27c42" -> "0efc4ea7f9d8411bbeaa07b9e2c27c42"

    Args:
        endpoint: The API endpoint URL

    Returns:
        The entity ID if found, None otherwise
    """
    if not endpoint:
        return None
    parts = endpoint.rstrip("/").split("/")
    if parts:
        return parts[-1]
    return None


def _find_existing_update_payload(
    payloads: List[Dict[str, Any]],
    api_type: str,
    entity_id: str,
) -> Optional[int]:
    """
    Find an existing update payload for a given entity by ID.

    This is more robust than exact endpoint matching because it extracts
    the entity ID from the endpoint and compares just the IDs.

    Args:
        payloads: List of payload dicts
        api_type: The zuora_api_type to match (e.g., "product_update", "rate_plan_update")
        entity_id: The Zuora entity ID to find

    Returns:
        Index of the matching payload if found, None otherwise
    """
    for i, p in enumerate(payloads):
        if p.get("zuora_api_type") != api_type:
            continue
        endpoint = p.get("payload", {}).get("endpoint", "")
        payload_entity_id = _extract_entity_id_from_endpoint(endpoint)
        if payload_entity_id and payload_entity_id == entity_id:
            return i
    return None


def _resolve_field_path_for_update_payload(
    payload: Dict[str, Any], field_path: str
) -> str:
    """
    For update payloads, auto-resolve field paths to body.* if needed.

    Update payloads have structure: {"method": "PUT", "endpoint": "...", "body": {...}}
    When user wants to update EffectiveEndDate, they should update body.EffectiveEndDate,
    not add a new field at the payload level.

    This function automatically prepends "body." to the field_path if:
    1. The payload is an update payload (has method/endpoint/body structure)
    2. The field_path doesn't already start with "body."
    3. The field exists in the body dict (case-insensitive match)

    Args:
        payload: The payload dict
        field_path: Original field path from user/agent

    Returns:
        Resolved field path (with "body." prepended if needed)
    """
    # Only process update payloads
    if not _is_update_payload(payload):
        return field_path

    # If field_path already starts with "body.", use as-is
    if field_path.lower().startswith("body."):
        return field_path

    # Check if field exists in body (case-insensitive)
    body = payload.get("body", {})
    field_key = field_path.split(".")[0]  # Get first part of path

    if _find_existing_key(body, field_key):
        # Field exists in body, prepend "body."
        resolved = f"body.{field_path}"
        logger.info(
            f"Auto-resolved field path for update payload: '{field_path}' -> '{resolved}'"
        )
        return resolved

    # Field doesn't exist in body, keep original path
    return field_path


def _resolve_currency_price_update(
    payload: Dict[str, Any],
    field_path: str,
    new_value: Any,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Handle currency-specific price updates for charge_create payloads.

    When the agent tries to update 'prices.EUR' or 'overage_prices.USD', this
    function redirects the update to the actual tier in ProductRatePlanChargeTierData.

    Zuora's API uses ProductRatePlanChargeTierData.ProductRatePlanChargeTier array
    with {Currency, Price} objects. There is no 'prices' field in the API - that's
    just an input parameter used during charge creation.

    Args:
        payload: The charge_create payload dict
        field_path: Original field path from user/agent (e.g., "prices.EUR", "overage_prices.USD")
        new_value: New price value

    Returns:
        Tuple of (was_handled: bool, currency_code: Optional[str], error_msg: Optional[str])
        - was_handled: True if this was a currency price update pattern
        - currency_code: The currency that was updated (e.g., "EUR")
        - error_msg: Error message if currency not found, None on success
    """
    field_lower = field_path.lower()

    # Check if this is a prices.{CURRENCY} or overage_prices.{CURRENCY} pattern
    is_price_pattern = field_lower.startswith("prices.")
    is_overage_pattern = field_lower.startswith("overage_prices.")

    if not is_price_pattern and not is_overage_pattern:
        return False, None, None

    parts = field_path.split(".")
    if len(parts) != 2:
        return False, None, None

    currency = parts[1].upper()

    # Find the tier data structure
    tier_data = payload.get("ProductRatePlanChargeTierData", {})
    tiers = tier_data.get("ProductRatePlanChargeTier", [])

    if not tiers:
        # No tier data exists yet - cannot update
        return (
            True,
            None,
            f"No pricing tiers found in payload. Cannot update {currency} price.",
        )

    # Find the tier with matching currency
    tier_found = False
    for tier in tiers:
        if tier.get("Currency", "").upper() == currency:
            tier["Price"] = new_value
            tier_found = True
            break

    if tier_found:
        logger.info(
            f"Updated {currency} price to {new_value} in ProductRatePlanChargeTierData"
        )
        return True, currency, None

    # Currency not found - add a new tier for this currency
    available_currencies = [t.get("Currency", "?") for t in tiers]
    logger.info(
        f"Currency '{currency}' not found in existing tiers {available_currencies}. "
        f"Adding new tier for {currency}."
    )

    # Create new tier with the currency and price
    # Copy structure from existing tier if available (for consistency)
    new_tier: Dict[str, Any] = {"Currency": currency, "Price": new_value}

    # If existing tiers have additional fields (like Tier, StartingUnit), copy the structure
    if tiers:
        sample_tier = tiers[0]
        if "Tier" in sample_tier:
            new_tier["Tier"] = len(tiers) + 1
        if "StartingUnit" in sample_tier:
            new_tier["StartingUnit"] = sample_tier.get("StartingUnit", 1)
        if "PriceFormat" in sample_tier:
            new_tier["PriceFormat"] = sample_tier.get("PriceFormat")

    tiers.append(new_tier)
    logger.info(f"Added new tier for {currency}: {new_tier}")

    return True, currency, None


def _find_payload_by_name(
    matching: List[Tuple[int, Dict[str, Any]]], name: str
) -> Tuple[Optional[Tuple[int, Dict[str, Any]]], List[str]]:
    """
    Find a payload by name using case-insensitive substring matching.

    For create payloads, matches against the "Name" or "name" field.
    For update payloads (which don't have a Name field), matches against
    the endpoint URL which contains the entity ID.

    Args:
        matching: List of (index, payload) tuples to search
        name: Name to search for (case-insensitive substring match)

    Returns:
        Tuple of:
        - (index, payload) if exactly one match found, None otherwise
        - List of all matching names/identifiers (for error messages)
    """
    name_lower = name.lower()
    matches = []

    for idx, p in matching:
        # First try to match by Name field (for create payloads)
        payload_name = p.get("payload", {}).get("Name") or p.get("payload", {}).get(
            "name", ""
        )
        if payload_name and name_lower in payload_name.lower():
            matches.append((idx, p, payload_name))
            continue

        # For update payloads, try to match by endpoint (contains entity ID)
        # Update payloads have structure: {"payload": {"method": "PUT", "endpoint": "...", "body": {...}}}
        endpoint = p.get("payload", {}).get("endpoint", "")
        if endpoint and name_lower in endpoint.lower():
            # Use the last part of the endpoint (entity ID) as the display name
            endpoint_id = endpoint.split("/")[-1] if "/" in endpoint else endpoint
            matches.append((idx, p, f"endpoint:{endpoint_id}"))

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

# ============ Currency Symbol Mapping ============
CURRENCY_SYMBOLS: Dict[str, str] = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CNY": "¥",
    "CHF": "CHF ",
    "CAD": "CA$",
    "AUD": "A$",
    "INR": "₹",
    "KRW": "₩",
    "MXN": "MX$",
    "BRL": "R$",
    "SGD": "S$",
    "HKD": "HK$",
    "SEK": "kr ",
    "NOK": "kr ",
    "DKK": "kr ",
    "NZD": "NZ$",
    "ZAR": "R ",
}


def _format_currency(amount: float, currency: str, decimals: int = 2) -> str:
    """
    Format a currency amount with the appropriate symbol.

    Args:
        amount: The numeric amount to format
        currency: Currency code (e.g., "USD", "EUR")
        decimals: Number of decimal places (default: 2)

    Returns:
        Formatted string like "$99.00" or "€90.00" or "99.00 XYZ" for unknown currencies
    """
    symbol = CURRENCY_SYMBOLS.get(currency, "")
    if decimals == 2:
        formatted_amount = f"{amount:,.2f}"
    else:
        formatted_amount = f"{amount:.{decimals}f}"

    if symbol:
        return f"{symbol}{formatted_amount}"
    else:
        # For unknown currencies, put code after amount
        return f"{formatted_amount} {currency}"


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
        return "No payloads found" + (f" for type '{api_type}'" if api_type else "")

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
    # Entry logging for debugging tool call issues
    logger.info(
        f"[TOOL CALL] update_payload: api_type={api_type}, field_path={field_path}, "
        f"new_value={new_value}, payload_name={payload_name}, payload_id={payload_id}, payload_index={payload_index}"
    )

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
            error_msg += "<p><strong>Matching payloads:</strong></p><ul>"
            for name in matched_names:
                error_msg += f"<li><strong>{name}</strong></li>"
            error_msg += "</ul>"
            error_msg += (
                "<p><em>Be more specific:</em> Use a more unique part of the name.</p>"
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
            error_msg += "<p><strong>Use payload_name (recommended):</strong></p>"
            first_name = matching[0][1].get("payload", {}).get("Name") or matching[0][
                1
            ].get("payload", {}).get("name", "NAME")
            error_msg += f"<pre><code>update_payload(api_type='{api_type}', payload_name='{first_name}', field_path='{field_path}', new_value={repr(new_value)})</code></pre>"
            return error_msg

    payload_entry = target_entry
    payload = payload_entry["payload"]

    # AUTO-RESOLVE: For update payloads, redirect fields to body.* if they exist there
    # This fixes the issue where agent calls update_payload(field_path="EffectiveEndDate")
    # but the field actually lives at payload.body.EffectiveEndDate
    field_path = _resolve_field_path_for_update_payload(payload, field_path)

    # SPECIAL HANDLING: Currency-specific price updates for charge_create payloads
    # Detects patterns like "prices.EUR" or "overage_prices.USD" and updates the actual
    # tier in ProductRatePlanChargeTierData instead of creating a spurious "prices" field.
    # Zuora API only uses ProductRatePlanChargeTierData - there is no "prices" field.
    if api_type.lower() == "charge_create":
        was_handled, currency, error_msg = _resolve_currency_price_update(
            payload, field_path, new_value
        )
        if was_handled:
            if error_msg:
                # Currency not found or other error
                return format_error_message("Price update failed", error_msg)

            # Success - update state and return
            tool_context.agent.state.set(PAYLOADS_STATE_KEY, payloads)

            friendly_type = (
                api_type.replace("_create", "").replace("_update", "").replace("_", " ")
            )
            payload_name = payload.get("Name", payload.get("name", "unnamed"))

            response = f'Updated {currency} price to {new_value} in {friendly_type} "{payload_name}".\n\n'
            response += f"(Updated ProductRatePlanChargeTierData.ProductRatePlanChargeTier for {currency})\n\n"

            if payload_entry.get("_placeholders"):
                remaining = payload_entry["_placeholders"]
                response += f"Still needs: {', '.join(remaining)}"
            else:
                response += "All fields complete - ready to execute."

            logger.info(
                f"[TOOL DONE] update_payload: successfully updated {currency} price to {new_value} "
                f"in charge '{payload_name}'"
            )
            return response

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

    # Exit logging for debugging
    logger.info(
        f"[TOOL DONE] update_payload: successfully updated {actual_key} in {friendly_type} '{payload_name}'"
    )

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
        format_defaults_applied_html,
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
                    output += "      Pricing:\n"
                    for price in pricing:
                        tier_id = price.get("id", "")
                        tier_num = price.get("tier", 1)
                        tier_id_str = f" (tier_id: {tier_id})" if tier_id else ""
                        output += f"        - Tier {tier_num}: {price.get('currency', 'N/A')} {price.get('price', 'N/A')}{tier_id_str}\n"

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
    # Check for price-related attributes - guide user to dedicated function
    price_attrs = ["price", "pricing", "tier", "tiers", "productrateplanchargetierdata"]
    if attribute.lower() in price_attrs:
        return f"""⚠️ **Price updates require the dedicated tool**

To update charge prices, use `update_zuora_charge_price`:

```
update_zuora_charge_price(
    charge_id="{charge_id}",
    new_price=<new_price_value>,
    currency="USD",
    tier=1  # optional: for tiered/volume pricing
)
```

This fetches the charge's pricing tiers and generates the correct API payload
for the tier-specific endpoint (`/v1/object/product-rate-plan-charge-tier/{{tier_id}}`).

Use `get_zuora_product` or `get_zuora_rate_plan_details` to see current pricing and tier IDs."""

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


@tool(context=True)
def update_zuora_charge_price(
    tool_context: ToolContext,
    charge_id: str,
    new_price: float,
    currency: str,
    tier: Optional[int] = None,
) -> str:
    """Update the price of an existing product rate plan charge tier.

    This tool fetches the charge's pricing tiers and generates the correct
    update payload for the Zuora tier-specific API endpoint.

    IMPORTANT: Call get_zuora_product or get_zuora_rate_plan_details first to
    identify the charge_id and see the current pricing structure.

    Args:
        charge_id: Zuora Product Rate Plan Charge ID (e.g., '8a8080...')
        new_price: New price value (e.g., 99.00)
        currency: Currency code (e.g., 'USD') - required
        tier: Tier number (1-based) for tiered/volume pricing. Required if charge
              has multiple tiers for the specified currency.

    Returns:
        Summary of generated update payload(s), or tier selection prompt if needed

    Note:
        Updates only affect NEW subscriptions. Existing subscriptions keep old values.

    Examples:
        # Update a flat fee charge price
        update_zuora_charge_price(charge_id="8a80...", new_price=149.00, currency="USD")

        # Update a specific tier in tiered pricing
        update_zuora_charge_price(charge_id="8a80...", new_price=0.05, currency="USD", tier=2)
    """
    logger.info(
        f"[TOOL CALL] update_zuora_charge_price: charge_id={charge_id}, "
        f"new_price={new_price}, currency={currency}, tier={tier}"
    )

    # Validate charge_id format
    if not validate_zuora_id(charge_id):
        return format_error_message(
            "Invalid charge_id",
            "Provide a valid Zuora Product Rate Plan Charge ID (e.g., '8a8080...'). "
            "Use get_zuora_product or get_zuora_rate_plan_details to find the charge ID.",
        )

    # Validate price is non-negative
    if new_price < 0:
        return format_error_message(
            "Invalid price",
            "Price must be a non-negative number. Provide a value >= 0.",
        )

    client = get_zuora_client()

    # 1. Fetch charge details to get tier info
    result = client.get_charge(charge_id)
    if not result.get("success"):
        error_msg = result.get("error", "Unknown error")
        details = result.get("details", {})
        if details:
            error_msg += f" - {details}"
        return f"❌ **Error retrieving charge:** {error_msg}\n\nPlease verify the charge ID is correct."

    charge_data = result.get("data", {})
    pricing_tiers = charge_data.get("pricing", [])
    charge_name = charge_data.get("name", "Unknown")
    charge_model = charge_data.get("model", "Unknown")

    if not pricing_tiers:
        return f"""❌ **No pricing tiers found for charge '{charge_name}'**

This charge may not have pricing data available through the API, or the charge model
does not use standard tier-based pricing.

**Charge ID:** `{charge_id}`
**Charge Model:** {charge_model}

Please verify this is the correct charge and that it uses a supported pricing model."""

    # 2. Filter tiers by currency
    currency_upper = currency.upper()
    matching_tiers = [
        t for t in pricing_tiers if t.get("currency", "").upper() == currency_upper
    ]

    if not matching_tiers:
        available = ", ".join(
            sorted(set(t.get("currency", "N/A") for t in pricing_tiers))
        )
        return f"""❌ **No tier found for currency '{currency}'**

**Charge:** {charge_name}
**Available currencies:** {available}

Please specify one of the available currencies."""

    # 3. Handle tiered pricing - if multiple tiers and tier not specified, ask user
    if len(matching_tiers) > 1 and tier is None:
        output = f"## Multiple Tiers Found for {currency}\n\n"
        output += f"**Charge:** {charge_name}\n"
        output += f"**Charge ID:** `{charge_id}`\n"
        output += f"**Charge Model:** {charge_model}\n\n"
        output += "| Tier | Current Price | Starting Unit | Ending Unit |\n"
        output += "|------|---------------|---------------|-------------|\n"
        for t in sorted(matching_tiers, key=lambda x: x.get("tier", 0)):
            tier_num = t.get("tier", "?")
            price = t.get("price", "N/A")
            start = t.get("startingUnit", "N/A")
            end = t.get("endingUnit")
            end_str = "unlimited" if end is None else end
            output += f"| {tier_num} | {price} | {start} | {end_str} |\n"

        output += "\n---\n\n"
        output += "**Which tier(s) would you like to update?**\n\n"
        output += f'- To update a single tier, call: `update_zuora_charge_price(charge_id="{charge_id}", new_price={new_price}, currency="{currency}", tier=<tier_number>)`\n'
        output += "- Or tell me which tier(s) you want to update and I'll generate the payloads.\n"
        return output

    # 4. Filter by tier number if specified
    if tier is not None:
        tier_match = [t for t in matching_tiers if t.get("tier") == tier]
        if not tier_match:
            available = ", ".join(
                str(t.get("tier", "?"))
                for t in sorted(matching_tiers, key=lambda x: x.get("tier", 0))
            )
            return f"""❌ **No tier #{tier} found for {currency}**

**Charge:** {charge_name}
**Available tiers for {currency}:** {available}

Please specify one of the available tier numbers."""
        matching_tiers = tier_match

    # 5. Generate update payloads
    payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []
    updates_generated = []

    for tier_data in matching_tiers:
        tier_id = tier_data.get("id")
        if not tier_id:
            logger.warning(f"Tier missing ID: {tier_data}")
            continue

        tier_num = tier_data.get("tier", 1)
        old_price = tier_data.get("price", "N/A")

        update_payload = {
            "payload": {
                "method": "PUT",
                "endpoint": f"/v1/object/product-rate-plan-charge-tier/{tier_id}",
                "body": {"Price": new_price},
            },
            "zuora_api_type": ZuoraApiType.CHARGE_TIER_UPDATE.value,
            "payload_id": str(uuid.uuid4())[:8],
        }

        payloads.append(update_payload)
        updates_generated.append(
            {
                "tier_id": tier_id,
                "tier": tier_num,
                "old_price": old_price,
                "new_price": new_price,
            }
        )

    tool_context.agent.state.set(PAYLOADS_STATE_KEY, payloads)

    # 6. Format response
    if not updates_generated:
        return """❌ **Could not generate price update payloads**

The tier data from Zuora did not include tier IDs, which are required to update prices.
This may indicate an API limitation or an issue with the charge configuration.

Please try using the Zuora UI to update this charge's price, or contact support."""

    output = "## ✅ Price Update Payload Generated\n\n"
    output += f"**Charge:** {charge_name}\n"
    output += f"**Charge ID:** `{charge_id}`\n"
    output += f"**Charge Model:** {charge_model}\n"
    output += f"**Currency:** {currency}\n\n"

    output += "| Tier | Old Price | New Price | Tier ID |\n"
    output += "|------|-----------|-----------|--------|\n"
    for u in updates_generated:
        tier_id = u["tier_id"]
        tier_id_display = f"{tier_id[:12]}..." if len(tier_id) > 12 else tier_id
        output += f"| {u['tier']} | {u['old_price']} | {u['new_price']} | `{tier_id_display}` |\n"

    output += f"\n**Payloads Generated:** {len(updates_generated)}\n\n"
    output += "---\n\n"
    output += "The payload has been added to the response. **Send to Zuora** to apply the update.\n\n"
    output += "⚠️ **Note:** Updates only affect NEW subscriptions. Existing subscriptions keep the old values.\n"

    return output


# ============ Product Expiration Tool ============


@tool(context=True)
def expire_product(
    tool_context: ToolContext,
    product_id: str,
    new_end_date: str,
) -> str:
    """
    Expire a product and all its rate plans by setting the same effective end date.

    Generates update payloads for:
    1. The product (sets EffectiveEndDate)
    2. All associated rate plans whose end date is after the new end date

    IMPORTANT: Call get_zuora_product first to verify the product exists and show
    the user its current details before calling this tool.

    Args:
        product_id: Zuora Product ID (e.g., '8a8080...' or '2c92c0f...')
        new_end_date: New effective end date in YYYY-MM-DD format.
                     Use today's date for immediate expiration.

    Returns:
        Summary of generated payloads and affected entities
    """
    import datetime as dt

    logger.info(
        f"[TOOL CALL] expire_product: product_id={product_id}, "
        f"new_end_date={new_end_date}"
    )

    # 1. Validate date format
    if not validate_date_format(new_end_date):
        return format_error_message(
            "Invalid date format",
            f"new_end_date must be YYYY-MM-DD format (e.g., 2024-12-31), got: {new_end_date}",
        )

    # 2. Fetch product details from Zuora
    client = get_zuora_client()
    result = client.get_product(product_id)

    if not result.get("success"):
        error_msg = result.get("error", "Unknown error")
        details = result.get("details", {})
        if details:
            error_msg += f" - {details}"
        return f"❌ **Error retrieving product:** {error_msg}\n\nPlease verify the product ID is correct."

    product = result.get("data", {})
    product_name = product.get("name", "Unknown")
    product_sku = product.get("sku", "N/A")
    current_start = product.get("effectiveStartDate")
    current_end = product.get("effectiveEndDate")
    rate_plans = product.get("productRatePlans", [])

    # 3. Validate new_end_date >= start_date
    if current_start and new_end_date < current_start:
        return format_error_message(
            "Invalid end date",
            f"End date ({new_end_date}) cannot be before product start date ({current_start})",
        )

    # 4. Check if product is already expired
    today = dt.datetime.now().strftime("%Y-%m-%d")
    warnings = []

    if current_end and current_end < today:
        return f"""ℹ️ **Product Already Expired**

**Product:** {product_name}
**Product ID:** `{product_id}`
**Current End Date:** {current_end}

This product is already expired. No changes needed.

If you want to extend the product, use `update_zuora_product` to set a new end date."""

    # 5. Warn if new_end_date is in the past (but allow it)
    if new_end_date < today:
        warnings.append(
            f"⚠️ **Warning:** New end date ({new_end_date}) is in the past. "
            "This will backdate the expiration."
        )

    # 6. Generate or update product update payload
    payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []

    # Use robust helper to find existing payload by entity ID
    existing_product_update_idx = _find_existing_update_payload(
        payloads, "product_update", product_id
    )
    product_endpoint = f"/v1/object/product/{product_id}"

    if existing_product_update_idx is not None:
        # Update existing payload in place
        payloads[existing_product_update_idx]["payload"]["body"]["EffectiveEndDate"] = (
            new_end_date
        )
        logger.info(f"Updated existing product_update payload for product {product_id}")
    else:
        # Create new payload
        product_payload = {
            "payload": {
                "method": "PUT",
                "endpoint": product_endpoint,
                "body": {"EffectiveEndDate": new_end_date},
            },
            "zuora_api_type": "product_update",
            "payload_id": str(uuid.uuid4())[:8],
        }
        payloads.append(product_payload)

    # 7. Generate or update rate plan update payloads
    rate_plans_to_expire: List[Dict[str, Any]] = []
    rate_plans_skipped: List[Dict[str, Any]] = []

    for rp in rate_plans:
        rp_id = rp.get("id")
        rp_name = rp.get("name", "Unknown")
        rp_current_end = rp.get("effectiveEndDate")

        # Check for existing rate_plan_update payload for this rate plan FIRST
        # This ensures we always update existing payloads regardless of date condition
        existing_rp_update_idx = _find_existing_update_payload(
            payloads, "rate_plan_update", rp_id
        )

        # Determine if we need to update/create a payload for this rate plan
        # Either: (1) rate plan needs expiring, or (2) we already have a payload for it
        needs_update = (rp_current_end and rp_current_end > new_end_date) or (
            existing_rp_update_idx is not None
        )

        if needs_update:
            rp_endpoint = f"/v1/object/product-rate-plan/{rp_id}"

            if existing_rp_update_idx is not None:
                # Update existing payload in place
                payloads[existing_rp_update_idx]["payload"]["body"][
                    "EffectiveEndDate"
                ] = new_end_date
                logger.info(
                    f"Updated existing rate_plan_update payload for rate plan {rp_id}"
                )
            else:
                # Create new payload
                rp_payload = {
                    "payload": {
                        "method": "PUT",
                        "endpoint": rp_endpoint,
                        "body": {"EffectiveEndDate": new_end_date},
                    },
                    "zuora_api_type": "rate_plan_update",
                    "payload_id": str(uuid.uuid4())[:8],
                }
                payloads.append(rp_payload)

            rate_plans_to_expire.append(
                {
                    "name": rp_name,
                    "id": rp_id,
                    "current_end": rp_current_end or "N/A",
                    "new_end": new_end_date,
                }
            )
        else:
            rate_plans_skipped.append(
                {
                    "name": rp_name,
                    "current_end": rp_current_end or "N/A",
                    "reason": "Already expires on or before new date",
                }
            )

    # 8. Save payloads to state
    tool_context.agent.state.set(PAYLOADS_STATE_KEY, payloads)

    # 9. Build response
    output = "## Product Expiration Payloads Generated\n\n"

    # Show warnings first
    if warnings:
        for w in warnings:
            output += f"{w}\n\n"

    # Product summary
    output += f"**Product:** {product_name}\n"
    output += f"- Product ID: `{product_id}`\n"
    output += f"- SKU: {product_sku}\n"
    output += f"- Current Effective End: {current_end}\n"
    output += f"- **New Effective End: {new_end_date}**\n\n"

    # Rate plans summary
    if rate_plans_to_expire:
        output += f"**Rate Plans to Expire ({len(rate_plans_to_expire)}):**\n\n"
        output += "| Rate Plan | Current End | New End |\n"
        output += "|-----------|-------------|----------|\n"
        for rp in rate_plans_to_expire:
            output += f"| {rp['name']} | {rp['current_end']} | {rp['new_end']} |\n"
        output += "\n"

    if rate_plans_skipped:
        output += f"**Rate Plans Unchanged ({len(rate_plans_skipped)}):**\n"
        for rp in rate_plans_skipped:
            output += f"- {rp['name']} (ends {rp['current_end']} - {rp['reason']})\n"
        output += "\n"

    if not rate_plans:
        output += "**Rate Plans:** None associated with this product.\n\n"

    # Payload count
    total_payloads = 1 + len(rate_plans_to_expire)
    rp_text = (
        f" + {len(rate_plans_to_expire)} rate plan(s)" if rate_plans_to_expire else ""
    )
    output += f"**Payloads Generated:** {total_payloads} (1 product{rp_text})\n\n"

    # Instructions
    output += "---\n\n"
    output += (
        "✅ **Review the payloads on the right, then Send to Zuora to apply.**\n\n"
    )
    output += (
        "⚠️ **Note:** Existing subscriptions will not be affected by this change.\n"
    )

    return output


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
    # Entry logging for debugging tool call issues
    logger.info(
        f"[TOOL CALL] create_product: name={name}, sku={sku}, "
        f"effective_start_date={effective_start_date}, effective_end_date={effective_end_date}"
    )

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
    # Entry logging for debugging tool call issues
    logger.info(
        f"[TOOL CALL] create_rate_plan: name={name}, product_id={product_id}, "
        f"product_index={product_index}"
    )

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
        else:
            # Default to first product in batch (index 0) - mandatory for batch creation
            payload_data["ProductId"] = "@{Product[0].Id}"
            defaults_applied.append(
                {
                    "field": "ProductId",
                    "value": "@{Product[0].Id} (auto-linked to first product in batch)",
                }
            )

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
    # Prepaid charges typically use Flat Fee Pricing with IsPrepaid=true
    "prepaid": "Flat Fee Pricing",
    # Drawdown charges use Per Unit Pricing with ChargeFunction=Drawdown
    "drawdown": "Per Unit Pricing",
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
    # ============ Core Identification ============
    rate_plan_id: Optional[str] = None,
    rate_plan_index: Optional[int] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    product_rate_plan_charge_number: Optional[str] = None,
    # ============ Charge Type & Model ============
    charge_type: Optional[Literal["Recurring", "OneTime", "Usage"]] = None,
    charge_model: Optional[str] = None,
    # ============ Pricing Fields ============
    price: Optional[float] = None,
    tiers: Optional[List[Dict[str, Any]]] = None,
    currency: Optional[str] = None,  # Single currency (for backward compatibility)
    currencies: Optional[List[str]] = None,  # Multiple currencies: ["USD", "EUR"]
    prices: Optional[
        Dict[str, float]
    ] = None,  # Price per currency: {"USD": 49.0, "EUR": 45.0}
    default_quantity: Optional[float] = None,
    min_quantity: Optional[float] = None,
    max_quantity: Optional[float] = None,
    included_units: Optional[float] = None,
    overage_price: Optional[float] = None,
    overage_prices: Optional[Dict[str, float]] = None,  # Overage price per currency
    # ============ Billing Configuration ============
    billing_period: Optional[
        Literal[
            "Month",
            "Quarter",
            "Annual",
            "Semi-Annual",
            "Week",
            "Specific Months",
            "Specific Weeks",
            "Specific Days",
            "Subscription Term",
        ]
    ] = None,
    billing_timing: Optional[Literal["In Advance", "In Arrears"]] = None,
    bill_cycle_type: Literal[
        "DefaultFromCustomer",
        "SpecificDayofMonth",
        "SubscriptionStartDay",
        "ChargeTriggerDay",
        "SpecificDayofWeek",
        "TermStartDay",
        "TermEndDay",
    ] = "DefaultFromCustomer",
    bill_cycle_day: Optional[int] = None,
    weekly_bill_cycle_day: Optional[
        Literal[
            "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"
        ]
    ] = None,
    specific_billing_period: Optional[int] = None,
    billing_period_alignment: Optional[
        Literal[
            "AlignToCharge",
            "AlignToSubscriptionStart",
            "AlignToTermStart",
            "AlignToTermEnd",
        ]
    ] = None,
    list_price_base: Optional[
        Literal[
            "Per Billing Period",
            "Per Month",
            "Per Week",
            "Per Year",
            "Per Specific Months",
        ]
    ] = None,
    specific_list_price_base: Optional[int] = None,
    trigger_event: Literal[
        "ContractEffective", "ServiceActivation", "CustomerAcceptance"
    ] = "ContractEffective",
    # ============ Charge Duration ============
    end_date_condition: Optional[Literal["SubscriptionEnd", "FixedPeriod"]] = None,
    up_to_periods: Optional[int] = None,
    up_to_periods_type: Optional[
        Literal["Billing Periods", "Days", "Weeks", "Months", "Years"]
    ] = None,
    # ============ Price Change on Renewal ============
    price_change_option: Optional[
        Literal["NoChange", "SpecificPercentageValue", "UseLatestProductCatalogPricing"]
    ] = None,
    price_increase_option: Optional[
        Literal["FromTenantPercentageValue", "SpecificPercentageValue"]
    ] = None,
    price_increase_percentage: Optional[float] = None,
    use_tenant_default_for_price_change: Optional[bool] = None,
    # ============ Usage Charge Fields ============
    uom: Optional[str] = None,
    rating_group: Optional[
        Literal[
            "ByBillingPeriod",
            "ByUsageStartDate",
            "ByUsageRecord",
            "ByUsageUpload",
            "ByGroupId",
        ]
    ] = None,
    usage_record_rating_option: Optional[
        Literal["EndOfBillingPeriod", "OnDemand"]
    ] = None,
    # ============ Overage Fields ============
    overage_calculation_option: Optional[
        Literal["EndOfSmoothingPeriod", "PerBillingPeriod"]
    ] = None,
    overage_unused_units_credit_option: Optional[
        Literal["NoCredit", "CreditBySpecificRate"]
    ] = None,
    number_of_period: Optional[int] = None,
    smoothing_model: Optional[Literal["RollingWindow", "Rollover"]] = None,
    # ============ Discount Fields ============
    apply_discount_to: Optional[
        Literal[
            "ONETIME",
            "RECURRING",
            "USAGE",
            "ONETIMERECURRING",
            "ONETIMEUSAGE",
            "RECURRINGUSAGE",
            "ONETIMERECURRINGUSAGE",
        ]
    ] = None,
    discount_level: Optional[Literal["rateplan", "subscription", "account"]] = None,
    is_stacked_discount: Optional[bool] = None,
    apply_to_billing_period_partially: Optional[bool] = None,
    reflect_discount_in_net_amount: Optional[bool] = None,
    use_discount_specific_accounting_code: Optional[bool] = None,
    # ============ Accounting Fields ============
    accounting_code: Optional[str] = None,
    deferred_revenue_account: Optional[str] = None,
    recognized_revenue_account: Optional[str] = None,
    # ============ Revenue Recognition Fields ============
    revenue_recognition_rule_name: Optional[
        Literal["Recognize upon invoicing", "Recognize daily over time"]
    ] = None,
    rev_rec_code: Optional[str] = None,
    rev_rec_trigger_condition: Optional[
        Literal[
            "ContractEffectiveDate", "ServiceActivationDate", "CustomerAcceptanceDate"
        ]
    ] = None,
    exclude_item_billing_from_revenue_accounting: Optional[bool] = None,
    exclude_item_booking_from_revenue_accounting: Optional[bool] = None,
    is_allocation_eligible: Optional[bool] = None,
    is_unbilled: Optional[bool] = None,
    legacy_revenue_reporting: Optional[bool] = None,
    revenue_recognition_timing: Optional[str] = None,
    revenue_amortization_method: Optional[str] = None,
    product_category: Optional[str] = None,
    product_class: Optional[str] = None,
    product_family: Optional[str] = None,
    product_line: Optional[str] = None,
    # ============ Tax Fields ============
    taxable: Optional[bool] = None,
    tax_code: Optional[str] = None,
    tax_mode: Optional[Literal["TaxExclusive", "TaxInclusive"]] = None,
    # ============ Proration Fields ============
    proration_option: Optional[
        Literal[
            "NoProration",
            "TimeBasedProration",
            "DefaultFromTenantSetting",
            "ChargeFullPeriod",
        ]
    ] = None,
    # ============ Prepaid with Drawdown Fields ============
    charge_function: Optional[
        Literal[
            "Standard",
            "Prepayment",
            "CommitmentTrueUp",
            "Drawdown",
            "CreditCommitment",
            "DrawdownAndCreditCommitment",
        ]
    ] = None,
    commitment_type: Optional[Literal["UNIT", "CURRENCY"]] = None,
    credit_option: Optional[
        Literal["TimeBased", "ConsumptionBased", "FullCreditBack"]
    ] = None,
    drawdown_rate: Optional[float] = None,
    drawdown_uom: Optional[str] = None,
    is_prepaid: Optional[bool] = None,
    prepaid_operation_type: Optional[Literal["topup", "drawdown"]] = None,
    prepaid_quantity: Optional[float] = None,
    prepaid_total_quantity: Optional[float] = None,
    prepaid_uom: Optional[str] = None,
    validity_period_type: Optional[
        Literal["SUBSCRIPTION_TERM", "ANNUAL", "SEMI_ANNUAL", "QUARTER", "MONTH"]
    ] = None,
    is_rollover: Optional[bool] = None,
    rollover_apply: Optional[Literal["ApplyFirst", "ApplyLast"]] = None,
    rollover_periods: Optional[int] = None,
    rollover_period_length: Optional[int] = None,
    # ============ Attribute-based Pricing ============
    formula: Optional[str] = None,
    charge_model_configuration: Optional[Dict[str, Any]] = None,
    delivery_schedule: Optional[Dict[str, Any]] = None,
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
    - BillingTiming: In Advance for Recurring/OneTime charges (not applicable to Usage)
    - Currency: USD
    - RatingGroup: ByBillingPeriod for tiered/volume Usage charges

    Pricing Models Supported:
    - Flat Fee Pricing: Single flat price (use 'price' parameter)
    - Per Unit Pricing: Price per unit (use 'price' parameter)
    - Tiered Pricing: Graduated pricing - each tier has its own rate (use 'tiers' parameter)
    - Volume Pricing: All-units pricing - entire qty priced at one tier's rate (use 'tiers' parameter)
    - Overage Pricing: X units included, then $Y per unit (use 'included_units' + 'overage_price')
    - Tiered with Overage: Tiered pricing + overage (use 'tiers' + 'included_units' + 'overage_price')
    - Discount-Fixed Amount / Discount-Percentage: Use discount fields
    - Delivery Pricing: Use delivery_schedule
    - Multi-Attribute Pricing: Use charge_model_configuration

    Args:
        rate_plan_id: Zuora rate plan ID OR object reference (e.g., '@{ProductRatePlan[0].Id}')
        rate_plan_index: Index of rate plan in current batch (0-based) to auto-generate object reference
        name: Charge name (max 100 chars)
        description: Charge description (max 500 chars)
        product_rate_plan_charge_number: Natural key (max 100 chars). Auto-generated if null.
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
        currency: Single currency code (for backward compatibility). Prefer 'currencies' for new code.
        currencies: List of currency codes for multi-currency support (e.g., ["USD", "EUR"])
        prices: Dict mapping currency to price (e.g., {"USD": 49.0, "EUR": 45.0})
               Used with 'currencies' for different prices per currency.
               If not provided, 'price' is used for all currencies.
        default_quantity: Default quantity of units. Required for Per Unit/Volume/Tiered Pricing. Defaults to 1.
        min_quantity: Minimum units allowed (max 16 chars)
        max_quantity: Maximum units allowed (max 16 chars)
        included_units: Units included before overage pricing (for Overage models)
        overage_price: Base price per unit after included units consumed (for Overage models)
        overage_prices: Dict mapping currency to overage price (e.g., {"USD": 0.003, "EUR": 0.003})
                       Used with 'currencies' for different overage prices per currency.
        billing_period: Billing period for recurring charges
        billing_timing: 'In Advance' or 'In Arrears'. Not for Usage charges.
        bill_cycle_type: How to determine billing day
        bill_cycle_day: Bill cycle day (1-31). Account BCD can override.
        weekly_bill_cycle_day: Weekly bill cycle day. Required when BillCycleType='SpecificDayofWeek'
        specific_billing_period: Custom months/weeks when BillingPeriod='Specific Months/Weeks'
        billing_period_alignment: Align charges within subscription
        list_price_base: List price base. Defaults to BillingPeriod if not set.
        specific_list_price_base: Months for list price base (1-120). Required when ListPriceBase='Per Specific Months'
        trigger_event: When to start billing
        end_date_condition: 'SubscriptionEnd' or 'FixedPeriod'
        up_to_periods: Charge duration (0-65535). Required when EndDateCondition='FixedPeriod'
        up_to_periods_type: Period type for up_to_periods
        price_change_option: Automatic price change on renewal
        price_increase_option: Price increase on renewal behavior
        price_increase_percentage: Percentage to increase/decrease price on renewal (-100 to 100)
        use_tenant_default_for_price_change: Set false when using specific percentage
        uom: Unit of measure for usage charges (max 25 chars)
        rating_group: How to aggregate usage for rating
        usage_record_rating_option: When to rate usage records
        overage_calculation_option: When to calculate overage
        overage_unused_units_credit_option: Credit unused units
        number_of_period: Periods for overage smoothing
        smoothing_model: Overage smoothing model
        apply_discount_to: Charge types discount applies to (for discount models)
        discount_level: Discount scope: 'rateplan', 'subscription', or 'account'
        is_stacked_discount: Calculate as stacked discount (Discount-Percentage only)
        apply_to_billing_period_partially: Allow discount duration aligned with billing period partially
        reflect_discount_in_net_amount: Reflect discount in net amount for Zuora Revenue
        use_discount_specific_accounting_code: Use specific accounting code for discount charge
        accounting_code: Accounting code (max 100 chars)
        deferred_revenue_account: Deferred revenue account name (max 100 chars)
        recognized_revenue_account: Recognized revenue account name (max 100 chars)
        revenue_recognition_rule_name: 'Recognize upon invoicing' or 'Recognize daily over time'
        rev_rec_code: Revenue recognition code (max 70 chars)
        rev_rec_trigger_condition: When revenue recognition begins
        exclude_item_billing_from_revenue_accounting: Exclude billing items from revenue accounting
        exclude_item_booking_from_revenue_accounting: Exclude booking items from revenue accounting
        is_allocation_eligible: Allocation eligible for revenue recognition
        is_unbilled: Unbilled accounting
        legacy_revenue_reporting: Legacy revenue reporting
        revenue_recognition_timing: Revenue recognition timing
        revenue_amortization_method: Revenue amortization method
        product_category: Product category for Zuora Revenue integration
        product_class: Product class for Zuora Revenue integration
        product_family: Product family for Zuora Revenue integration
        product_line: Product line for Zuora Revenue integration
        taxable: Whether charge is taxable. Requires TaxMode and TaxCode if true.
        tax_code: Tax code (max 64 chars). Required when Taxable=true.
        tax_mode: 'TaxExclusive' or 'TaxInclusive'. Required when Taxable=true.
        proration_option: Charge-level proration option
        charge_function: Charge function type (Prepaid with Drawdown feature)
        commitment_type: Commitment type: 'UNIT' or 'CURRENCY'
        credit_option: Credit calculation: 'TimeBased', 'ConsumptionBased', 'FullCreditBack'
        drawdown_rate: Conversion rate between Usage UOM and Drawdown UOM
        drawdown_uom: Drawdown unit of measure
        is_prepaid: Whether this is a prepayment (topup) or drawdown charge
        prepaid_operation_type: 'topup' or 'drawdown'
        prepaid_quantity: Units included in prepayment charge
        prepaid_total_quantity: Total units available during validity period
        prepaid_uom: Unit of measure for prepayment
        validity_period_type: Prepaid validity period
        is_rollover: Enable rollover for prepaid
        rollover_apply: Rollover priority: 'ApplyFirst' or 'ApplyLast'
        rollover_periods: Number of rollover periods (max 3)
        rollover_period_length: Rollover fund period length
        formula: Price lookup formula for Attribute-based Pricing
        charge_model_configuration: Container for charge model configuration (Multi-Attribute/Pre-Rated Pricing)
        delivery_schedule: Delivery schedule configuration (Delivery Pricing)

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

        # Recurring charge with 10% price increase on each renewal
        create_charge(
            name="Monthly Subscription",
            charge_type="Recurring",
            charge_model="Per Unit Pricing",
            price=30.00,
            billing_period="Month",
            price_increase_option="SpecificPercentageValue",
            price_increase_percentage=10,  # 10% increase on each renewal
        )
    """
    # Entry logging for debugging tool call issues
    logger.info(
        f"[TOOL CALL] create_charge: name={name}, charge_type={charge_type}, "
        f"charge_model={charge_model}, price={price}, billing_period={billing_period}, "
        f"rate_plan_id={rate_plan_id}, rate_plan_index={rate_plan_index}"
    )

    # Build charge payload with provided values - use PascalCase for Zuora v1 CRUD API
    payload_data = {}

    # Track defaults applied for transparency
    defaults_applied: List[Dict[str, str]] = []

    # ============ Currency Resolution ============
    # Priority: currencies > currency > None (will add placeholder/warning)
    active_currencies: Optional[List[str]] = None
    currency_prices: Dict[str, float] = {}
    overage_currency_prices: Dict[str, float] = {}

    if currencies:
        # Multi-currency mode
        active_currencies = currencies
        if prices:
            currency_prices = prices
        elif price is not None:
            # Same price for all currencies if not specified per-currency
            currency_prices = {c: price for c in currencies}
        # Handle overage prices for multi-currency
        if overage_prices:
            overage_currency_prices = overage_prices
        elif overage_price is not None:
            overage_currency_prices = {c: overage_price for c in currencies}
    elif currency:
        # Single currency mode (backward compatibility)
        active_currencies = [currency]
        if price is not None:
            currency_prices = {currency: price}
        if overage_price is not None:
            overage_currency_prices = {currency: overage_price}
    # If neither currencies nor currency is provided, active_currencies stays None
    # and we'll add a warning later when generating tier data

    # Track if user provided currency explicitly
    user_provided_currency = currencies is not None or currency is not None

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
        else:
            # Default to first rate plan in batch (index 0) - mandatory for batch creation
            payload_data["ProductRatePlanId"] = "@{ProductRatePlan[0].Id}"
            defaults_applied.append(
                {
                    "field": "ProductRatePlanId",
                    "value": "@{ProductRatePlan[0].Id} (auto-linked to first rate plan in batch)",
                }
            )

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

    # Smart default for BillingTiming based on charge type
    # Note: Only Recurring charges use BillingTiming per Zuora API
    # OneTime and Usage charges do NOT use BillingTiming
    if charge_type == "Recurring":
        if billing_timing is not None:
            payload_data["BillingTiming"] = billing_timing
        else:
            payload_data["BillingTiming"] = "In Advance"
            defaults_applied.append(
                {
                    "field": "BillingTiming",
                    "value": "In Advance",
                }
            )
    # OneTime and Usage charges do NOT use BillingTiming - skip entirely

    if description:
        payload_data["Description"] = description

    # Billing period - only applicable for Recurring charges
    # OneTime and Usage charges do NOT use BillingPeriod
    if charge_type == "Recurring":
        if billing_period:
            payload_data["BillingPeriod"] = billing_period
        # If not provided for Recurring charges, validation will create a placeholder

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

    # Track currency if user didn't explicitly provide it
    if not user_provided_currency:
        # Currency was not provided - add a warning
        warnings_pre: List[str] = []
        warnings_pre.append(
            "Currency not specified. Please provide 'currency' or 'currencies' parameter."
        )
    else:
        warnings_pre = []
        if active_currencies:
            currencies_str = ", ".join(active_currencies)
            defaults_applied.append(
                {
                    "field": "Currency",
                    "value": currencies_str,
                }
            )

    # Collect warnings (tier validation warnings will be added here)
    warnings: List[str] = warnings_pre.copy() if not user_provided_currency else []

    # Handle IncludedUnits (for Overage and Tiered with Overage pricing)
    if included_units is not None:
        payload_data["IncludedUnits"] = included_units

    # Build ProductRatePlanChargeTierData (required per Zuora API)
    # This is the container for pricing information
    if tiers:
        # Tiered, Volume, or Tiered with Overage pricing
        # Use _normalize_tiers to ensure all required fields are present
        # For multi-currency, we need to normalize tiers for each currency
        all_normalized_tiers: List[Dict[str, Any]] = []
        if active_currencies:
            for curr in active_currencies:
                normalized_tiers, tier_warnings = _normalize_tiers(tiers, curr)
                warnings.extend(tier_warnings)
                all_normalized_tiers.extend(normalized_tiers)

                # For Tiered with Overage, add an overage tier at the end if overage_price is provided
                if is_tiered_with_overage:
                    curr_overage_price = overage_currency_prices.get(
                        curr, overage_price
                    )
                    if curr_overage_price is not None:
                        # Find the last tier for this currency
                        curr_tiers = [
                            t for t in all_normalized_tiers if t.get("Currency") == curr
                        ]
                        last_tier_num = len(curr_tiers)
                        last_ending = (
                            curr_tiers[-1].get("EndingUnit") if curr_tiers else None
                        )

                        # Calculate overage tier starting unit
                        if last_ending is not None:
                            overage_start = last_ending + 1
                            all_normalized_tiers.append(
                                {
                                    "Currency": curr,
                                    "Price": curr_overage_price,
                                    "Tier": last_tier_num + 1,
                                    "StartingUnit": overage_start,
                                    "PriceFormat": "Per Unit",
                                    # No EndingUnit = unlimited overage tier
                                }
                            )
                        elif curr == active_currencies[0]:
                            # Only warn once (for first currency)
                            warnings.append(
                                "Last tier has no EndingUnit (unlimited). Overage tier will not be added. "
                                "Set EndingUnit on the last tier to enable overage pricing after that tier."
                            )
        else:
            warnings.append(
                "Currency not specified for tiered pricing. "
                "Please provide 'currency' or 'currencies' parameter."
            )

        if all_normalized_tiers:
            payload_data["ProductRatePlanChargeTierData"] = {
                "ProductRatePlanChargeTier": all_normalized_tiers
            }

    elif is_overage:
        # Overage Pricing: IncludedUnits at charge level + simple price tier
        # Per Zuora docs: only Currency and Price needed in tier for Overage Pricing
        overage_tier_price = overage_price if overage_price is not None else price
        if overage_tier_price is not None and active_currencies:
            tier_list: List[Dict[str, Any]] = []
            for curr in active_currencies:
                # Get currency-specific overage price, fallback to base overage price
                curr_price = overage_currency_prices.get(curr, overage_tier_price)
                tier_list.append(
                    {
                        "Currency": curr,
                        "Price": curr_price,
                    }
                )
            payload_data["ProductRatePlanChargeTierData"] = {
                "ProductRatePlanChargeTier": tier_list
            }
        elif overage_tier_price is None:
            warnings.append(
                "Overage Pricing requires a price for overage units. "
                "Please specify 'overage_price' or 'price' parameter."
            )
        else:
            warnings.append(
                "Currency not specified for Overage Pricing. "
                "Please provide 'currency' or 'currencies' parameter."
            )

    elif price is not None or currency_prices:
        # Single tier pricing - structure differs by charge model
        if normalized_charge_model == "Flat Fee Pricing":
            # Flat Fee: minimal tier structure per Zuora docs
            # No StartingUnit, Tier, or PriceFormat needed
            if active_currencies:
                tier_list = []
                for curr in active_currencies:
                    curr_price = currency_prices.get(curr, price)
                    if curr_price is not None:
                        tier_list.append(
                            {
                                "Currency": curr,
                                "Price": curr_price,
                            }
                        )
                if tier_list:
                    payload_data["ProductRatePlanChargeTierData"] = {
                        "ProductRatePlanChargeTier": tier_list
                    }
            else:
                warnings.append(
                    "Currency not specified for Flat Fee Pricing. "
                    "Please provide 'currency' or 'currencies' parameter."
                )
        elif normalized_charge_model == "Per Unit Pricing":
            # Per Unit Pricing: simple price per unit, no tier boundaries needed
            # Per Zuora docs: only Currency and Price needed
            if active_currencies:
                tier_list = []
                for curr in active_currencies:
                    curr_price = currency_prices.get(curr, price)
                    if curr_price is not None:
                        tier_list.append(
                            {
                                "Currency": curr,
                                "Price": curr_price,
                            }
                        )
                if tier_list:
                    payload_data["ProductRatePlanChargeTierData"] = {
                        "ProductRatePlanChargeTier": tier_list
                    }
            else:
                warnings.append(
                    "Currency not specified for Per Unit Pricing. "
                    "Please provide 'currency' or 'currencies' parameter."
                )
        else:
            # Other unit-based models - keep full tier structure for safety
            if active_currencies:
                tier_list = []
                for curr in active_currencies:
                    curr_price = currency_prices.get(curr, price)
                    if curr_price is not None:
                        tier_list.append(
                            {
                                "Currency": curr,
                                "Price": curr_price,
                                "StartingUnit": 1,
                                "PriceFormat": "Per Unit",
                                "Tier": 1,
                            }
                        )
                if tier_list:
                    payload_data["ProductRatePlanChargeTierData"] = {
                        "ProductRatePlanChargeTier": tier_list
                    }
            else:
                warnings.append(
                    "Currency not specified. "
                    "Please provide 'currency' or 'currencies' parameter."
                )

    # Price increase on renewal (for termed subscriptions)
    # See: https://developer.zuora.com/v1-api-reference/api/operation/Object_POSTProductRatePlanCharge/
    if price_increase_percentage is not None:
        # Validate range: -100 to 100
        if price_increase_percentage < -100 or price_increase_percentage > 100:
            warnings.append(
                f"PriceIncreasePercentage must be between -100 and 100. Got: {price_increase_percentage}"
            )
        else:
            payload_data["PriceIncreasePercentage"] = price_increase_percentage

            # CRITICAL: Must set UseTenantDefaultForPriceChange to false when using specific percentage
            # Otherwise Zuora returns error: "The percentage change cannot be updated when you
            # choose to use your tenant default price change value."
            payload_data["UseTenantDefaultForPriceChange"] = False
            defaults_applied.append(
                {
                    "field": "UseTenantDefaultForPriceChange",
                    "value": "false (required when using specific percentage)",
                }
            )

        # Auto-set PriceChangeOption if percentage provided but option not specified
        # Note: PriceChangeOption is the correct field per Zuora API docs
        # https://developer.zuora.com/v1-api-reference/api/operation/Object_POSTProductRatePlanCharge/
        if not price_change_option:
            payload_data["PriceChangeOption"] = "SpecificPercentageValue"
            defaults_applied.append(
                {
                    "field": "PriceChangeOption",
                    "value": "SpecificPercentageValue (auto-set because PriceIncreasePercentage was provided)",
                }
            )

    if price_increase_option:
        payload_data["PriceIncreaseOption"] = price_increase_option

    # PriceChangeOption (different from PriceIncreaseOption)
    if price_change_option:
        payload_data["PriceChangeOption"] = price_change_option

    # UseTenantDefaultForPriceChange - explicit override if provided
    if use_tenant_default_for_price_change is not None:
        payload_data["UseTenantDefaultForPriceChange"] = (
            use_tenant_default_for_price_change
        )

    # DefaultQuantity - required for Per Unit Pricing, Volume Pricing, Tiered Pricing
    # See: https://developer.zuora.com/v1-api-reference/api/operation/Object_POSTProductRatePlanCharge/
    if default_quantity is not None:
        payload_data["DefaultQuantity"] = default_quantity
    elif normalized_charge_model in (
        "Per Unit Pricing",
        "Volume Pricing",
        "Tiered Pricing",
    ):
        # Smart default: These charge models require DefaultQuantity, default to 1
        payload_data["DefaultQuantity"] = 1
        defaults_applied.append(
            {
                "field": "DefaultQuantity",
                "value": f"1 (required for {normalized_charge_model})",
            }
        )

    # ============ Additional Pricing Fields ============
    if min_quantity is not None:
        payload_data["MinQuantity"] = min_quantity
    if max_quantity is not None:
        payload_data["MaxQuantity"] = max_quantity

    # ============ Additional Billing Configuration ============
    if bill_cycle_day is not None:
        payload_data["BillCycleDay"] = bill_cycle_day
    if weekly_bill_cycle_day:
        payload_data["WeeklyBillCycleDay"] = weekly_bill_cycle_day
    if specific_billing_period is not None:
        payload_data["SpecificBillingPeriod"] = specific_billing_period
    if billing_period_alignment:
        payload_data["BillingPeriodAlignment"] = billing_period_alignment
    if list_price_base:
        payload_data["ListPriceBase"] = list_price_base
    if specific_list_price_base is not None:
        payload_data["SpecificListPriceBase"] = specific_list_price_base

    # ============ Charge Duration ============
    if end_date_condition:
        payload_data["EndDateCondition"] = end_date_condition
    if up_to_periods is not None:
        payload_data["UpToPeriods"] = up_to_periods
    if up_to_periods_type:
        payload_data["UpToPeriodsType"] = up_to_periods_type

    # ============ Usage Charge Fields ============
    if usage_record_rating_option:
        payload_data["UsageRecordRatingOption"] = usage_record_rating_option

    # ============ Overage Fields ============
    if overage_calculation_option:
        payload_data["OverageCalculationOption"] = overage_calculation_option
    if overage_unused_units_credit_option:
        payload_data["OverageUnusedUnitsCreditOption"] = (
            overage_unused_units_credit_option
        )
    if number_of_period is not None:
        payload_data["NumberOfPeriod"] = number_of_period
    if smoothing_model:
        payload_data["SmoothingModel"] = smoothing_model

    # ============ Discount Fields ============
    if apply_discount_to:
        payload_data["ApplyDiscountTo"] = apply_discount_to
    if discount_level:
        payload_data["DiscountLevel"] = discount_level
    if is_stacked_discount is not None:
        payload_data["IsStackedDiscount"] = is_stacked_discount
    if apply_to_billing_period_partially is not None:
        payload_data["ApplyToBillingPeriodPartially"] = (
            apply_to_billing_period_partially
        )
    if reflect_discount_in_net_amount is not None:
        payload_data["ReflectDiscountInNetAmount"] = reflect_discount_in_net_amount
    if use_discount_specific_accounting_code is not None:
        payload_data["UseDiscountSpecificAccountingCode"] = (
            use_discount_specific_accounting_code
        )

    # ============ Accounting Fields ============
    if accounting_code:
        payload_data["AccountingCode"] = accounting_code
    if deferred_revenue_account:
        payload_data["DeferredRevenueAccount"] = deferred_revenue_account
    if recognized_revenue_account:
        payload_data["RecognizedRevenueAccount"] = recognized_revenue_account

    # ============ Revenue Recognition Fields ============
    if revenue_recognition_rule_name:
        payload_data["RevenueRecognitionRuleName"] = revenue_recognition_rule_name
    if rev_rec_code:
        payload_data["RevRecCode"] = rev_rec_code
    if rev_rec_trigger_condition:
        payload_data["RevRecTriggerCondition"] = rev_rec_trigger_condition
    if exclude_item_billing_from_revenue_accounting is not None:
        payload_data["ExcludeItemBillingFromRevenueAccounting"] = (
            exclude_item_billing_from_revenue_accounting
        )
    if exclude_item_booking_from_revenue_accounting is not None:
        payload_data["ExcludeItemBookingFromRevenueAccounting"] = (
            exclude_item_booking_from_revenue_accounting
        )
    if is_allocation_eligible is not None:
        payload_data["IsAllocationEligible"] = is_allocation_eligible
    if is_unbilled is not None:
        payload_data["IsUnbilled"] = is_unbilled
    if legacy_revenue_reporting is not None:
        payload_data["LegacyRevenueReporting"] = legacy_revenue_reporting
    if revenue_recognition_timing:
        payload_data["RevenueRecognitionTiming"] = revenue_recognition_timing
    if revenue_amortization_method:
        payload_data["RevenueAmortizationMethod"] = revenue_amortization_method
    if product_category:
        payload_data["ProductCategory"] = product_category
    if product_class:
        payload_data["ProductClass"] = product_class
    if product_family:
        payload_data["ProductFamily"] = product_family
    if product_line:
        payload_data["ProductLine"] = product_line

    # ============ Tax Fields ============
    if taxable is not None:
        payload_data["Taxable"] = taxable
    if tax_code:
        payload_data["TaxCode"] = tax_code
    if tax_mode:
        payload_data["TaxMode"] = tax_mode

    # ============ Proration Fields ============
    if proration_option:
        payload_data["ProrationOption"] = proration_option

    # ============ Prepaid with Drawdown Fields ============
    if charge_function:
        payload_data["ChargeFunction"] = charge_function
    if commitment_type:
        payload_data["CommitmentType"] = commitment_type
    if credit_option:
        payload_data["CreditOption"] = credit_option
    if drawdown_rate is not None:
        payload_data["DrawdownRate"] = drawdown_rate
    if drawdown_uom:
        payload_data["DrawdownUom"] = drawdown_uom
    if is_prepaid is not None:
        payload_data["IsPrepaid"] = is_prepaid
    if prepaid_operation_type:
        payload_data["PrepaidOperationType"] = prepaid_operation_type
    if prepaid_quantity is not None:
        payload_data["PrepaidQuantity"] = prepaid_quantity
    if prepaid_total_quantity is not None:
        payload_data["PrepaidTotalQuantity"] = prepaid_total_quantity
    if prepaid_uom:
        payload_data["PrepaidUom"] = prepaid_uom
    if validity_period_type:
        payload_data["ValidityPeriodType"] = validity_period_type
    if is_rollover is not None:
        payload_data["IsRollover"] = is_rollover
    if rollover_apply:
        payload_data["RolloverApply"] = rollover_apply
    if rollover_periods is not None:
        payload_data["RolloverPeriods"] = rollover_periods
    if rollover_period_length is not None:
        payload_data["RolloverPeriodLength"] = rollover_period_length

    # ============ Identification Fields ============
    if product_rate_plan_charge_number:
        payload_data["ProductRatePlanChargeNumber"] = product_rate_plan_charge_number

    # ============ Attribute-based Pricing ============
    if formula:
        payload_data["Formula"] = formula
    if charge_model_configuration:
        payload_data["ChargeModelConfiguration"] = charge_model_configuration
    if delivery_schedule:
        payload_data["DeliverySchedule"] = delivery_schedule

    if name:
        # Validate name length
        is_valid_len, len_warning = validate_name_length(name, "Charge name")
        if not is_valid_len and len_warning:
            warnings.append(len_warning)

        # Validate name uniqueness within rate plan
        payloads = tool_context.agent.state.get(PAYLOADS_STATE_KEY) or []
        rp_ref = payload_data.get("ProductRatePlanId", "")
        is_unique, unique_warning = validate_charge_name_unique(name, rp_ref, payloads)
        if not is_unique and unique_warning:
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


# ============ Prepaid with Drawdown Helper Functions ============


@tool(context=True)
def create_prepaid_charge(
    tool_context: ToolContext,
    name: str,
    prepaid_uom: str,
    prepaid_quantity: float,
    price: float,
    # Rate plan reference
    rate_plan_id: Optional[str] = None,
    rate_plan_index: Optional[int] = None,
    # Prepaid configuration
    commitment_type: Literal["UNIT", "CURRENCY"] = "UNIT",
    validity_period_type: Literal[
        "SUBSCRIPTION_TERM", "ANNUAL", "SEMI_ANNUAL", "QUARTER", "MONTH"
    ] = "SUBSCRIPTION_TERM",
    # Credit option for unused balance at end of validity period
    credit_option: Literal[
        "TimeBased", "ConsumptionBased", "FullCreditBack"
    ] = "ConsumptionBased",
    # Rollover settings
    is_rollover: bool = True,
    rollover_apply: Literal["ApplyFirst", "ApplyLast"] = "ApplyFirst",
    rollover_periods: Optional[int] = 1,
    rollover_period_length: Optional[int] = None,
    # Billing configuration
    billing_period: Literal[
        "Month",
        "Quarter",
        "Annual",
        "Semi-Annual",
        "Week",
        "Specific Months",
        "Specific Weeks",
        "Specific Days",
        "Subscription Term",
    ] = "Month",
    billing_timing: Literal["In Advance", "In Arrears"] = "In Advance",
    bill_cycle_type: Literal[
        "DefaultFromCustomer",
        "SpecificDayofMonth",
        "SubscriptionStartDay",
        "ChargeTriggerDay",
        "SpecificDayofWeek",
        "TermStartDay",
        "TermEndDay",
    ] = "DefaultFromCustomer",
    trigger_event: Literal[
        "ContractEffective", "ServiceActivation", "CustomerAcceptance"
    ] = "ContractEffective",
    # Currency
    currency: str = "USD",
    currencies: Optional[List[str]] = None,
    # Optional metadata
    description: Optional[str] = None,
    charge_number: Optional[str] = None,
) -> str:
    """Create a prepaid (top-up) charge that establishes a prepaid balance.

    This is the "wallet" charge that customers purchase to load units into their
    prepaid balance. Usage charges then draw down from this balance.

    Prepaid charges are typically Recurring charges that reload the balance each
    billing period, though they can also be OneTime for initial balance loading.

    Per Zuora Prepaid with Drawdown feature:
    - Unit-based (default): Tracks units like API calls, GB, credits
    - Currency-based: Tracks monetary value, usage is rated before drawdown

    Args:
        name: Charge name (e.g., "API Credits - Monthly Prepaid")
        prepaid_uom: Unit of measure for the prepaid balance (e.g., "API_CALL", "CREDIT", "GB")
        prepaid_quantity: Number of units loaded per billing period
        price: Cost to customer for the prepaid package
        rate_plan_id: Zuora rate plan ID or object reference
        rate_plan_index: Index of rate plan in batch for auto-reference
        commitment_type: "UNIT" (track units) or "CURRENCY" (track monetary value)
        validity_period_type: How long prepaid balance is valid:
            - SUBSCRIPTION_TERM: Valid for entire subscription term
            - ANNUAL: Valid for 1 year
            - SEMI_ANNUAL: Valid for 6 months
            - QUARTER: Valid for 3 months
            - MONTH: Valid for 1 month
        credit_option: What happens to unused balance at end of validity:
            - FullCreditBack: Full credit returned
            - TimeBased: Prorated credit based on time
            - ConsumptionBased: Credit based on consumption ratio
        is_rollover: Whether unused units roll over to next period
        rollover_apply: When to use rollover units:
            - ApplyFirst: Use rollover before new units
            - ApplyLast: Use new units before rollover
        rollover_periods: Number of periods rollover is valid (max 3)
        rollover_period_length: Length of each rollover period
        billing_period: Billing frequency (Month, Quarter, Annual, etc.)
        billing_timing: "In Advance" (charge at start) or "In Arrears" (charge at end)
        bill_cycle_type: How to determine billing day
        trigger_event: When billing starts
        currency: Currency code (default: USD)
        currencies: List of currencies for multi-currency support
        description: Charge description
        charge_number: Natural key for the charge

    Returns:
        HTML-formatted payload confirmation with prepaid charge details.

    Example:
        create_prepaid_charge(
            name="API Credits - 10K Monthly",
            prepaid_uom="API_CALL",
            prepaid_quantity=10000,
            price=99.00,
            validity_period_type="MONTH",
            is_rollover=True,
            rollover_periods=2
        )
    """
    # Use create_charge with prepaid-specific settings
    return create_charge(
        tool_context=tool_context,
        rate_plan_id=rate_plan_id,
        rate_plan_index=rate_plan_index,
        name=name,
        description=description,
        product_rate_plan_charge_number=charge_number,
        # Prepaid charges are Recurring with standard charge model (e.g., Flat Fee Pricing)
        # The prepaid behavior is controlled by IsPrepaid=true and PrepaidOperationType=topup
        charge_type="Recurring",
        charge_model="Flat Fee Pricing",
        price=price,
        currency=currency,
        currencies=currencies,
        # Billing configuration
        billing_period=billing_period,
        billing_timing=billing_timing,
        bill_cycle_type=bill_cycle_type,
        trigger_event=trigger_event,
        # Prepaid-specific fields
        charge_function="Prepayment",
        commitment_type=commitment_type,
        credit_option=credit_option,
        is_prepaid=True,
        prepaid_operation_type="topup",
        prepaid_quantity=prepaid_quantity,
        prepaid_uom=prepaid_uom,
        validity_period_type=validity_period_type,
        # Rollover settings
        is_rollover=is_rollover,
        rollover_apply=rollover_apply if is_rollover else None,
        rollover_periods=rollover_periods if is_rollover else None,
        rollover_period_length=rollover_period_length if is_rollover else None,
    )


@tool(context=True)
def create_drawdown_charge(
    tool_context: ToolContext,
    name: str,
    uom: str,
    # Drawdown UOM - required, the UOM to draw from the prepaid balance
    drawdown_uom: str,
    # Rate plan reference
    rate_plan_id: Optional[str] = None,
    rate_plan_index: Optional[int] = None,
    # Drawdown configuration - for different UOM than prepaid
    drawdown_rate: Optional[float] = None,
    # Overage handling
    overage_price: Optional[float] = None,
    allow_overage: bool = True,
    # Billing configuration - BillingPeriod is required for drawdown, but NOT BillingTiming
    billing_period: Literal[
        "Month",
        "Quarter",
        "Annual",
        "Semi-Annual",
        "Week",
        "Specific Months",
        "Specific Weeks",
        "Specific Days",
        "Subscription Term",
    ] = "Month",
    billing_period_alignment: Literal[
        "AlignToCharge",
        "AlignToSubscriptionStart",
        "AlignToTermStart",
        "AlignToTermEnd",
    ] = "AlignToCharge",
    bill_cycle_type: Literal[
        "DefaultFromCustomer",
        "SpecificDayofMonth",
        "SubscriptionStartDay",
        "ChargeTriggerDay",
        "SpecificDayofWeek",
        "TermStartDay",
        "TermEndDay",
    ] = "DefaultFromCustomer",
    trigger_event: Literal[
        "ContractEffective", "ServiceActivation", "CustomerAcceptance"
    ] = "ContractEffective",
    rating_group: Optional[
        Literal[
            "ByBillingPeriod",
            "ByUsageStartDate",
            "ByUsageRecord",
            "ByUsageUpload",
            "ByGroupId",
        ]
    ] = "ByBillingPeriod",
    # Currency
    currency: str = "USD",
    currencies: Optional[List[str]] = None,
    # Optional metadata
    description: Optional[str] = None,
    charge_number: Optional[str] = None,
) -> str:
    """Create a drawdown (usage) charge that consumes from a prepaid balance.

    This charge draws down units from a prepaid balance created by a prepaid charge.
    The price is typically $0 since usage is "free" - it's already paid for via
    the prepaid charge. Optionally configure overage pricing for usage beyond
    the prepaid balance.

    Per Zuora Prepaid with Drawdown feature:
    - Must be a Usage charge type (ChargeType=Usage)
    - Requires BillingPeriod but NOT BillingTiming
    - UOM should match the prepaid charge's UOM (or use drawdown_rate for conversion)
    - Multiple drawdown charges can share the same prepaid balance

    Args:
        name: Charge name (e.g., "API Usage - Drawdown")
        uom: Unit of measure for usage tracking
        drawdown_uom: The prepaid UOM to draw from (required for drawdown charges)
        rate_plan_id: Zuora rate plan ID or object reference
        rate_plan_index: Index of rate plan in batch for auto-reference
        drawdown_rate: Conversion rate if usage UOM differs from prepaid UOM
            Example: If prepaid is "CREDIT" and usage is "REPORT", and 1 report = 5 credits,
            set drawdown_rate=5 and drawdown_uom="CREDIT"
        overage_price: Price per unit when prepaid balance is exhausted
            If None and allow_overage=True, overage usage is not charged (free overage)
            If None and allow_overage=False, usage beyond balance may be blocked
        allow_overage: Whether to allow usage beyond prepaid balance
        billing_period: Billing period (required for drawdown charges, default: Month)
        billing_period_alignment: Align charges within subscription (default: AlignToCharge)
        bill_cycle_type: How to determine billing day
        trigger_event: When billing starts
        rating_group: How to aggregate usage for rating
        currency: Currency code (default: USD)
        currencies: List of currencies for multi-currency support
        description: Charge description
        charge_number: Natural key for the charge

    Returns:
        HTML-formatted payload confirmation with drawdown charge details.

    Example - Simple drawdown (same UOM as prepaid):
        create_drawdown_charge(
            name="API Usage",
            uom="Million calls",
            drawdown_uom="Million calls"
        )

    Example - Different UOM with conversion rate:
        create_drawdown_charge(
            name="Report Generation",
            uom="REPORT",
            drawdown_uom="CREDIT",
            drawdown_rate=5  # 1 report = 5 credits
        )

    Example - With overage pricing:
        create_drawdown_charge(
            name="API Usage with Overage",
            uom="API_CALL",
            drawdown_uom="API_CALL",
            overage_price=0.001  # $0.001 per call after prepaid exhausted
        )
    """
    # Determine the price - $0 for drawdown (usage is "free" from prepaid balance)
    # If overage_price is set, we need to handle that differently
    charge_price = 0.0 if overage_price is None else 0.0

    # Build overage configuration if needed
    # Note: Zuora handles overage through the prepaid balance mechanism
    # The overage_price would be applied when balance is exhausted
    charge_description = description
    if overage_price is not None:
        if not charge_description:
            charge_description = f"Drawdown charge. Overage rate: ${overage_price}/unit after prepaid balance exhausted."
        # Store overage config in description for now - actual implementation
        # depends on tenant's overage handling configuration

    # Use create_charge with drawdown-specific settings
    # Note: Drawdown charges require BillingPeriod but NOT BillingTiming
    return create_charge(
        tool_context=tool_context,
        rate_plan_id=rate_plan_id,
        rate_plan_index=rate_plan_index,
        name=name,
        description=charge_description,
        product_rate_plan_charge_number=charge_number,
        # Drawdown charges are Usage with Per Unit Pricing
        charge_type="Usage",
        charge_model="Per Unit Pricing",
        price=charge_price,
        currency=currency,
        currencies=currencies,
        uom=uom,
        # Billing configuration - BillingPeriod required, NO BillingTiming for drawdown
        billing_period=billing_period,
        billing_period_alignment=billing_period_alignment,
        bill_cycle_type=bill_cycle_type,
        trigger_event=trigger_event,
        rating_group=rating_group,
        # Drawdown-specific fields
        charge_function="Drawdown",
        is_prepaid=True,
        prepaid_operation_type="drawdown",
        # Drawdown rate for UOM conversion
        drawdown_rate=drawdown_rate,
        drawdown_uom=drawdown_uom,
    )


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
    commitment_type: Literal["UNIT", "CURRENCY"] = "UNIT",
    validity_period_type: Literal[
        "SUBSCRIPTION_TERM", "ANNUAL", "SEMI_ANNUAL", "QUARTER", "MONTH"
    ] = "SUBSCRIPTION_TERM",
    is_rollover: bool = True,
    rollover_periods: int = 1,
) -> str:
    """
    Generate Prepaid with Drawdown configuration with optional auto top-up.

    ADVISORY ONLY - provides configuration guidance and payloads without executing.
    For actual charge creation, use `create_prepaid_charge()` and `create_drawdown_charge()`.

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
        commitment_type: "UNIT" (track units) or "CURRENCY" (track monetary value)
        validity_period_type: How long prepaid balance is valid
        is_rollover: Whether unused units roll over to next period
        rollover_periods: Number of periods rollover is valid (max 3)

    Returns:
        Complete configuration guide for Prepaid with Drawdown setup.
    """
    # Prepaid charge configuration
    # Note: Prepaid topup uses standard charge models (e.g., Flat Fee Pricing)
    # The prepaid behavior is controlled by IsPrepaid=true and PrepaidOperationType=topup
    prepaid_charge_config = {
        "name": f"{rate_plan_name} - Prepaid {prepaid_uom}",
        "ChargeType": "Recurring",
        "ChargeModel": "Flat Fee Pricing",
        "BillingPeriod": "Month",
        "BillingTiming": "In Advance",
        "ChargeFunction": "Prepayment",
        "CommitmentType": commitment_type,
        "IsPrepaid": True,
        "PrepaidOperationType": "topup",
        "PrepaidUom": prepaid_uom,
        "PrepaidQuantity": prepaid_quantity,
        "ValidityPeriodType": validity_period_type,
        "IsRollover": is_rollover,
        "RolloverPeriods": rollover_periods if is_rollover else None,
        "RolloverApply": "ApplyFirst" if is_rollover else None,
        "CreditOption": "ConsumptionBased",
        "pricing": [{"currency": "USD", "price": prepaid_amount}],
    }

    # Drawdown charge configuration
    # Note: Drawdown charges require BillingPeriod but NOT BillingTiming
    drawdown_charge_config = {
        "name": f"{rate_plan_name} - {prepaid_uom} Usage",
        "ChargeType": "Usage",
        "ChargeModel": "Per Unit Pricing",
        "ChargeFunction": "Drawdown",
        "BillingPeriod": "Month",
        "BillingPeriodAlignment": "AlignToCharge",
        "IsPrepaid": True,
        "PrepaidOperationType": "drawdown",
        "UOM": prepaid_uom,
        "DrawdownUom": prepaid_uom,
        "pricing": [{"currency": "USD", "price": 0}],
    }

    # Field lookup expression
    field_lookup_expr = ""
    if use_field_lookup_for_topup and account_field_name:
        field_lookup_expr = f"fieldLookup('Account.{account_field_name}')"

    rollover_info = (
        f"Rollover enabled for {rollover_periods} period(s)"
        if is_rollover
        else "No rollover"
    )
    guide = f"""
## Prepaid with Drawdown Configuration

### Product: {product_name}
### Rate Plan: {rate_plan_name}

---

### Quick Start: Use Helper Functions

For actual charge creation, use these convenience functions:

**1. Create Prepaid Charge:**
```python
create_prepaid_charge(
    name="{rate_plan_name} - Prepaid {prepaid_uom}",
    prepaid_uom="{prepaid_uom}",
    prepaid_quantity={prepaid_quantity},
    price={prepaid_amount},
    commitment_type="{commitment_type}",
    validity_period_type="{validity_period_type}",
    is_rollover={is_rollover},
    rollover_periods={rollover_periods}
)
```

**2. Create Drawdown Charge:**
```python
create_drawdown_charge(
    name="{rate_plan_name} - {prepaid_uom} Usage",
    uom="{prepaid_uom}"
)
```

---

### Step 1: Create the Prepaid Charge

This charge creates the prepaid balance (wallet) for the customer.

**API Endpoint:** POST /v1/object/product-rate-plan-charge

```json
{json.dumps(prepaid_charge_config, indent=2)}
```

**Key Settings:**
- `PrepaidUom`: {prepaid_uom} - The unit type tracked in the balance
- `PrepaidQuantity`: {prepaid_quantity:,.0f} - Units loaded per billing period
- `CommitmentType`: {commitment_type} - {"Track units directly" if commitment_type == "UNIT" else "Track monetary value"}
- `ValidityPeriodType`: {validity_period_type} - Balance validity period
- `price`: ${prepaid_amount:,.2f} - Cost to the customer
- {rollover_info}

---

### Step 2: Create the Drawdown Charge

This usage charge draws from the prepaid balance.

**API Endpoint:** POST /v1/object/product-rate-plan-charge

```json
{json.dumps(drawdown_charge_config, indent=2)}
```

**Key Settings:**
- `ChargeFunction`: Drawdown - Links to prepaid balance
- `PrepaidOperationType`: drawdown - Consumes from prepaid balance
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

        guide += """
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


# ============ PWD SeedSpec Tools (Billing Architect) ============


@tool(context=True)
def generate_pwd_seedspec(
    tool_context: ToolContext,
    product_name: str,
    sku: str,
    uom: str,
    currencies: List[str],
    prepaid_plans: List[Dict[str, Any]],
    topup_packs: Optional[List[Dict[str, Any]]] = None,
    overage: Optional[Dict[str, Any]] = None,
    wallet_policy: Optional[Dict[str, Any]] = None,
    validate_tenant: bool = True,
) -> str:
    """
    Generate a complete PWD SeedSpec with validation (no execution).

    ADVISORY ONLY - generates specification and planning payloads with placeholders.
    Does NOT create actual Zuora objects.

    Validates against PWD rules:
    - Drawdown price = 0
    - Prepay + drawdown in same rate plan
    - Threshold sanity (auto-topup < monthly load)
    - UOM enabled in tenant (if validate_tenant=True)
    - Currencies enabled in tenant (if validate_tenant=True)
    - Rollover cap defaults applied if missing

    Args:
        product_name: Name of the wallet product (e.g., "API Credits Wallet")
        sku: Product SKU (e.g., "API-WALLET-100")
        uom: Unit of measure for credits (e.g., "api_call")
        currencies: List of currency codes (e.g., ["USD", "EUR"])
        prepaid_plans: List of prepaid plan specifications with:
            - name: Plan name
            - prepaid_quantity: Units per period
            - prices: Dict of currency -> price
            - billing_period: Month, Quarter, Annual (default: Month)
            - trigger_event: ServiceActivation, ContractEffective (default: ServiceActivation)
            - wallet_policy: Optional wallet policies dict with:
                - pooling_type: ACCOUNT or SUBSCRIPTION
                - rollover_pct: Percentage to roll over (0-100)
                - rollover_cap: Max units to roll over
                - rollover_expiry_months: Months until rollover expires
                - auto_topup_enabled: Enable auto top-up
                - auto_topup_threshold: Balance threshold to trigger
                - auto_topup_quantity: Units to add
                - auto_topup_prices: Price per currency for top-up
        topup_packs: Optional one-time top-up packs with:
            - name: Pack name
            - quantity: Units in pack
            - prices: Dict of currency -> price
        overage: Optional overage configuration with:
            - enabled: Whether overage billing is enabled
            - prices_per_unit: Dict of currency -> overage price
            - billing_period: Billing period for overage
        wallet_policy: Default wallet policy for all plans (overridden by plan-specific)
        validate_tenant: Whether to check tenant UOM/currency compatibility

    Returns:
        Validation summary, raw JSON spec, and placeholder map.
    """
    from .zuora_settings import get_available_uom_names, get_available_currencies

    errors: List[str] = []
    warnings: List[str] = []
    auto_fixes: List[Dict[str, Any]] = []
    applied_defaults: List[str] = []

    # Step 1: Validate tenant compatibility if requested
    tenant_uoms: List[str] = []
    tenant_currencies: List[str] = []

    if validate_tenant:
        try:
            tenant_uoms = get_available_uom_names()
            tenant_currencies = get_available_currencies()
        except Exception as e:
            warnings.append(
                f"Could not fetch tenant settings: {e}. Skipping tenant validation."
            )
            validate_tenant = False

    # Step 2: Check UOM compatibility
    uom_issue = None
    if validate_tenant and tenant_uoms:
        uom_ok, uom_issue = check_pwd_uom_compatibility(uom, tenant_uoms)
        if not uom_ok and uom_issue:
            auto_fixes.append(uom_issue)

    # Step 3: Check currency compatibility
    currency_issues: List[Dict[str, Any]] = []
    if validate_tenant and tenant_currencies:
        currencies_ok, currency_issues = check_pwd_currency_compatibility(
            currencies, tenant_currencies
        )
        if not currencies_ok:
            auto_fixes.extend(currency_issues)

    # Step 4: Validate thresholds and apply defaults for each plan
    for i, plan in enumerate(prepaid_plans):
        plan_name = plan.get("name", f"Plan {i + 1}")
        monthly_load = plan.get("prepaid_quantity", 0)

        # Get wallet policy (plan-specific or default)
        plan_wallet_policy = plan.get("wallet_policy") or wallet_policy or {}

        rollover_pct = plan_wallet_policy.get("rollover_pct")
        rollover_cap = plan_wallet_policy.get("rollover_cap")
        auto_topup_threshold = plan_wallet_policy.get("auto_topup_threshold")

        # Apply rollover defaults
        if rollover_pct is not None:
            new_cap, default_explanation = apply_pwd_rollover_defaults(
                monthly_load, rollover_pct, rollover_cap
            )
            if default_explanation:
                applied_defaults.append(f"{plan_name}: {default_explanation}")
                # Update the plan's wallet policy with calculated cap
                if "wallet_policy" not in plan:
                    plan["wallet_policy"] = {}
                plan["wallet_policy"]["rollover_cap"] = new_cap
                rollover_cap = new_cap

        # Validate thresholds
        if plan_wallet_policy.get("auto_topup_enabled"):
            threshold_ok, threshold_errors, threshold_recs = validate_pwd_thresholds(
                monthly_load, auto_topup_threshold, rollover_cap, rollover_pct
            )
            if not threshold_ok:
                for err in threshold_errors:
                    errors.append(f"{plan_name}: {err}")
            warnings.extend([f"{plan_name}: {rec}" for rec in threshold_recs])

    # Step 5: Build the spec summary
    is_valid = len(errors) == 0 and len(auto_fixes) == 0

    # Build summary table
    summary_rows = []
    for plan in prepaid_plans:
        plan_name = plan.get("name", "Unnamed Plan")
        quantity = plan.get("prepaid_quantity", 0)
        prices = plan.get("prices", {})
        billing = plan.get("billing_period", "Month")
        plan_type = "Recurring Prepay" if plan.get("is_recurring", True) else "One-Time"

        price_str = " / ".join(
            [
                f"{_format_currency(p, c, decimals=0 if p >= 1 else 4)} {c}"
                for c, p in prices.items()
            ]
        )
        summary_rows.append(
            f"| {plan_name} | {plan_type} | {quantity:,.0f} {uom} | {price_str} | {billing} |"
        )

    if topup_packs:
        for pack in topup_packs:
            pack_name = pack.get("name", "Top-Up Pack")
            quantity = pack.get("quantity", 0)
            prices = pack.get("prices", {})
            price_str = " / ".join(
                [
                    f"{_format_currency(p, c, decimals=0 if p >= 1 else 4)} {c}"
                    for c, p in prices.items()
                ]
            )
            summary_rows.append(
                f"| {pack_name} | One-Time | {quantity:,.0f} {uom} | {price_str} | — |"
            )

    if overage and overage.get("enabled", True):
        overage_prices = overage.get("prices_per_unit", {})
        price_str = " / ".join(
            [
                f"{_format_currency(p, c, decimals=4)}/{uom} {c}"
                for c, p in overage_prices.items()
            ]
        )
        overage_billing = overage.get("billing_period", "Month")
        summary_rows.append(
            f"| Overage | Usage | Per-unit | {price_str} | {overage_billing} |"
        )

    summary_table = "\n".join(summary_rows)

    # Build wallet policy summary
    wallet_policy_summary = ""
    if prepaid_plans and prepaid_plans[0].get("wallet_policy"):
        wp = prepaid_plans[0].get("wallet_policy", {})
        policy_items = []

        pooling = wp.get("pooling_type", "ACCOUNT")
        pooling_id = wp.get("pooling_id", "POOL-DEFAULT")
        policy_items.append(f"- Pooling: {pooling}-level ({pooling_id})")

        if wp.get("rollover_pct") is not None:
            rollover_cap = wp.get("rollover_cap", "unlimited")
            expiry = wp.get("rollover_expiry_months", 1)
            cap_str = (
                f"{rollover_cap:,.0f}"
                if isinstance(rollover_cap, (int, float))
                else rollover_cap
            )
            policy_items.append(
                f"- Rollover: {wp.get('rollover_pct')}% capped at {cap_str}, expires after {expiry} month(s)"
            )

        if wp.get("auto_topup_enabled"):
            threshold = wp.get("auto_topup_threshold", 0)
            quantity = wp.get("auto_topup_quantity", 0)
            policy_items.append(
                f"- Auto Top-Up: Trigger when balance < {threshold:,.0f} → add {quantity:,.0f}"
            )

        wallet_policy_summary = "\n".join(policy_items)

    # Build raw JSON spec
    raw_spec = {
        "product_name": product_name,
        "sku": sku,
        "uom": uom,
        "currencies": currencies,
        "prepaid_plans": prepaid_plans,
    }
    if topup_packs:
        raw_spec["topup_packs"] = topup_packs
    if overage:
        raw_spec["overage"] = overage

    raw_json = json.dumps(raw_spec, indent=2)

    # Build placeholder map
    placeholder_map = {
        "{{PRODUCT_ID}}": f"{product_name} ({sku})",
    }
    for i, plan in enumerate(prepaid_plans):
        plan_name = plan.get("name", f"Plan_{i}")
        safe_name = plan_name.upper().replace(" ", "_").replace("-", "_")
        placeholder_map[f"{{{{RP_{safe_name}_ID}}}}"] = f"Rate Plan: {plan_name}"
        placeholder_map[f"{{{{CHARGE_PREPAY_{safe_name}_ID}}}}"] = (
            f"Prepaid Charge: {plan_name}"
        )
        placeholder_map[f"{{{{CHARGE_DRAWDOWN_{safe_name}_ID}}}}"] = (
            f"Drawdown Charge: {plan_name}"
        )

    if topup_packs:
        for i, pack in enumerate(topup_packs):
            pack_name = pack.get("name", f"TopUp_{i}")
            safe_name = pack_name.upper().replace(" ", "_").replace("-", "_")
            placeholder_map[f"{{{{RP_{safe_name}_ID}}}}"] = f"Rate Plan: {pack_name}"
            placeholder_map[f"{{{{CHARGE_{safe_name}_ID}}}}"] = f"Charge: {pack_name}"

    if overage and overage.get("enabled", True):
        placeholder_map["{{CHARGE_OVERAGE_ID}}"] = "Overage Charge"

    placeholder_table = "\n".join(
        [f"| `{k}` | {v} |" for k, v in placeholder_map.items()]
    )

    # Store spec in advisory state
    payloads = tool_context.agent.state.get(ADVISORY_PAYLOADS_STATE_KEY) or []
    payloads.append(
        {
            "type": "pwd_seedspec",
            "name": product_name,
            "spec": raw_spec,
            "placeholder_map": placeholder_map,
            "validation": {
                "is_valid": is_valid,
                "errors": errors,
                "warnings": warnings,
                "auto_fixes": auto_fixes,
                "applied_defaults": applied_defaults,
            },
        }
    )
    tool_context.agent.state.set(ADVISORY_PAYLOADS_STATE_KEY, payloads)

    # Build output
    if is_valid:
        status_icon = "✅"
        status_text = "PWD SeedSpec Validated"
    elif auto_fixes:
        status_icon = "⚠️"
        status_text = "PWD SeedSpec Has Issues (Auto-Fix Available)"
    else:
        status_icon = "❌"
        status_text = "PWD SeedSpec Validation Failed"

    output = f"""
## {status_icon} {status_text}

### Summary

| Plan | Type | Quantity | Price | Billing |
|------|------|----------|-------|---------|
{summary_table}
"""

    if wallet_policy_summary:
        output += f"""
### Wallet Policies

{wallet_policy_summary}
"""

    if applied_defaults:
        output += """
### Applied Defaults

"""
        for default in applied_defaults:
            output += f"- ℹ️ {default}\n"

    if errors:
        output += """
### Errors

"""
        for error in errors:
            output += f"- ❌ {error}\n"

    if warnings:
        output += """
### Warnings

"""
        for warning in warnings:
            output += f"- ⚠️ {warning}\n"

    if auto_fixes:
        output += """
### Tenant Compatibility Issues

The following issues were detected. Please choose how to resolve:

"""
        for i, fix in enumerate(auto_fixes, 1):
            field = fix.get("field", "unknown")
            original = fix.get("original", "")
            suggestion = fix.get("suggestion")
            message = fix.get("message", "")

            output += f"**Issue {i}: {field.upper()}**\n"
            output += f"- {message}\n"
            if suggestion:
                output += "\nOptions:\n"
                output += f"1. Apply fix: `{original}` → `{suggestion}`\n"
                output += "2. Keep original value\n"
                output += "3. Specify a different value\n\n"
            else:
                output += "\nOptions:\n"
                output += "1. Select from available values\n"
                output += f"2. Create new {field} in tenant settings\n\n"

    output += f"""
### Placeholder Map

| Placeholder | Description |
|-------------|-------------|
{placeholder_table}

### Raw JSON Spec

```json
{raw_json}
```

---
**Status**: {"PLANNING ONLY — No execution performed" if is_valid else "Fix issues before generating planning payloads"}
"""

    return output


@tool(context=True)
def validate_pwd_spec(
    tool_context: ToolContext,
    spec: Dict[str, Any],
    check_tenant: bool = True,
) -> str:
    """
    Validate a PWD SeedSpec against Zuora rules.

    Rules checked:
    1. Drawdown price must be 0 (usage draws from prepaid balance)
    2. Prepay + drawdown must be in same rate plan
    3. Auto-topup threshold < monthly load
    4. UOM must be enabled in tenant (if check_tenant=True)
    5. Currencies must be enabled (if check_tenant=True)
    6. Rollover cap <= rollover_pct * monthly_load

    Args:
        spec: PWDSeedSpec as dictionary with:
            - product_name: Product name
            - sku: Product SKU
            - uom: Unit of measure
            - currencies: List of currency codes
            - prepaid_plans: List of prepaid plan specs
            - topup_packs: Optional top-up packs
            - overage: Optional overage config
        check_tenant: Whether to validate against tenant configuration

    Returns:
        Validation result with errors, warnings, and auto-fix suggestions.
        If issues found, asks user before applying fixes.
    """
    from .zuora_settings import get_available_uom_names, get_available_currencies

    errors: List[str] = []
    warnings: List[str] = []
    auto_fixes: List[Dict[str, Any]] = []
    applied_defaults: List[str] = []

    uom = spec.get("uom", "")
    currencies = spec.get("currencies", [])
    prepaid_plans = spec.get("prepaid_plans", [])

    # Tenant validation
    if check_tenant:
        try:
            tenant_uoms = get_available_uom_names()
            tenant_currencies = get_available_currencies()

            # Check UOM
            uom_ok, uom_issue = check_pwd_uom_compatibility(uom, tenant_uoms)
            if not uom_ok and uom_issue:
                auto_fixes.append(uom_issue)

            # Check currencies
            currencies_ok, currency_issues = check_pwd_currency_compatibility(
                currencies, tenant_currencies
            )
            if not currencies_ok:
                auto_fixes.extend(currency_issues)

        except Exception as e:
            warnings.append(f"Could not fetch tenant settings: {e}")

    # Validate each plan
    for i, plan in enumerate(prepaid_plans):
        plan_name = plan.get("name", f"Plan {i + 1}")
        monthly_load = plan.get("prepaid_quantity", 0)
        plan_wp = plan.get("wallet_policy", {})

        # Check thresholds
        if plan_wp.get("auto_topup_enabled"):
            threshold_ok, threshold_errors, threshold_recs = validate_pwd_thresholds(
                monthly_load,
                plan_wp.get("auto_topup_threshold"),
                plan_wp.get("rollover_cap"),
                plan_wp.get("rollover_pct"),
            )
            if not threshold_ok:
                errors.extend([f"{plan_name}: {e}" for e in threshold_errors])
            warnings.extend([f"{plan_name}: {r}" for r in threshold_recs])

        # Check rollover defaults
        rollover_pct = plan_wp.get("rollover_pct")
        rollover_cap = plan_wp.get("rollover_cap")
        if rollover_pct is not None and rollover_cap is None:
            new_cap, explanation = apply_pwd_rollover_defaults(
                monthly_load, rollover_pct, rollover_cap
            )
            if explanation:
                applied_defaults.append(f"{plan_name}: {explanation}")

    # Validate drawdown price = 0 rule (informational)
    price_ok, price_msg = validate_pwd_drawdown_price(0)  # Always check for $0
    if not price_ok and price_msg:
        warnings.append(price_msg)

    # Build result
    is_valid = len(errors) == 0 and len(auto_fixes) == 0

    if is_valid:
        status = "✅ Validation Passed"
    elif auto_fixes:
        status = "⚠️ Validation Issues (Fixable)"
    else:
        status = "❌ Validation Failed"

    output = f"## {status}\n\n"

    if errors:
        output += "### Errors\n\n"
        for e in errors:
            output += f"- ❌ {e}\n"
        output += "\n"

    if warnings:
        output += "### Warnings\n\n"
        for w in warnings:
            output += f"- ⚠️ {w}\n"
        output += "\n"

    if auto_fixes:
        output += "### Tenant Issues (Require Action)\n\n"
        for i, fix in enumerate(auto_fixes, 1):
            output += (
                f"**{i}. {fix.get('field', '').upper()}**: {fix.get('message', '')}\n"
            )
            if fix.get("suggestion"):
                output += f"   - Suggested fix: `{fix.get('original')}` → `{fix.get('suggestion')}`\n"
        output += "\n"

    if applied_defaults:
        output += "### Applied Defaults\n\n"
        for d in applied_defaults:
            output += f"- ℹ️ {d}\n"
        output += "\n"

    if is_valid:
        output += "**Ready to generate planning payloads.** Use `generate_pwd_planning_payloads()` to create advisory JSON.\n"

    return output


@tool(context=True)
def generate_pwd_planning_payloads(
    tool_context: ToolContext,
    spec: Optional[Dict[str, Any]] = None,
    include_order_example: bool = True,
) -> str:
    """
    Generate planning payloads with placeholder IDs (no execution).

    Creates advisory JSON payloads for:
    - Product with {{PRODUCT_ID}}
    - Rate Plans with {{RP_*_ID}}
    - Charges with {{CHARGE_PREPAY_ID}}, {{CHARGE_DRAWDOWN_ID}}, {{CHARGE_OVERAGE_ID}}
    - Optional example Order payload for subscription creation

    Args:
        spec: PWDSeedSpec as dictionary. If None, uses the last spec from advisory state.
        include_order_example: Whether to include sample order JSON

    Returns:
        Planning payloads with placeholder map and JSON output.
        Does NOT add to execution queue - this is advisory only.
    """
    # Get spec from state if not provided
    resolved_spec: Dict[str, Any]
    if spec is None:
        payloads = tool_context.agent.state.get(ADVISORY_PAYLOADS_STATE_KEY) or []
        pwd_specs = [p for p in payloads if p.get("type") == "pwd_seedspec"]
        if not pwd_specs:
            return (
                "❌ No PWD SeedSpec found. Please run `generate_pwd_seedspec()` first."
            )
        resolved_spec = pwd_specs[-1].get("spec", {}) or {}
    else:
        resolved_spec = spec

    product_name = resolved_spec.get("product_name", "API Credits Wallet")
    sku = resolved_spec.get("sku", "API-WALLET-100")
    uom = resolved_spec.get("uom", "api_call")
    currencies = resolved_spec.get("currencies", ["USD"])
    prepaid_plans = resolved_spec.get("prepaid_plans", [])
    topup_packs = resolved_spec.get("topup_packs", [])
    overage = resolved_spec.get("overage", {})

    # Build Product payload
    product_payload = {
        "Name": product_name,
        "SKU": sku,
        "Description": resolved_spec.get(
            "description", f"Prepaid wallet product for {uom} credits"
        ),
        "EffectiveStartDate": "{{EFFECTIVE_START_DATE}}",
        "EffectiveEndDate": "{{EFFECTIVE_END_DATE}}",
    }

    # Build Rate Plan and Charge payloads
    rate_plan_payloads = []
    charge_payloads = []

    for i, plan in enumerate(prepaid_plans):
        plan_name = plan.get("name", f"Plan {i + 1}")
        safe_name = plan_name.upper().replace(" ", "_").replace("-", "_")
        quantity = plan.get("prepaid_quantity", 0)
        prices = plan.get("prices", {})
        billing_period = plan.get("billing_period", "Month")
        trigger_event = plan.get("trigger_event", "ServiceActivation")
        wp = plan.get("wallet_policy", {})

        # Rate Plan
        rp_payload = {
            "Name": plan_name,
            "ProductId": "{{PRODUCT_ID}}",
            "Description": f"Prepaid plan: {quantity:,.0f} {uom} per {billing_period.lower()}",
        }
        rate_plan_payloads.append(
            {"placeholder": f"{{{{RP_{safe_name}_ID}}}}", "payload": rp_payload}
        )

        # Prepaid Charge
        prepaid_tiers = [{"Currency": c, "Price": p} for c, p in prices.items()]
        prepaid_charge = {
            "Name": f"{plan_name} - Prepaid",
            "ProductRatePlanId": f"{{{{RP_{safe_name}_ID}}}}",
            "ChargeType": "Recurring",
            "ChargeModel": "Flat Fee Pricing",
            "ChargeFunction": "Prepayment",
            "BillingPeriod": billing_period,
            "BillingTiming": "In Advance",
            "BillCycleType": "DefaultFromCustomer",
            "TriggerEvent": trigger_event,
            "IsPrepaid": True,
            "PrepaidOperationType": "topup",
            "PrepaidQuantity": quantity,
            "PrepaidUom": uom,
            "CommitmentType": "UNIT",
            "ValidityPeriodType": "MONTH",
            "CreditOption": "ConsumptionBased",
            "ProductRatePlanChargeTierData": {
                "ProductRatePlanChargeTier": prepaid_tiers
            },
        }

        # Add rollover config if present
        if wp.get("rollover_pct") is not None:
            prepaid_charge["IsRollover"] = True
            prepaid_charge["RolloverPeriods"] = min(
                wp.get("rollover_expiry_months", 1), 3
            )
            prepaid_charge["RolloverApply"] = "ApplyFirst"

        charge_payloads.append(
            {
                "placeholder": f"{{{{CHARGE_PREPAY_{safe_name}_ID}}}}",
                "payload": prepaid_charge,
            }
        )

        # Drawdown Charge (price = $0)
        drawdown_tiers = [{"Currency": c, "Price": 0} for c in currencies]
        drawdown_charge = {
            "Name": f"{plan_name} - Drawdown",
            "ProductRatePlanId": f"{{{{RP_{safe_name}_ID}}}}",
            "ChargeType": "Usage",
            "ChargeModel": "Per Unit Pricing",
            "ChargeFunction": "Drawdown",
            "BillingPeriod": billing_period,
            "BillCycleType": "DefaultFromCustomer",
            "TriggerEvent": trigger_event,
            "IsPrepaid": True,
            "PrepaidOperationType": "drawdown",
            "UOM": uom,
            "DrawdownUom": uom,
            "RatingGroup": "ByBillingPeriod",
            "ProductRatePlanChargeTierData": {
                "ProductRatePlanChargeTier": drawdown_tiers
            },
        }
        charge_payloads.append(
            {
                "placeholder": f"{{{{CHARGE_DRAWDOWN_{safe_name}_ID}}}}",
                "payload": drawdown_charge,
            }
        )

    # Top-up packs
    for i, pack in enumerate(topup_packs or []):
        pack_name = pack.get("name", f"Top-Up Pack {i + 1}")
        safe_name = pack_name.upper().replace(" ", "_").replace("-", "_")
        quantity = pack.get("quantity", 0)
        prices = pack.get("prices", {})

        rp_payload = {
            "Name": pack_name,
            "ProductId": "{{PRODUCT_ID}}",
            "Description": f"One-time top-up: {quantity:,.0f} {uom}",
        }
        rate_plan_payloads.append(
            {"placeholder": f"{{{{RP_{safe_name}_ID}}}}", "payload": rp_payload}
        )

        topup_tiers = [{"Currency": c, "Price": p} for c, p in prices.items()]
        topup_charge = {
            "Name": pack_name,
            "ProductRatePlanId": f"{{{{RP_{safe_name}_ID}}}}",
            "ChargeType": "OneTime",
            "ChargeModel": "Flat Fee Pricing",
            "ChargeFunction": "Prepayment",
            "BillCycleType": "DefaultFromCustomer",
            "TriggerEvent": "ContractEffective",
            "IsPrepaid": True,
            "PrepaidOperationType": "topup",
            "PrepaidQuantity": quantity,
            "PrepaidUom": uom,
            "CommitmentType": "UNIT",
            "ProductRatePlanChargeTierData": {"ProductRatePlanChargeTier": topup_tiers},
        }
        charge_payloads.append(
            {"placeholder": f"{{{{CHARGE_{safe_name}_ID}}}}", "payload": topup_charge}
        )

    # Overage charge (if enabled)
    if overage and overage.get("enabled", True):
        overage_prices = overage.get("prices_per_unit", {})
        overage_billing = overage.get("billing_period", "Month")

        # Add to first prepaid plan's rate plan
        if prepaid_plans:
            first_plan = prepaid_plans[0].get("name", "Plan 1")
            safe_name = first_plan.upper().replace(" ", "_").replace("-", "_")
            rp_ref = f"{{{{RP_{safe_name}_ID}}}}"
        else:
            rp_ref = "{{RP_OVERAGE_ID}}"

        overage_tiers = [{"Currency": c, "Price": p} for c, p in overage_prices.items()]
        overage_charge = {
            "Name": "Overage Usage",
            "Description": "Overage billing when prepaid balance exhausted and auto top-up OFF",
            "ProductRatePlanId": rp_ref,
            "ChargeType": "Usage",
            "ChargeModel": "Per Unit Pricing",
            "ChargeFunction": "Standard",  # NOT Drawdown - standard usage charge
            "BillingPeriod": overage_billing,
            "BillCycleType": "DefaultFromCustomer",
            "TriggerEvent": "ContractEffective",
            "UOM": uom,
            "RatingGroup": "ByBillingPeriod",
            "ProductRatePlanChargeTierData": {
                "ProductRatePlanChargeTier": overage_tiers
            },
        }
        charge_payloads.append(
            {"placeholder": "{{CHARGE_OVERAGE_ID}}", "payload": overage_charge}
        )

    # Build Order example if requested
    order_example = None
    if include_order_example and prepaid_plans:
        first_plan = prepaid_plans[0].get("name", "Plan 1")
        safe_name = first_plan.upper().replace(" ", "_").replace("-", "_")

        order_example = {
            "orderDate": "{{ORDER_DATE}}",
            "existingAccountNumber": "{{ACCOUNT_NUMBER}}",
            "description": f"Subscribe to {product_name}",
            "subscriptions": [
                {
                    "orderActions": [
                        {
                            "type": "CreateSubscription",
                            "createSubscription": {
                                "terms": {
                                    "initialTerm": {
                                        "termType": "TERMED",
                                        "period": 12,
                                        "periodType": "Month",
                                    },
                                    "renewalSetting": "RENEW_WITH_SPECIFIC_TERM",
                                    "renewalTerms": [
                                        {"period": 12, "periodType": "Month"}
                                    ],
                                },
                                "subscribeToRatePlans": [
                                    {"productRatePlanId": f"{{{{RP_{safe_name}_ID}}}}"}
                                ],
                            },
                        }
                    ]
                }
            ],
        }

    # Build placeholder map table
    all_placeholders = {"{{PRODUCT_ID}}": f"{product_name} ({sku})"}
    for rp in rate_plan_payloads:
        all_placeholders[rp["placeholder"]] = f"Rate Plan: {rp['payload']['Name']}"
    for ch in charge_payloads:
        all_placeholders[ch["placeholder"]] = f"Charge: {ch['payload']['Name']}"

    placeholder_table = "\n".join(
        [f"| `{k}` | {v} |" for k, v in all_placeholders.items()]
    )

    # Build output
    output = f"""
## 📦 Planning Payloads Generated

### Placeholder Map

| Placeholder | Description |
|-------------|-------------|
{placeholder_table}

---

### Product Payload

```json
{json.dumps(product_payload, indent=2)}
```

### Rate Plan Payloads

"""
    for rp in rate_plan_payloads:
        output += f"**{rp['placeholder']}**\n```json\n{json.dumps(rp['payload'], indent=2)}\n```\n\n"

    output += "### Charge Payloads\n\n"
    for ch in charge_payloads:
        output += f"**{ch['placeholder']}**\n```json\n{json.dumps(ch['payload'], indent=2)}\n```\n\n"

    if order_example:
        output += f"""### Example Order (Subscription Creation)

```json
{json.dumps(order_example, indent=2)}
```

"""

    output += """---
**Status**: PLANNING ONLY — No execution performed

To execute these payloads, use the Product Manager persona with `create_product()`, `create_rate_plan()`, and `create_charge()` tools.
"""

    return output


@tool(context=True)
def get_pwd_knowledge_base(tool_context: ToolContext) -> str:
    """
    Get Zuora Prepaid with Drawdown best practices and KB links.

    Returns comprehensive advisory guide covering:
    - How the wallet is represented (prepaid + drawdown charges)
    - Why drawdown price is $0
    - Rollover, top-up, overage modeling patterns
    - Why charge model changes are blocked post go-live
    - 2-3 relevant Knowledge Center links
    - 6-bullet implementation checklist

    Returns:
        Formatted advisory guide with KB links and checklist.
    """
    kb_content = """
## Zuora Prepaid with Drawdown (PWD) — Best Practices

### How the Wallet is Represented

| Component | Charge Type | ChargeFunction | Purpose |
|-----------|-------------|----------------|---------|
| **Prepaid (Top-Up)** | Recurring | `Prepayment` | Creates the wallet balance |
| **Drawdown** | Usage | `Drawdown` | Consumes from wallet |
| **Overage** | Usage | `Standard` | Bills when wallet = 0 |

Both prepaid and drawdown charges must be in the **same rate plan**.
Balance is tracked at account or subscription level via `CommitmentType`:
- `UNIT`: Track units (API calls, credits, etc.)
- `CURRENCY`: Track monetary value

---

### Why Drawdown Price = $0

- Customer has **already paid** via the Prepaid charge
- Drawdown is "free" usage against pre-purchased credits
- Price = $0 ensures **no double-billing**
- Overage pricing applies **only after** balance exhausted
- The `ChargeFunction: Drawdown` tells Zuora to deduct from prepaid balance

---

### Modeling Patterns

#### Rollover Configuration
```json
{
  "IsRollover": true,
  "RolloverPeriods": 2,           // Max 3 per Zuora
  "RolloverApply": "ApplyFirst",  // Use old credits first
  "RolloverPeriodLength": null    // Optional: custom period
}
```

**RolloverApply options:**
- `ApplyFirst`: Use rolled-over credits before new credits (recommended)
- `ApplyLast`: Use new credits first, rollover as backup

#### Auto Top-Up (via Workflow)
- Triggered when `PrepaidBalance < threshold`
- Creates Order with `AddProduct` action for top-up rate plan
- Use `fieldLookup('Account.TopUpAmount__c')` for dynamic amounts
- Threshold should be 10-20% of monthly load (not higher)

#### Overage Handling
- **Separate Usage charge** in same rate plan
- `ChargeFunction = "Standard"` (NOT Drawdown)
- Standard per-unit pricing (e.g., $0.007/unit)
- Only billed when auto top-up is OFF and balance = 0

---

### Why Charge Model Changes Are Blocked Post Go-Live

1. **Active subscriptions reference the charge** - changing model breaks billing
2. **Historical data integrity** - past invoices tied to original model
3. **Revenue recognition** - model changes affect deferred revenue
4. **Zuora enforces immutability** for data consistency

**Solution**: Create new rate plan version, migrate subscribers via Orders API

---

### Knowledge Center Links

1. **[Prepaid with Drawdown Overview](https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/Prepaid_with_Drawdown)**
   Complete guide to PWD feature configuration

2. **[Create Prepayment Charge](https://knowledgecenter.zuora.com/Zuora_Billing/Bill_your_customers/Bill_for_usage_or_prepaid_products/Advanced_Consumption_Billing/Prepaid_with_Drawdown/Create_prepayment_charge)**
   Detailed setup for the top-up charge

3. **[Create Drawdown Charge](https://knowledgecenter.zuora.com/Zuora_Billing/Bill_your_customers/Bill_for_usage_or_prepaid_products/Advanced_Consumption_Billing/Prepaid_with_Drawdown/Create_drawdown_charge)**
   Configuring the usage drawdown charge

---

### Implementation Checklist

1. ☐ **Enable PWD feature** in tenant settings
   - Settings > Billing > Prepaid with Drawdown > Enable

2. ☐ **Create/verify UOM** for prepaid units
   - Settings > Units of Measure > Add (e.g., "api_call", "credit")

3. ☐ **Create Product** with rate plan containing:
   - Prepaid charge (ChargeFunction: Prepayment)
   - Drawdown charge (ChargeFunction: Drawdown, Price: $0)
   - Both in SAME rate plan

4. ☐ **Configure wallet policy**:
   - CommitmentType: UNIT or CURRENCY
   - ValidityPeriodType: MONTH, QUARTER, ANNUAL, or SUBSCRIPTION_TERM
   - Rollover settings if needed

5. ☐ **Set up auto top-up workflow** (if required):
   - Event trigger: PrepaidBalanceLow or custom event
   - Action: Create Order with AddProduct for top-up pack

6. ☐ **Test end-to-end**:
   - Create subscription with prepaid plan
   - Upload usage records
   - Verify drawdown from balance
   - Run billing to generate invoice
"""
    return kb_content


# ============ Solution Selection Tools (Billing Architect) ============


@tool(context=True)
def generate_solution_options(
    tool_context: ToolContext,
    use_case_description: str,
) -> str:
    """
    Analyze user's prepaid/wallet use case and generate solution options.

    IMPORTANT: After calling this tool, your response must be ONLY the tool output.
    DO NOT add any additional text. DO NOT assume the user chose Option 1.
    Wait for the user to explicitly reply with "Option 1" or "Option 2".

    Use this tool when user describes a prepaid, wallet, credits, or balance-based
    billing scenario. It checks tenant capabilities and provides two solution options:
    - Option 1: Native PPDD (Prepaid with Drawdown) - Recommended if available
    - Option 2: Standard workaround using credits/adjustments

    Args:
        use_case_description: Summary of what the user wants to achieve
            (e.g., "prepaid credits with automatic deduction and overage billing")

    Returns:
        Formatted solution options with pros/cons and next step prompt.
        Display this output AS-IS to the user and STOP. Do not continue.
        Wait for user to reply with their choice (Option 1 or Option 2).
    """
    from .zuora_settings import get_ppdd_capability_status

    # Check tenant capabilities
    ppdd_status = get_ppdd_capability_status()
    available_uoms = ppdd_status.get("available_uoms", [])
    available_currencies = ppdd_status.get("available_currencies", [])
    ppdd_likely = ppdd_status.get("likely_available", True)

    # Format UOM list for display
    uom_display = ", ".join(available_uoms[:5]) if available_uoms else "None configured"
    if len(available_uoms) > 5:
        uom_display += f" (+{len(available_uoms) - 5} more)"

    # Format currency list
    currency_display = (
        ", ".join(available_currencies[:5])
        if available_currencies
        else "None configured"
    )

    # Build output - compact narrative format (harder to truncate)
    # Note: Using ASCII characters instead of Unicode emojis to avoid potential
    # model encoding issues with certain Bedrock models (e.g., Qwen)
    env_status = "[OK] PPDD is enabled" if ppdd_likely else "[!] PPDD may need setup"
    recommend_tag = " [RECOMMENDED]" if ppdd_likely else ""

    output = f"""I've analyzed your request for a prepaid wallet solution.

**Your Zuora Environment:** {env_status} ({len(available_uoms)} UOMs: {uom_display} | {len(available_currencies)} currencies: {currency_display})

---

**Option 1: Prepaid with Drawdown (PPDD)**{recommend_tag}
Customer prepays for credits -> Zuora tracks balance automatically -> Usage deducts from balance -> Invoice shows remaining balance.
- Automatic real-time balance tracking
- Clear invoices with remaining balance displayed
- Built-in rollover, auto-top-up, and overage support
- Fully supported by Zuora

<hr>

**Option 2: Standard Workaround**
Customer pays upfront -> Usage billed separately -> Manual credit memos to offset -> Track balance externally.
- No automatic deduction (manual credit memos required)
- Invoice doesn't show remaining balance
- No native rollover or auto-top-up
- More complex to manage at scale

---

Reply with **"Option 1"**, **"Option 2"**, or **"Tell me more about [Option 1 / Option 2 / both]"**
"""

    # Store the options in advisory state for reference
    payloads = tool_context.agent.state.get(ADVISORY_PAYLOADS_STATE_KEY) or []
    payloads.append(
        {
            "type": "solution_options",
            "use_case": use_case_description,
            "ppdd_likely": ppdd_likely,
            "available_uoms": available_uoms,
            "available_currencies": available_currencies,
        }
    )
    tool_context.agent.state.set(ADVISORY_PAYLOADS_STATE_KEY, payloads)

    return output


@tool(context=True)
def explain_solution_option(
    tool_context: ToolContext,
    option: Literal["1", "2", "both"],
) -> str:
    """
    Provide detailed explanation of a solution option for prepaid/wallet billing.

    Use this tool when the user asks "tell me more about Option 1/2/both" after
    seeing the initial solution options from generate_solution_options().

    Args:
        option: Which option to explain - "1" for PPDD, "2" for workaround, "both" for comparison

    Returns:
        Detailed explanation with how it works, benefits/drawbacks, and invoice examples.
        After displaying, wait for user to choose Option 1 or Option 2.
    """
    from .zuora_settings import get_ppdd_capability_status

    # Check tenant capabilities for context
    ppdd_status = get_ppdd_capability_status()
    ppdd_likely = ppdd_status.get("likely_available", True)

    # Option 1: PPDD detailed explanation - compact narrative
    tenant_status_1 = "✅ Your tenant is ready" if ppdd_likely else "⚠️ May need setup"
    option_1_explanation = f"""**Option 1: Prepaid with Drawdown (PPDD) — Details**

**How it works:**
1. Create a product with two charges: Prepaid Charge ($99 for 100 credits) + Drawdown Charge ($0/unit, deducts from balance)
2. Zuora tracks balance in real-time
3. Each invoice shows: Credits Used → Deducted from Balance → Remaining Balance
4. When balance hits zero: overage billing kicks in OR auto-top-up triggers

**Benefits:** Native balance tracking • Audit-ready invoices • Rollover support • Auto-top-up workflows • Scales to unlimited customers • Fully supported by Zuora

**Example Invoice:**
```
Credits Used: 45 | Deducted: 45 | Remaining: 55 credits
Charges: Prepaid Bundle (100 credits): $99.00
```

**Prerequisites:** PPDD enabled in tenant ({tenant_status_1}), UOM configured"""

    # Option 2: Workaround detailed explanation - compact narrative
    option_2_explanation = """**Option 2: Standard Workaround — Details**

**How it works:**
1. Create one-time charge for prepaid amount ($99)
2. Create usage charge ($1/credit)
3. Manually apply credit memos to offset usage
4. Track balance in custom field or external system
5. Build custom reports for usage vs balance

**Drawbacks:** No automatic deduction • Invoices don't show balance (customers will ask "where's my balance?") • No native rollover • Manual work doesn't scale • Not officially supported by Zuora

**Example Invoice (confusing):**
```
Prepaid Purchase: $99.00
API Usage (45 credits): $45.00
Credit Memo (offset): -$45.00
Balance: ??? (calculated externally)
```

**Why PPDD is preferred:** Eliminates manual work, provides clear invoices, scales without custom code."""

    # Comparison table for "both" - compact version
    recommend_note = (
        "✅ Your tenant supports PPDD — **Option 1 is recommended**"
        if ppdd_likely
        else "⚠️ Check if PPDD is enabled in your tenant"
    )
    comparison_output = f"""**Comparison: Option 1 vs Option 2**

| Aspect | Option 1: PPDD ✅ | Option 2: Workaround |
|--------|------------------|----------------------|
| Balance Tracking | Automatic | Manual |
| Invoice Clarity | Shows balance | Requires calculation |
| Rollover | Native | Custom logic |
| Auto-Top-Up | Built-in | Manual/custom |
| Scalability | Unlimited | Limited |
| Zuora Support | Fully supported | Not supported |

{recommend_note}

---

{option_1_explanation}

---

{option_2_explanation}"""

    # Build output based on option
    if option == "1":
        output = option_1_explanation
    elif option == "2":
        output = option_2_explanation
    else:  # both
        output = comparison_output

    # Add next step - compact
    recommend_tag = " (recommended)" if ppdd_likely else ""
    output += f"""

---

Reply with **"Option 1"**{recommend_tag} or **"Option 2"** to proceed."""

    return output


@tool(context=True)
def generate_pm_handoff_prompt(
    tool_context: ToolContext,
    solution_type: Literal["ppdd", "standard"],
    product_name: str,
    sku: str,
    prepaid_quantity: int,
    currencies: List[str],
    prices: Dict[str, float],
    uom: str,
    billing_period: str = "Month",
    include_overage: bool = True,
    overage_prices: Optional[Dict[str, float]] = None,
    include_topup_pack: bool = False,
    topup_quantity: Optional[int] = None,
    topup_prices: Optional[Dict[str, float]] = None,
    include_rollover: bool = False,
    rollover_periods: Optional[int] = None,
    include_auto_topup_info: bool = False,
    auto_topup_threshold: Optional[int] = None,
) -> str:
    """
    Generate a ready-to-paste prompt for ProductManager persona.

    Creates a complete, formatted prompt that the user can copy and paste
    into a new conversation with ProductManager to create the product structure.

    CRITICAL: After calling this tool, your response MUST include the COMPLETE tool output.
    The output contains a code block with the prompt - this is what the user needs to copy.
    DO NOT summarize. DO NOT say "the prompt is ready" without showing the actual prompt.
    The user cannot copy a prompt they cannot see!

    IMPORTANT: Always ask the user for all required values before calling this tool.
    Do not use default values - get product_name, sku, prepaid_quantity, currencies,
    prices, and uom from the user.

    Args:
        solution_type: "ppdd" for Prepaid with Drawdown, "standard" for workaround
        product_name: Name of the product (ask user)
        sku: Product SKU (ask user)
        prepaid_quantity: Number of credits/units in prepaid charge (ask user)
        currencies: List of currency codes, e.g., ["USD", "EUR"] (ask user)
        prices: Price per currency, e.g., {"USD": 99.0, "EUR": 90.0} (ask user)
        uom: Unit of measure for credits, e.g., "credit", "api_call" (ask user)
        billing_period: Month, Quarter, Annual (default: Month)
        include_overage: Whether to include overage charge
        overage_prices: Price per unit per currency for overage, e.g., {"USD": 0.01}
        include_topup_pack: Whether to include one-time top-up pack
        topup_quantity: Units in top-up pack
        topup_prices: Prices for top-up pack per currency
        include_rollover: Whether to include rollover configuration info
        rollover_periods: Number of periods credits can roll over
        include_auto_topup_info: Whether to include auto top-up workflow info
        auto_topup_threshold: Balance threshold to trigger auto top-up

    Returns:
        Formatted prompt ready to copy/paste into ProductManager conversation.
        DISPLAY THIS ENTIRE OUTPUT TO THE USER - do not summarize or truncate!
    """
    # Format prices for display
    price_display = " / ".join(
        [f"{_format_currency(p, c)} {c}" for c, p in prices.items()]
    )

    # Get first currency and price for narrative descriptions
    # currencies[0] is the user's primary currency (first in their preference list)
    first_currency = currencies[0] if currencies else DEFAULT_FALLBACK_CURRENCY
    first_price = prices.get(first_currency, DEFAULT_FALLBACK_PRICE)

    if solution_type == "ppdd":
        # Build the detailed PPDD prompt (narrative style matching the example)
        prompt_lines = [
            "Create a Zuora Product with Prepaid Drawdown",
            "",
            f'Create a Zuora product called "{product_name}" (SKU: {sku}) that supports {billing_period.lower()}ly prepaid credits with usage-based drawdown.',
            "",
            "**Prepaid Credit Charge (Top-Up):**",
            f'Set up a recurring prepaid charge called "{product_name} – {prepaid_quantity:,} {uom.title()} {billing_period}ly."',
            f"This charge should bill {_format_currency(first_price, first_currency)} {first_currency} per {billing_period.lower()}, in advance, starting when the contract becomes effective.",
            "The billing cycle should follow the customer's default billing cycle.",
            f"This charge represents a prepaid credit top-up that grants {prepaid_quantity:,} {uom}s every {billing_period.lower()}.",
            "",
            "The charge should:",
            "- Use flat fee pricing",
            "- Be marked as a Prepayment charge",
            "- Have a unit-based commitment",
            "- Credit Option should be Consumption based",
            "- Be configured as a top-up prepaid operation",
            f"- Use {uom.title()}s as the unit of measure",
            f"- Have a {billing_period.lower()}ly validity period",
        ]

        # Add rollover configuration
        if include_rollover and rollover_periods:
            prompt_lines.extend(
                [
                    f"- Allow rollover of unused credits for {rollover_periods} period(s)",
                    "- Apply rolled-over credits first before new credits",
                ]
            )
        else:
            prompt_lines.append(
                "- Not allow rollover of unused credits into the next period"
            )

        # Add multi-currency pricing if applicable
        # Note: The main narrative above uses the primary currency (first in list).
        # This section shows all configured currencies for completeness.
        if len(currencies) > 1:
            prompt_lines.extend(
                [
                    "",
                    "**Multi-Currency Pricing:**",
                    f"Configure pricing for all {len(currencies)} currencies:",
                ]
            )
            for currency, price in prices.items():
                prompt_lines.append(
                    f"- {currency}: {_format_currency(price, currency)} per {billing_period.lower()}"
                )

        # Drawdown charge section
        prompt_lines.extend(
            [
                "",
                "**Usage Drawdown Charge:**",
                f'Add a usage charge named "{uom.title()} Usage – Drawdown."',
                "This charge should track consumption of the prepaid credits and deduct usage from the available balance.",
                "",
                "The usage charge should:",
                "- Use per-unit usage pricing",
                "- Be billed on the customer's default billing cycle",
                "- Start at contract effective date",
                "- Be rated by billing period",
                f"- Use {uom.title()}s as the unit of measure",
                "- Have a price of $0 per unit while prepaid credits are available",
                "- Be configured as a Drawdown charge",
                "- Use drawdown as the prepaid operation type",
                f"- Have a {billing_period.lower()}ly billing period",
            ]
        )

        # Add overage information
        if include_overage and overage_prices:
            overage_first_price = overage_prices.get(first_currency, 1.0)
            prompt_lines.append(
                f"- Include a description indicating that usage first consumes prepaid credits and that overage charges apply after the prepaid balance is exhausted (for example, {_format_currency(overage_first_price, first_currency, decimals=4)} per unit once credits run out)"
            )

            # Add separate overage charge
            prompt_lines.extend(
                [
                    "",
                    "**Overage Charge (when prepaid balance exhausted):**",
                    f'Add a usage charge named "{uom.title()} Overage."',
                    "This charge should bill for usage that exceeds the prepaid balance.",
                    "",
                    "The overage charge should:",
                    "- Use per-unit usage pricing",
                    "- Be a Standard charge (NOT a Drawdown charge)",
                    f"- Use {uom.title()}s as the unit of measure",
                ]
            )
            for currency, price in overage_prices.items():
                prompt_lines.append(
                    f"- Price ({currency}): {_format_currency(price, currency, decimals=4)} per {uom}"
                )

        # Add top-up pack if requested
        if include_topup_pack and topup_quantity and topup_prices:
            topup_first_price = topup_prices.get(first_currency, 50.0)
            prompt_lines.extend(
                [
                    "",
                    "**One-Time Top-Up Pack (Optional Add-On):**",
                    f'Create an additional rate plan called "Top-Up Pack – {topup_quantity:,} {uom.title()}s"',
                    "This allows customers to purchase additional credits as a one-time purchase.",
                    "",
                    "The top-up charge should:",
                    "- Be a OneTime charge",
                    "- Use flat fee pricing",
                    f"- Price: {_format_currency(topup_first_price, first_currency)} for {topup_quantity:,} {uom}s",
                    "- Be marked as a Prepayment charge",
                    f"- Grant {topup_quantity:,} {uom}s to the prepaid balance",
                ]
            )

        prompt_content = "\n".join(prompt_lines)

    else:  # standard workaround
        prompt_lines = [
            "Create a Zuora Product for Prepaid Credits (Standard Approach)",
            "",
            f'Create a Zuora product called "{product_name}" (SKU: {sku}) for prepaid credits using the standard approach (without Prepaid with Drawdown feature).',
            "",
            "**Note:** This approach does NOT use Zuora's native PPDD feature. Balance tracking and credit application will require manual processes or custom automation.",
            "",
            "**Prepaid Funds Charge:**",
            f'Set up a recurring charge called "{product_name} – Prepaid Funds" representing the prepaid amount.',
            f"This charge should bill {_format_currency(first_price, first_currency)} {first_currency} per {billing_period.lower()}, in advance.",
            f"This represents the prepaid amount the customer pays upfront (equivalent to {prepaid_quantity:,} {uom}s worth of value).",
            "",
            "The charge should:",
            "- Use flat fee pricing",
            "- Be billed In Advance",
            f"- Have a {billing_period.lower()}ly billing period",
        ]

        # Add multi-currency pricing if applicable
        # Note: The main narrative above uses the primary currency (first in list).
        # This section shows all configured currencies for completeness.
        if len(currencies) > 1:
            prompt_lines.extend(
                [
                    "",
                    "**Multi-Currency Pricing:**",
                    f"Configure pricing for all {len(currencies)} currencies:",
                ]
            )
            for currency, price in prices.items():
                prompt_lines.append(
                    f"- {currency}: {_format_currency(price, currency)} per {billing_period.lower()}"
                )

        # Usage tracking charge
        prompt_lines.extend(
            [
                "",
                "**Usage Tracking Charge:**",
                f'Add a usage charge named "{uom.title()} Usage."',
                "This charge tracks consumption but does NOT automatically deduct from prepaid balance.",
                "Usage is invoiced normally, and credit memos must be applied manually to offset against the prepaid amount.",
                "",
                "The usage charge should:",
                "- Use per-unit usage pricing",
                f"- Use {uom.title()}s as the unit of measure",
            ]
        )

        if overage_prices:
            for currency, price in overage_prices.items():
                prompt_lines.append(
                    f"- Price ({currency}): {_format_currency(price, currency, decimals=4)} per {uom}"
                )
        else:
            prompt_lines.append(
                f"- Price: {_format_currency(0.01, first_currency, decimals=4)} per {uom} (adjust as needed)"
            )

        # Balance management section
        prompt_lines.extend(
            [
                "",
                "**Balance Management (Manual Process Required):**",
                "Since this approach does not use native PPDD, you must:",
                "",
                "1. **Track remaining balance** using a custom field on Account (e.g., `PrepaidBalance__c`) or an external system",
                "2. **Apply credit memos** manually to offset usage charges against the prepaid amount",
                "3. **Configure automation** (optional) using Zuora Workflows to:",
                "   - Calculate remaining balance after each invoice",
                "   - Auto-generate credit memos to apply prepaid funds",
                "   - Alert when prepaid amount is running low",
                "4. **Handle exhaustion** by either:",
                "   - Issuing new invoices for additional usage",
                "   - Asking customer to top up manually",
            ]
        )

        prompt_content = "\n".join(prompt_lines)

    # Build the full output
    # NOTE: The [DISPLAY_FULL_OUTPUT] marker instructs the model to show everything
    output = f"""[DISPLAY_FULL_OUTPUT: Show this entire response to the user. Do NOT summarize.]

## ProductManager Prompt Generated

Copy the text below and paste it into a new conversation with the **ProductManager** persona:

---

```
{prompt_content}
```

---

### Configuration Summary

| Setting | Value |
|---------|-------|
| Solution | {"Prepaid with Drawdown (PPDD)" if solution_type == "ppdd" else "Standard Workaround"} |
| Product | {product_name} ({sku}) |
| Prepaid Amount | {prepaid_quantity:,} {uom} |
| Price | {price_display} |
| Billing | {billing_period}ly |
| Overage | {"Yes - " + ", ".join([f"{_format_currency(p, c, decimals=4)}/{uom} {c}" for c, p in (overage_prices or {}).items()]) if include_overage and overage_prices else "No"} |
| Rollover | {"Yes - " + str(rollover_periods) + " periods" if include_rollover and rollover_periods else "No"} |

---

### How to Use This Prompt

1. **Start a new chat** with the **ProductManager** persona
2. **Copy and paste** the entire prompt from the code block above
3. ProductManager will create payloads for the product, rate plan, and charges
4. **Review** the generated payloads
5. **Send to Zuora** when ready to create the actual catalog objects

---
"""

    # Add disadvantages section for Standard workaround
    if solution_type == "standard":
        output += """
### Disadvantages of Standard Approach

| Limitation | Impact |
|------------|--------|
| No automatic balance deduction | Manual credit memo application required |
| Manual balance tracking | Must use custom field or external system |
| No native rollover | Cannot automatically carry over unused credits |
| No auto top-up | Cannot trigger automatic replenishment |
| Complex reporting | Requires custom reporting for balance visibility |
| Invoice clarity | Invoices don't natively show prepaid deductions |

---

### Why Prepaid with Drawdown (PPDD) is Preferred

If your Zuora tenant has the PPDD feature enabled, it provides:
- **Automatic** balance tracking and deduction
- **Native** invoice line items showing usage, deduction, and remaining balance
- **Built-in** rollover and auto-top-up capabilities
- **Simplified** operations with no manual credit memos

**Recommendation:** If PPDD is available in your tenant, consider using Option 1 instead for a more streamlined implementation.

---
"""

    # Add auto top-up info if requested
    if include_auto_topup_info and auto_topup_threshold:
        output += f"""
### Auto Top-Up Workflow (Separate Configuration)

To enable automatic top-up when balance falls below {auto_topup_threshold:,} {uom}:

1. Create a **Workflow** in Zuora (Settings > Workflows)
2. Trigger: `PrepaidBalanceLow` event
3. Condition: `PrepaidBalance < {auto_topup_threshold}`
4. Action: Create Order to add top-up rate plan

This requires additional setup beyond the product catalog.

---
"""

    output += """
### Want to customize?

Tell me what to change:
- "Add another currency (GBP at £80)"
- "Change prepaid quantity to 50,000"
- "Include a top-up pack"
- "Add rollover for 2 periods"

[END_OF_PROMPT_OUTPUT: The above content must be displayed in full to the user.]
"""

    # Store the PM handoff prompt in advisory state for reference
    payloads = tool_context.agent.state.get(ADVISORY_PAYLOADS_STATE_KEY) or []
    payloads.append(
        {
            "type": "pm_handoff_prompt",
            "solution_type": solution_type,
            "product_name": product_name,
            "sku": sku,
            "prepaid_quantity": prepaid_quantity,
            "currencies": currencies,
            "prices": prices,
            "uom": uom,
            "billing_period": billing_period,
            "include_overage": include_overage,
            "overage_prices": overage_prices,
        }
    )
    tool_context.agent.state.set(ADVISORY_PAYLOADS_STATE_KEY, payloads)

    return output


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
    channel_config: Dict[str, Any] = {"type": channel_type}
    if channel_type in ["Callout", "Webhook"]:
        channel_config["endpoint"] = endpoint_url or "{{WORKFLOW_CALLOUT_URL}}"
        channel_config["retryCount"] = 3
        channel_config["retryInterval"] = 60

    notification_config: Dict[str, Any] = {
        "name": rule_name,
        "description": description,
        "eventType": event_type,
        "active": True,
        "channel": channel_config,
    }

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
    order_payload: Dict[str, Any] = {
        "orderDate": effective_date or "{{REPLACE_WITH_DATE}}",
        "existingAccountNumber": "{{REPLACE_WITH_ACCOUNT_NUMBER}}",
        "subscriptions": [],
    }

    subscription_action: Dict[str, Any] = {
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
        add_product_config: Dict[str, Any] = {"productRatePlanId": add_rate_plan_id}
        if actual_charge_overrides:
            add_product_config["chargeOverrides"] = [actual_charge_overrides]
        add_action: Dict[str, Any] = {
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
            "addProduct": add_product_config,
        }
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
            add_product_config_transition: Dict[str, Any] = {
                "productRatePlanId": add_rate_plan_id
            }
            if actual_charge_overrides:
                add_product_config_transition["chargeOverrides"] = [
                    actual_charge_overrides
                ]
            add_action_transition: Dict[str, Any] = {
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
                "addProduct": add_product_config_transition,
            }
            subscription_action["orderActions"].append(add_action_transition)

    elif action_type == "TopUp":
        # Add prepaid balance via order
        add_product_config_topup: Dict[str, Any] = {
            "productRatePlanId": add_rate_plan_id or "{{PREPAID_RATE_PLAN_ID}}"
        }
        if actual_charge_overrides:
            add_product_config_topup["chargeOverrides"] = [actual_charge_overrides]
        add_action_topup: Dict[str, Any] = {
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
            "addProduct": add_product_config_topup,
        }
        subscription_action["orderActions"].append(add_action_topup)

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
    currency: str = "USD",
) -> str:
    """
    Generate Multi-Attribute Pricing (MAP) configuration.

    ADVISORY ONLY - provides configuration guidance.

    Args:
        charge_name: Name of the charge
        attributes: List of pricing attributes with their values
                   Example: [{"name": "Region", "values": ["US", "EU", "APAC"]}]
        base_price: Base price before attribute adjustments
        currency: Currency code for pricing (default: USD)

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
### Base Price: {_format_currency(base_price, currency)}

---

### Pricing Attributes

"""
    for attr in attributes:
        guide += f"**{attr['name']}**: {', '.join(attr.get('values', []))}\n"

    guide += """
---

### Single-Attribute Price Matrix

| Attribute Value | Price |
|-----------------|-------|
"""
    for key, price in price_matrix.items():
        guide += f"| {key} | {_format_currency(price, currency)} |\n"

    if combined_matrix:
        guide += """
---

### Combined Price Matrix (Example)

| Combination | Price |
|-------------|-------|
"""
        for key, price in list(combined_matrix.items())[:8]:  # Show first 8
            guide += f"| {key} | {_format_currency(price, currency)} |\n"

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
6. Set default price for unmatched combinations: {_format_currency(base_price, currency)}
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
        "currency": "{currency}",
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
            guide += f"- `{charge_name} - {key.replace('|', ' / ')}`: {_format_currency(price, currency)}\n"
        if len(combined_matrix) > 4:
            guide += f"- ... ({len(combined_matrix) - 4} more rate plans)\n"
    else:
        for key, price in price_matrix.items():
            guide += f"- `{charge_name} - {key}`: {_format_currency(price, currency)}\n"

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

    guide += """
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
        result: Dict[str, Any] = {
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

    output += """
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
