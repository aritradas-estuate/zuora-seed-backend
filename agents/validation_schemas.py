"""
Validation schemas for Zuora API payloads.

Defines required fields and validation rules for different entity types.
This module is extracted from tools.py for better organization and maintainability.
"""

from typing import Dict, Any, List, Tuple


# ============ Required Fields Schema ============

REQUIRED_FIELDS = {
    "product": {
        "always": ["Name", "EffectiveStartDate"],
        "nested": {},
        "conditional": {},
        "descriptions": {
            "Name": "Product name",
            "EffectiveStartDate": "Start date (YYYY-MM-DD format, e.g., 2024-01-01)",
        },
    },
    "product_create": {
        "always": ["name", "effectiveStartDate"],
        "nested": {},
        "conditional": {},
        "descriptions": {
            "name": "Product name",
            "effectiveStartDate": "Start date (YYYY-MM-DD format, e.g., 2024-01-01)",
            "sku": "Product SKU (alphanumeric, hyphens, underscores)",
        },
    },
    "product_rate_plan": {
        "always": ["Name", "ProductId"],
        "nested": {},
        "conditional": {},
        "descriptions": {
            "Name": "Rate plan name",
            "ProductId": "Product ID (use @{Product.Id} to reference a product in the same payload)",
        },
    },
    "rate_plan_create": {
        "always": ["name", "productId"],
        "nested": {},
        "conditional": {},
        "descriptions": {
            "name": "Rate plan name",
            "productId": "Product ID from Zuora (e.g., '8a1234567890abcd')",
        },
    },
    "product_rate_plan_charge": {
        "always": ["Name", "ProductRatePlanId", "ChargeModel", "ChargeType"],
        "nested": {},
        "conditional": {
            "ChargeType=Recurring": ["BillingPeriod"],
            "ChargeType=Usage": ["UOM"],
            "ChargeModel=FlatFee": ["Price"],
            "ChargeModel=PerUnit": ["Price"],
            "ChargeModel=Tiered": ["ProductRatePlanChargeTierData"],
            "ChargeModel=Volume": ["ProductRatePlanChargeTierData"],
        },
        "descriptions": {
            "Name": "Charge name",
            "ProductRatePlanId": "Rate plan ID (use @{ProductRatePlan.Id} or @{ProductRatePlan[0].Id})",
            "ChargeModel": "Pricing model (FlatFee, PerUnit, Tiered, or Volume)",
            "ChargeType": "Charge type (Recurring, OneTime, or Usage)",
            "BillingPeriod": "Billing period for recurring charges (Month, Quarter, Annual)",
            "UOM": "Unit of measure for usage charges (e.g., API_CALL, GB, SMS)",
            "Price": "Price amount (numeric)",
            "ProductRatePlanChargeTierData": "Tier pricing data for tiered/volume charges",
        },
    },
    "charge_create": {
        "always": ["name", "productRatePlanId", "chargeModel", "chargeType"],
        "nested": {},
        "conditional": {
            "chargeType=Recurring": ["billingPeriod"],
            "chargeType=Usage": ["uom"],
            "chargeModel=FlatFee": ["price"],
            "chargeModel=PerUnit": ["price"],
        },
        "descriptions": {
            "name": "Charge name",
            "productRatePlanId": "Rate plan ID from Zuora",
            "chargeModel": "Pricing model (FlatFee, PerUnit, Tiered, or Volume)",
            "chargeType": "Charge type (Recurring, OneTime, or Usage)",
            "billingPeriod": "Billing period for recurring charges (Month, Quarter, Annual)",
            "uom": "Unit of measure for usage charges (e.g., API_CALL, GB, SMS)",
            "price": "Price amount (numeric)",
        },
    },
    "account": {
        "always": ["name", "currency", "billCycleDay"],
        "nested": {"billToContact": ["firstName", "lastName", "country"]},
        "conditional": {},
        "descriptions": {
            "name": "Account name",
            "currency": "Currency code (USD, EUR, GBP)",
            "billCycleDay": "Bill cycle day (1-31)",
            "billToContact.firstName": "Billing contact first name",
            "billToContact.lastName": "Billing contact last name",
            "billToContact.country": "Billing contact country",
        },
    },
    "subscription": {
        "always": [
            "accountKey",
            "contractEffectiveDate",
            "termType",
            "subscribeToRatePlans",
        ],
        "nested": {},
        "conditional": {"termType=TERMED": ["initialTerm", "renewalTerm", "autoRenew"]},
        "descriptions": {
            "accountKey": "Account ID or account number",
            "contractEffectiveDate": "Contract effective date (YYYY-MM-DD)",
            "termType": "Term type (TERMED or EVERGREEN)",
            "subscribeToRatePlans": "Array of rate plans with productRatePlanId",
            "initialTerm": "Initial term length in months (required for TERMED)",
            "renewalTerm": "Renewal term length in months (required for TERMED)",
            "autoRenew": "Auto-renew flag true/false (required for TERMED)",
        },
    },
    "billrun": {
        "always": ["invoiceDate", "targetDate"],
        "nested": {},
        "conditional": {},
        "descriptions": {
            "invoiceDate": "Invoice date (YYYY-MM-DD)",
            "targetDate": "Target date for billing (YYYY-MM-DD)",
        },
    },
    "contact": {
        "always": ["firstName", "lastName", "country"],
        "nested": {},
        "conditional": {},
        "descriptions": {
            "firstName": "Contact first name",
            "lastName": "Contact last name",
            "country": "Country name",
        },
    },
}


