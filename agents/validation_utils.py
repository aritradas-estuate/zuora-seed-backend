"""
Common validation utilities for tools.

Provides reusable validation functions for dates, IDs, SKUs, etc.
Extracted from tools.py to reduce code duplication.
"""

import re
from datetime import datetime
from typing import Tuple, Optional, List


def validate_date_format(
    date_str: str, field_name: str = "date"
) -> Tuple[bool, Optional[str]]:
    """
    Validate date is in YYYY-MM-DD format.

    Args:
        date_str: Date string to validate
        field_name: Name of the field for error messages

    Returns:
        Tuple of (is_valid, error_message)
        error_message is None if valid
    """
    pattern = r"^\d{4}-\d{2}-\d{2}$"
    if not re.match(pattern, date_str):
        return False, f"Invalid {field_name} format. Use YYYY-MM-DD (e.g., 2024-01-01)"

    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True, None
    except ValueError as e:
        return False, f"Invalid {field_name}: {str(e)}"


def validate_date_range(start_date: str, end_date: str) -> Tuple[bool, Optional[str]]:
    """
    Validate end_date is after start_date.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        Tuple of (is_valid, error_message)
        error_message is None if valid
    """
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        if end <= start:
            return False, "End date must be after start date"
        return True, None
    except ValueError as e:
        return False, f"Invalid date: {str(e)}"


def validate_zuora_id(id_str: str, id_type: str = "ID") -> Tuple[bool, Optional[str]]:
    """
    Validate Zuora ID or object reference format.

    Accepts:
    - Real Zuora IDs: alphanumeric strings (e.g., '8a1234567890abcd')
    - Object references: @{Object.Id} or @{Object[index].Id}
      - @{Product.Id}, @{Product[0].Id}
      - @{ProductRatePlan.Id}, @{ProductRatePlan[0].Id}
      - @{ProductRatePlanCharge.Id}, @{ProductRatePlanCharge[0].Id}

    Args:
        id_str: ID string to validate
        id_type: Type of ID for error messages (e.g., "product_id", "rate_plan_id")

    Returns:
        Tuple of (is_valid, error_message)
        error_message is None if valid
    """
    if not id_str:
        return (
            False,
            f"Invalid {id_type}. Provide valid Zuora ID or object reference",
        )

    # Check for object reference syntax: @{Object.Id} or @{Object[index].Id}
    if id_str.startswith("@{") and id_str.endswith("}"):
        # Valid patterns:
        # @{Product.Id}, @{Product[0].Id}
        # @{ProductRatePlan.Id}, @{ProductRatePlan[0].Id}
        # @{ProductRatePlanCharge.Id}, @{ProductRatePlanCharge[0].Id}
        pattern = (
            r"^@\{(Product|ProductRatePlan|ProductRatePlanCharge)(\[\d+\])?\.Id\}$"
        )
        if re.match(pattern, id_str):
            return True, None
        else:
            return (
                False,
                f"Invalid object reference format. Use @{{Object[index].Id}} (e.g., '@{{Product[0].Id}}')",
            )

    # Otherwise validate as Zuora ID (alphanumeric, typically 32 chars but can vary)
    # Must be at least 8 characters and alphanumeric (allowing hyphens)
    if len(id_str) < 8:
        return (
            False,
            f"Invalid {id_type}. Provide valid Zuora ID (e.g., '8a1234567890abcd') or object reference (e.g., '@{{Product[0].Id}}')",
        )

    if not id_str.replace("-", "").isalnum():
        return (
            False,
            f"Invalid {id_type}. Zuora IDs must be alphanumeric",
        )

    return True, None


def is_object_reference(id_str: str) -> bool:
    """
    Check if the given string is a Zuora object reference.

    Args:
        id_str: ID string to check

    Returns:
        True if it's an object reference (@{Object.Id} format), False otherwise
    """
    if not id_str:
        return False
    return id_str.startswith("@{") and id_str.endswith("}")


