"""
Validation schemas for Zuora API payloads.

Defines required fields and validation rules for different entity types.
This module is extracted from tools.py for better organization and maintainability.
"""

from typing import Dict, Any, List, Tuple


# ============ Human-Friendly Labels for Technical Zuora Values ============

# Maps technical enum values to human-readable descriptions
FRIENDLY_LABELS = {
    # Billing Periods
    "Specific_Months": "custom months",
    "Specific Months": "custom months",
    "Specific_Days": "custom days",
    "Specific Days": "custom days",
    "Specific_Weeks": "custom weeks",
    "Specific Weeks": "custom weeks",
    "Eighteen_Months": "18 months",
    "Two_Years": "2 years",
    "Three_Years": "3 years",
    "Five_Years": "5 years",
    "Annual": "yearly",
    "Semi-Annual": "every 6 months",
    "Quarter": "quarterly",
    "Month": "monthly",
    "Week": "weekly",
    # Bill Cycle Types
    "DefaultFromCustomer": "customer's billing day",
    "SpecificDayofMonth": "specific day of month",
    "SubscriptionStartDay": "subscription start day",
    "ChargeTriggerDay": "charge trigger day",
    # Charge Types
    "OneTime": "one-time",
    "Recurring": "recurring",
    "Usage": "usage-based",
    # Trigger Events
    "ContractEffective": "contract start",
    "ServiceActivation": "service activation",
    "CustomerAcceptance": "customer acceptance",
    # Charge Models
    "Flat Fee Pricing": "flat fee",
    "Per Unit Pricing": "per unit",
    "Tiered Pricing": "tiered",
    "Volume Pricing": "volume-based",
    "Overage Pricing": "overage",
    "Tiered with Overage Pricing": "tiered with overage",
    "Discount-Fixed Amount": "fixed discount",
    "Discount-Percentage": "percentage discount",
}

# Common defaults to suggest for each field type
COMMON_DEFAULTS = {
    "BillingPeriod": "monthly",
    "BillCycleType": "customer's billing day",
    "ChargeType": "recurring",
    "TriggerEvent": "contract start",
    "ChargeModel": "flat fee",
    "Currency": "USD",
}


def get_friendly_label(value: str) -> str:
    """Convert a technical Zuora value to a human-friendly label."""
    return FRIENDLY_LABELS.get(value, value)


def get_friendly_options(options: List[str], max_show: int = 5) -> str:
    """Convert a list of technical options to human-friendly text."""
    friendly = [get_friendly_label(opt) for opt in options[:max_show]]
    result = ", ".join(friendly)
    if len(options) > max_show:
        result += f", etc."
    return result


# ============ Required Fields Schema ============

