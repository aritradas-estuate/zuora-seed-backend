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