def validate_sku_format(sku: str) -> Tuple[bool, Optional[str]]:
    """
    Validate SKU format (alphanumeric, hyphens, underscores).

    Args:
        sku: SKU string to validate

    Returns:
        Tuple of (is_valid, error_message)
        error_message is None if valid
    """
    if not re.match(r"^[a-zA-Z0-9_-]+$", sku):
        return (
            False,
            "Invalid SKU format. Use only alphanumeric characters, hyphens, and underscores",
        )
    return True, None


def format_error_message(title: str, detail: str = "") -> str:
    """
    Format validation error message with emoji.

    Args:
        title: Error title/type
        detail: Optional detailed error message

    Returns:
        Formatted error string with ❌ emoji
    """
    if detail:
        return f"❌ {title}: {detail}"
    return f"❌ {title}"


# ============ Name Validation Functions ============

MAX_NAME_LENGTH = 60


def validate_name_length(
    name: str, field_type: str = "Name"
) -> Tuple[bool, Optional[str]]:
    """
    Validate name doesn't exceed max length.

    Args:
        name: Name string to validate
        field_type: Type of name for error messages (e.g., "Product name", "Rate plan name")

    Returns:
        Tuple of (is_valid, warning_message)
        warning_message is None if valid
    """
    if not name:
        return (True, None)
    if len(name) > MAX_NAME_LENGTH:
        return (
            False,
            f"{field_type} exceeds {MAX_NAME_LENGTH} characters (got {len(name)}). Please shorten it.",
        )
    return (True, None)


def validate_product_name_unique(
    name: str, existing_payloads: List[dict]
) -> Tuple[bool, Optional[str]]:
    """
    Check if product name is unique among existing product payloads in current session.

    Args:
        name: Product name to check
        existing_payloads: List of payload dicts from agent state

    Returns:
        Tuple of (is_unique, warning_message)
        warning_message is None if unique
    """
    if not name:
        return (True, None)

    for payload in existing_payloads:
        if payload.get("zuora_api_type") in ("product", "product_create"):
            existing_name = payload.get("payload", {}).get("Name") or payload.get(
                "payload", {}
            ).get("name")
            if existing_name and existing_name.lower() == name.lower():
                return (
                    False,
                    f"Duplicate product name '{name}' - a product with this name already exists in the current payload",
                )

    return (True, None)


def validate_rate_plan_name_unique(
    name: str, product_id: str, existing_payloads: List[dict]
) -> Tuple[bool, Optional[str]]:
    """
    Check if rate plan name is unique within the same product in current session.

    Args:
        name: Rate plan name to check
        product_id: Product ID or object reference this rate plan belongs to
        existing_payloads: List of payload dicts from agent state

    Returns:
        Tuple of (is_unique, warning_message)
        warning_message is None if unique
    """
    if not name:
        return (True, None)

    for payload in existing_payloads:
        if payload.get("zuora_api_type") in (
            "rate_plan",
            "rate_plan_create",
            "product_rate_plan",
        ):
            payload_data = payload.get("payload", {})
            existing_name = payload_data.get("Name") or payload_data.get("name")
            existing_product_id = payload_data.get("ProductId") or payload_data.get(
                "productId"
            )

            # Check if same name AND same product
            if (
                existing_name
                and existing_name.lower() == name.lower()
                and existing_product_id
                and existing_product_id == product_id
            ):
                return (
                    False,
                    f"Duplicate rate plan name '{name}' - a rate plan with this name already exists for this product",
                )

    return (True, None)