# ============ Validation Helper Functions ============


def _get_nested_value(data: Dict[str, Any], path: str) -> Any:
    """Get a nested value from a dictionary using dot notation."""
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def _check_field_exists(data: Dict[str, Any], field: str) -> bool:
    """Check if a field exists in the payload (supports nested dot notation and flexible casing)."""
    if "." in field:
        return _get_nested_value(data, field) is not None

    # exact match
    if field in data:
        return True

    # Case-insensitive and underscore-insensitive match
    # e.g. "EffectiveStartDate" matches "effective_start_date" or "effectiveStartDate"
    target = field.lower().replace("_", "")
    existing_keys = {k.lower().replace("_", "") for k in data.keys()}

    return target in existing_keys


def validate_payload(
    api_type: str, payload_data: Dict[str, Any]
) -> Tuple[bool, List[Tuple[str, str]]]:
    """
    Validate payload against required fields for the given API type.

    Args:
        api_type: The API type (product, account, subscription, etc.)
        payload_data: The payload data dictionary

    Returns:
        Tuple of (is_valid, list_of_missing_field_tuples)
        Each tuple is (field_name, description)
    """
    api_type_lower = api_type.lower()

    # Get schema for this API type
    schema = REQUIRED_FIELDS.get(api_type_lower)
    if not schema:
        # Unknown type, skip validation
        return (True, [])

    missing = []
    descriptions = schema.get("descriptions", {})

    # Check "always" required fields
    for field in schema.get("always", []):
        if not _check_field_exists(payload_data, field):
            desc = descriptions.get(field, field)
            missing.append((field, desc))

    # Check "nested" required fields
    for parent_field, nested_fields in schema.get("nested", {}).items():
        parent_data = payload_data.get(parent_field, {})
        if not parent_data:
            # Parent is missing, add all nested fields
            for nested_field in nested_fields:
                full_path = f"{parent_field}.{nested_field}"
                desc = descriptions.get(full_path, nested_field)
                missing.append((full_path, desc))
        else:
            # Check each nested field
            for nested_field in nested_fields:
                if nested_field not in parent_data:
                    full_path = f"{parent_field}.{nested_field}"
                    desc = descriptions.get(full_path, nested_field)
                    missing.append((full_path, desc))

    # Check "conditional" required fields
    for condition, conditional_fields in schema.get("conditional", {}).items():
        # Parse condition like "ChargeType=Recurring"
        if "=" in condition:
            cond_field, cond_value = condition.split("=", 1)
            # Get actual value from payload (case-insensitive)
            actual_value = None
            for key in payload_data.keys():
                if key.lower() == cond_field.lower():
                    actual_value = payload_data[key]
                    break

            # Check if condition is met
            if actual_value and str(actual_value).upper() == cond_value.upper():
                # Condition met, check required fields
                for field in conditional_fields:
                    if not _check_field_exists(payload_data, field):
                        desc = descriptions.get(field, field)
                        cond_desc = (
                            f"{desc} (required because {cond_field}={cond_value})"
                        )
                        missing.append((field, cond_desc))

    return (len(missing) == 0, missing)