REQUIRED_FIELDS = {
    "product": {
        "always": ["Name", "EffectiveStartDate", "EffectiveEndDate"],
        "nested": {},
        "conditional": {},
        "descriptions": {
            "Name": "Product name",
            "EffectiveStartDate": "Start date (YYYY-MM-DD format, e.g., 2024-01-01)",
            "EffectiveEndDate": "End date (YYYY-MM-DD format, e.g., 2034-01-01)",
        },
    },
    "product_create": {
        "always": ["Name", "EffectiveStartDate", "EffectiveEndDate"],
        "nested": {},
        "conditional": {},
        "descriptions": {
            "Name": "Product name",
            "EffectiveStartDate": "Start date (YYYY-MM-DD format, e.g., 2024-01-01)",
            "EffectiveEndDate": "End date (YYYY-MM-DD format, e.g., 2034-01-01)",
            "SKU": "Product SKU (alphanumeric, hyphens, underscores)",
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
        "always": ["Name", "ProductId"],
        "nested": {},
        "conditional": {},
        "descriptions": {
            "Name": "Rate plan name",
            "ProductId": "Product ID or object reference (e.g., '@{Product[0].Id}')",
        },
    },
    "product_rate_plan_charge": {
        "always": [
            "Name",
            "ProductRatePlanId",
            "ChargeModel",
            "ChargeType",
            "BillCycleType",
            "BillingPeriod",
            "TriggerEvent",
            "ProductRatePlanChargeTierData",
        ],
        "nested": {},
        "conditional": {
            "ChargeType=Usage": ["UOM"],
        },
        "descriptions": {
            "Name": "Charge name",
            "ProductRatePlanId": "Rate plan ID (use @{ProductRatePlan.Id} or @{ProductRatePlan[0].Id})",
            "ChargeModel": "Pricing model: 'Flat Fee Pricing', 'Per Unit Pricing', 'Tiered Pricing', 'Volume Pricing', 'Overage Pricing', 'Tiered with Overage Pricing', 'Discount-Fixed Amount', 'Discount-Percentage'",
            "ChargeType": "Charge type: 'OneTime', 'Recurring', or 'Usage'",
            "BillCycleType": "Billing day type: 'DefaultFromCustomer', 'SpecificDayofMonth', 'SubscriptionStartDay', 'ChargeTriggerDay'",
            "BillingPeriod": "Billing period: 'Month', 'Quarter', 'Annual', 'Semi-Annual', 'Specific Months', 'Week'",
            "TriggerEvent": "When billing starts: 'ContractEffective', 'ServiceActivation', 'CustomerAcceptance'",
            "UOM": "Unit of measure for usage charges (e.g., API_CALL, GB, SMS)",
            "ProductRatePlanChargeTierData": "Container for pricing tiers with currency and price",
        },
    },
    "charge_create": {
        "always": [
            "Name",
            "ProductRatePlanId",
            "ChargeModel",
            "ChargeType",
            "BillCycleType",
            "BillingPeriod",
            "TriggerEvent",
            "ProductRatePlanChargeTierData",
        ],
        "nested": {},
        "conditional": {
            "ChargeType=Usage": ["UOM"],
        },
        "descriptions": {
            "Name": "Charge name",
            "ProductRatePlanId": "Rate plan ID or object reference (e.g., '@{ProductRatePlan[0].Id}')",
            "ChargeModel": "Pricing model: 'Flat Fee Pricing', 'Per Unit Pricing', 'Tiered Pricing', 'Volume Pricing', 'Overage Pricing'",
            "ChargeType": "Charge type: 'OneTime', 'Recurring', or 'Usage'",
            "BillCycleType": "Billing day type: 'DefaultFromCustomer', 'SpecificDayofMonth', 'SubscriptionStartDay', 'ChargeTriggerDay'",
            "BillingPeriod": "Billing period: 'Month', 'Quarter', 'Annual', 'Semi-Annual', 'Specific Months', 'Week'",
            "TriggerEvent": "When billing starts: 'ContractEffective', 'ServiceActivation', 'CustomerAcceptance'",
            "UOM": "Unit of measure for usage charges (e.g., API_CALL, GB, SMS)",
            "ProductRatePlanChargeTierData": "Container for pricing tiers with currency and price",
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


def _get_env_options(option_type: str) -> List[str]:
    """
    Get environment-specific options from Zuora settings.
    Returns empty list if settings not available.
    """
    try:
        from .zuora_settings import (
            get_available_charge_models,
            get_available_billing_periods,
            get_available_billing_cycle_types,
            get_available_currencies,
            is_settings_loaded,
        )

        if not is_settings_loaded():
            return []

        if option_type == "charge_models":
            return get_available_charge_models()
        elif option_type == "billing_periods":
            return get_available_billing_periods()
        elif option_type == "billing_cycle_types":
            return get_available_billing_cycle_types()
        elif option_type == "currencies":
            return get_available_currencies()
    except ImportError:
        pass
    return []


def _get_placeholder_question(field_name: str, api_type: str) -> str:
    """
    Generate a natural language question for a placeholder field.
    Uses environment settings when available and provides human-friendly options.
    """
    field_lower = field_name.lower()

    if field_lower == "chargemodel":
        models = _get_env_options("charge_models")
        if models:
            friendly_options = get_friendly_options(models, max_show=4)
            return f"What pricing model? (e.g., {friendly_options} - common: {COMMON_DEFAULTS.get('ChargeModel', 'flat fee')})"
        return f"What pricing model? (e.g., flat fee, per unit, tiered, volume-based - common: {COMMON_DEFAULTS.get('ChargeModel', 'flat fee')})"

    elif field_lower == "billingperiod":
        periods = _get_env_options("billing_periods")
        if periods:
            friendly_options = get_friendly_options(periods, max_show=4)
            return f"What billing period? (e.g., {friendly_options} - common: {COMMON_DEFAULTS.get('BillingPeriod', 'monthly')})"
        return f"What billing period? (e.g., monthly, quarterly, yearly, weekly - common: {COMMON_DEFAULTS.get('BillingPeriod', 'monthly')})"

    elif field_lower == "billcycletype":
        types = _get_env_options("billing_cycle_types")
        default_cycle = COMMON_DEFAULTS.get("BillCycleType", "customer's billing day")
        if types:
            friendly_options = get_friendly_options(types, max_show=4)
            return f"What bill cycle type? (e.g., {friendly_options} - common: {default_cycle})"
        return f"What bill cycle type? (e.g., customer's billing day, specific day of month, subscription start day - common: {default_cycle})"

    elif field_lower == "productrateplanchargertierdata":
        return "What is the price? (e.g., 49.99)"

    elif field_lower == "productrateplanid":
        return "Which rate plan should this charge belong to?"

    elif field_lower == "productid":
        return "Which product should this rate plan belong to?"

    elif field_lower == "uom":
        return "What unit of measure? (e.g., API calls, GB, users, transactions)"

    elif field_lower == "name":
        friendly_type = api_type.replace("_create", "").replace("_", " ")
        return f"What should this {friendly_type} be named?"

    elif field_lower == "chargetype":
        return f"What type of charge? (e.g., recurring, one-time, or usage-based - common: {COMMON_DEFAULTS.get('ChargeType', 'recurring')})"

    elif field_lower == "triggerevent":
        return f"When should billing start? (e.g., contract start, service activation, customer acceptance - common: {COMMON_DEFAULTS.get('TriggerEvent', 'contract start')})"

    elif field_lower in ("effectivestartdate", "effectiveenddate"):
        friendly_name = "start date" if "start" in field_lower else "end date"
        return f"What {friendly_name}? (format: YYYY-MM-DD)"

    elif field_lower == "sku":
        return "What SKU (product code)?"

    elif field_lower == "currency":
        currencies = _get_env_options("currencies")
        if currencies:
            return f"What currency? (e.g., {', '.join(currencies[:3])} - common: USD)"
        return "What currency? (e.g., USD, EUR, GBP - common: USD)"

    else:
        # Generic fallback - make field name readable
        readable_name = field_name.replace("_", " ").replace("__c", "")
        return f"What {readable_name}?"


def format_placeholder_warning(
    api_type: str,
    placeholder_list: List[str],
    payload: Dict[str, Any],
    current_index: int = 0,
    total_count: int = 1,
) -> str:
    """
    Format a user-friendly message about placeholders with natural language questions.

    Instead of showing tool commands (which users cannot execute), this generates
    natural language questions that the agent can ask the user.

    Args:
        api_type: The API type
        placeholder_list: List of field names that have placeholders
        payload: The complete payload with placeholders
        current_index: Index of this payload among same-type payloads (0-based)
        total_count: Total number of payloads of this type

    Returns:
        HTML-formatted message with clarifying questions (no JSON)
    """
    payload_id = payload.get("payload_id", "N/A")
    payload_name = payload.get("payload", {}).get(
        "Name", payload.get("payload", {}).get("name", "unnamed")
    )

    # Make api_type human-friendly (e.g., "charge_create" -> "Charge")
    friendly_type = (
        api_type.replace("_create", "").replace("_update", "").replace("_", " ").title()
    )

    output = f"<h4>Created {friendly_type}</h4>\n"
    output += f"<p><strong>Name:</strong> {payload_name} &nbsp; <strong>ID:</strong> {payload_id}</p>\n"

    if placeholder_list:
        output += f"<p>I need {len(placeholder_list)} more detail(s):</p>\n"
        output += "<ul>\n"

        for field in placeholder_list:
            question = _get_placeholder_question(field, api_type)
            output += f"  <li>{question}</li>\n"

        output += "</ul>\n"
    else:
        output += "<p>All required fields are set. Ready to execute.</p>\n"

    return output