def validate_charge_name_unique(
    name: str, rate_plan_id: str, existing_payloads: List[dict]
) -> Tuple[bool, Optional[str]]:
    """
    Check if charge name is unique within the same rate plan in current session.

    Args:
        name: Charge name to check
        rate_plan_id: Rate plan ID or object reference this charge belongs to
        existing_payloads: List of payload dicts from agent state

    Returns:
        Tuple of (is_unique, warning_message)
        warning_message is None if unique
    """
    if not name:
        return (True, None)

    for payload in existing_payloads:
        if payload.get("zuora_api_type") in (
            "charge",
            "charge_create",
            "product_rate_plan_charge",
        ):
            payload_data = payload.get("payload", {})
            existing_name = payload_data.get("Name") or payload_data.get("name")
            existing_rp_id = payload_data.get("ProductRatePlanId") or payload_data.get(
                "productRatePlanId"
            )

            # Check if same name AND same rate plan
            if (
                existing_name
                and existing_name.lower() == name.lower()
                and existing_rp_id
                and existing_rp_id == rate_plan_id
            ):
                return (
                    False,
                    f"Duplicate charge name '{name}' - a charge with this name already exists for this rate plan",
                )

    return (True, None)


# ============ PWD Validation Functions (Architect Persona) ============


def validate_pwd_drawdown_price(price: float) -> Tuple[bool, Optional[str]]:
    """
    Validate drawdown price is 0 (usage draws from prepaid balance).

    Per Zuora PWD model, drawdown charges should have price=$0 because
    usage is "free" - already paid for via the prepaid charge.

    Args:
        price: The drawdown charge price

    Returns:
        Tuple of (is_valid, error_message)
    """
    if price != 0:
        return (
            False,
            f"Drawdown price must be $0 (got ${price}). "
            "Usage is 'free' - already paid via prepaid charge.",
        )
    return True, None


def validate_pwd_thresholds(
    monthly_load: float,
    auto_topup_threshold: Optional[float],
    rollover_cap: Optional[float],
    rollover_pct: Optional[float],
) -> Tuple[bool, List[str], List[str]]:
    """
    Validate PWD threshold configuration sanity.

    Rules:
    1. auto_topup_threshold < monthly_load (otherwise triggers before any usage)
    2. rollover_cap should align with rollover_pct if both set

    Args:
        monthly_load: Units loaded per billing period
        auto_topup_threshold: Balance threshold to trigger top-up
        rollover_cap: Maximum units that can roll over
        rollover_pct: Percentage of unused balance to roll over

    Returns:
        Tuple of (is_valid, errors, recommendations)
    """
    errors = []
    recommendations = []

    # Rule 1: Auto top-up threshold must be less than monthly load
    if auto_topup_threshold is not None:
        if auto_topup_threshold >= monthly_load:
            errors.append(
                f"Auto top-up threshold ({auto_topup_threshold:,.0f}) must be < "
                f"monthly load ({monthly_load:,.0f}). "
                f"With threshold >= load, top-up triggers before any usage occurs."
            )
            safe_threshold = monthly_load * 0.2  # 20% is typical
            recommendations.append(
                f"Suggested threshold: {safe_threshold:,.0f} (20% of monthly load)"
            )
        elif auto_topup_threshold > monthly_load * 0.8:
            recommendations.append(
                f"Warning: Threshold ({auto_topup_threshold:,.0f}) is >80% of load. "
                f"Consider lowering to avoid premature top-ups."
            )

    # Rule 2: Rollover cap vs percentage alignment
    if rollover_pct is not None and rollover_cap is not None:
        expected_cap = monthly_load * (rollover_pct / 100)
        if rollover_cap > expected_cap * 1.5:  # Allow some flexibility
            recommendations.append(
                f"Rollover cap ({rollover_cap:,.0f}) exceeds {rollover_pct}% of load "
                f"({expected_cap:,.0f}). Consider aligning for consistency."
            )

    return len(errors) == 0, errors, recommendations


