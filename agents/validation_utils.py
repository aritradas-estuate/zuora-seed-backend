"""
Common validation utilities for tools.

Provides reusable validation functions for dates, IDs, SKUs, etc.
Extracted from tools.py to reduce code duplication.
"""

import re
from datetime import datetime
from typing import Tuple, Optional


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
