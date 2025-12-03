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
    Validate Zuora ID format.

    Args:
        id_str: ID string to validate
        id_type: Type of ID for error messages (e.g., "product_id", "rate_plan_id")

    Returns:
        Tuple of (is_valid, error_message)
        error_message is None if valid
    """
    if not id_str or len(id_str) < 10:
        return (
            False,
            f"Invalid {id_type}. Provide valid Zuora ID (e.g., '8a1234567890abcd')",
        )
    return True, None


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


def format_error_message(error: str) -> str:
    """
    Format validation error message with emoji.

    Args:
        error: Error message

    Returns:
        Formatted error string with ❌ emoji
    """
    return f"❌ {error}"