def apply_pwd_rollover_defaults(
    monthly_load: float,
    rollover_pct: Optional[float],
    rollover_cap: Optional[float],
) -> Tuple[Optional[float], Optional[str]]:
    """
    Apply intelligent defaults for rollover cap.

    If rollover_pct is set but rollover_cap is None:
        rollover_cap = monthly_load * (rollover_pct / 100)

    Args:
        monthly_load: Units loaded per billing period
        rollover_pct: Percentage of unused balance to roll over
        rollover_cap: Maximum units that can roll over (may be None)

    Returns:
        Tuple of (calculated_cap, explanation)
        explanation is None if no default was applied
    """
    if rollover_pct is not None and rollover_cap is None:
        calculated_cap = monthly_load * (rollover_pct / 100)
        explanation = (
            f"No rollover_cap provided. Defaulted to {rollover_pct}% of monthly load: "
            f"{calculated_cap:,.0f} units"
        )
        return calculated_cap, explanation
    return rollover_cap, None


def check_pwd_uom_compatibility(
    spec_uom: str,
    tenant_uoms: List[str],
) -> Tuple[bool, Optional[dict]]:
    """
    Check if UOM exists in tenant and suggest fix if not.

    Args:
        spec_uom: UOM specified in the PWD spec
        tenant_uoms: List of UOMs available in the tenant

    Returns:
        Tuple of (is_compatible, auto_fix_suggestion)
        auto_fix_suggestion is None if compatible
    """
    # Exact match
    if spec_uom in tenant_uoms:
        return True, None

    # Case-insensitive match
    for uom in tenant_uoms:
        if uom.lower() == spec_uom.lower():
            return False, {
                "field": "uom",
                "original": spec_uom,
                "suggestion": uom,
                "action": "normalize_case",
                "message": f"UOM '{spec_uom}' not found. Did you mean '{uom}'?",
            }

    # Common alias check
    uom_aliases = {
        "api_calls": "api_call",
        "apicalls": "api_call",
        "API_CALLS": "api_call",
        "credits": "credit",
        "CREDITS": "credit",
        "Credit": "credit",
        "messages": "sms",
        "SMS": "sms",
        "Message": "sms",
        "gigabytes": "GB",
        "gb": "GB",
        "Gigabyte": "GB",
        "megabytes": "MB",
        "mb": "MB",
        "hours": "Hour",
        "hour": "Hour",
        "Hours": "Hour",
        "users": "User",
        "user": "User",
        "each": "Each",
        "unit": "Each",
        "units": "Each",
    }

    normalized = uom_aliases.get(spec_uom, uom_aliases.get(spec_uom.lower()))
    if normalized:
        for uom in tenant_uoms:
            if uom.lower() == normalized.lower():
                return False, {
                    "field": "uom",
                    "original": spec_uom,
                    "suggestion": uom,
                    "action": "normalize_alias",
                    "message": f"UOM '{spec_uom}' normalized to tenant UOM '{uom}'",
                }

    # No match found
    available_display = ", ".join(tenant_uoms[:8])
    if len(tenant_uoms) > 8:
        available_display += "..."

    return False, {
        "field": "uom",
        "original": spec_uom,
        "suggestion": None,
        "action": "create_or_select",
        "message": f"UOM '{spec_uom}' not found in tenant. Available UOMs: {available_display}",
    }


def check_pwd_currency_compatibility(
    spec_currencies: List[str],
    tenant_currencies: List[str],
) -> Tuple[bool, List[dict]]:
    """
    Check if currencies exist in tenant and suggest fixes.

    Args:
        spec_currencies: Currencies specified in the PWD spec
        tenant_currencies: Currencies enabled in the tenant

    Returns:
        Tuple of (all_compatible, list_of_issues)
        list_of_issues is empty if all compatible
    """
    issues = []
    tenant_currencies_upper = [c.upper() for c in tenant_currencies]

    for currency in spec_currencies:
        if currency.upper() not in tenant_currencies_upper:
            issues.append(
                {
                    "field": "currency",
                    "original": currency,
                    "suggestion": None,
                    "action": "enable_or_replace",
                    "message": f"Currency '{currency}' not enabled in tenant. "
                    f"Available: {', '.join(tenant_currencies)}",
                }
            )

    return len(issues) == 0, issues