def format_validation_questions(
    api_type: str, missing_fields: List[Tuple[str, str]]
) -> str:
    """
    Format missing fields as HTML clarifying questions.

    Args:
        api_type: The API type
        missing_fields: List of (field_name, description) tuples

    Returns:
        HTML-formatted string with questions
    """
    output = f"<h4>Clarifying Questions Needed</h4>\n"
    output += f"<p>To create this <strong>{api_type}</strong> payload, I need the following information:</p>\n"
    output += "<ol>\n"

    for field_name, description in missing_fields:
        output += (
            f"  <li>What is the <strong>{field_name}</strong>? ({description})</li>\n"
        )

    output += "</ol>\n"
    output += (
        "<p><em>Please provide these details and I'll create the payload.</em></p>"
    )

    return output


def generate_placeholder_value(field_name: str, description: str) -> str:
    """
    Generate a placeholder string for a missing field.

    Args:
        field_name: The field name (e.g., "EffectiveStartDate" or "billToContact.firstName")
        description: The field description

    Returns:
        Placeholder string in format: <<PLACEHOLDER:FieldName>> or with description
    """
    # For conditional fields, description includes the condition
    if "required because" in description.lower():
        # Extract just the condition part
        return f"<<PLACEHOLDER:{field_name} ({description.split('(')[1].strip(')')})>>"
    else:
        # Simple placeholder
        return f"<<PLACEHOLDER:{field_name}>>"


def generate_placeholder_payload(
    api_type: str, payload_data: Dict[str, Any], missing_fields: List[Tuple[str, str]]
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Generate a complete payload with placeholders for missing required fields.

    Args:
        api_type: The API type (product, account, subscription, etc.)
        payload_data: The partial payload data
        missing_fields: List of (field_name, description) tuples for missing fields

    Returns:
        Tuple of (complete_payload_with_placeholders, list_of_placeholder_fields)
    """
    # Start with a copy of the existing payload
    complete_payload = payload_data.copy()
    placeholder_list = []

    for field_name, description in missing_fields:
        placeholder_value = generate_placeholder_value(field_name, description)
        placeholder_list.append(field_name)

        # Handle nested fields (e.g., "billToContact.firstName")
        if "." in field_name:
            parts = field_name.split(".")
            current = complete_payload

            # Navigate to parent, creating dicts as needed
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]

            # Set placeholder at the final key
            current[parts[-1]] = placeholder_value
        else:
            # Simple field
            complete_payload[field_name] = placeholder_value

    return (complete_payload, placeholder_list)


def format_placeholder_warning(
    api_type: str,
    placeholder_list: List[str],
    payload: Dict[str, Any],
    current_index: int = 0,
    total_count: int = 1,
) -> str:
    """
    Format a user-friendly warning about placeholders in the generated payload.

    Args:
        api_type: The API type
        placeholder_list: List of field names that have placeholders
        payload: The complete payload with placeholders
        current_index: Index of this payload among same-type payloads (0-based)
        total_count: Total number of payloads of this type

    Returns:
        HTML-formatted warning message
    """
    import json

    payload_id = payload.get("payload_id", "N/A")

    output = f"<h4>✅ Created {api_type} Payload (with placeholders)</h4>\n"
    output += f"<p><strong>Payload ID:</strong> <code>{payload_id}</code></p>\n"
    output += f"<p><strong>Index:</strong> {current_index} (of {total_count} {api_type} payload{'s' if total_count > 1 else ''})</p>\n"
    output += f"<p>I've generated the payload with <strong>{len(placeholder_list)}</strong> placeholder(s) for missing information:</p>\n"
    output += "<ul>\n"

    for field in placeholder_list:
        output += f"  <li><code>{field}</code></li>\n"

    output += "</ul>\n"

    # Show explicit update command examples
    output += "<p><strong>⚠️ To fill in placeholders, use:</strong></p>\n"
    if placeholder_list:
        example_field = placeholder_list[0]
        output += f"<pre><code>update_payload(api_type='{api_type}', payload_id='{payload_id}', field_path='{example_field}', new_value='YOUR_VALUE')</code></pre>\n"

    output += f"<pre><code>{json.dumps(payload, indent=2)}</code></pre>\n"

    return output
