"""
Zuora Environment Settings Manager.

Fetches and caches tenant-specific settings like available charge models,
billing periods, currencies, etc. Used to validate payloads and inform
the agent about the environment's capabilities.

Settings are cached for the session only (no persistence).
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Session-level cached settings
_cached_settings: Optional[Dict[str, Any]] = None
_fetch_attempted: bool = False
_fetch_error: Optional[str] = None


def fetch_environment_settings(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Fetch and cache Zuora environment settings.

    Args:
        force_refresh: If True, refetch even if cached

    Returns:
        Dict of settings keyed by setting name, or dict with _error key on failure
    """
    global _cached_settings, _fetch_attempted, _fetch_error

    if _cached_settings is not None and not force_refresh:
        return _cached_settings

    if _fetch_attempted and not force_refresh:
        # Already tried and failed, don't retry
        return {"_error": _fetch_error}

    _fetch_attempted = True

    try:
        from .zuora_client import get_zuora_client

        client = get_zuora_client()
        result = client.get_settings_batch()

        if not result.get("success"):
            _fetch_error = result.get("error", "Failed to fetch settings")
            logger.warning(f"Failed to fetch Zuora settings: {_fetch_error}")
            return {"_error": _fetch_error}

        # Parse responses into a structured format
        settings = {}
        for response in result.get("data", {}).get("responses", []):
            url = response.get("url", "").lstrip("/")
            body = response.get("response", {}).get("body", {})
            status = response.get("response", {}).get("status", "")

            if "200" in str(status):
                settings[url] = body
            else:
                logger.warning(f"Setting {url} returned status: {status}")

        _cached_settings = settings
        logger.info(f"Successfully fetched {len(settings)} Zuora settings")
        return settings

    except Exception as e:
        _fetch_error = str(e)
        logger.warning(f"Exception fetching Zuora settings: {_fetch_error}")
        return {"_error": _fetch_error}


def get_available_charge_models() -> List[str]:
    """Get list of charge models enabled in this Zuora tenant."""
    settings = fetch_environment_settings()
    if "_error" in settings:
        return []

    charge_models_data = settings.get("charge-models", {})

    # Handle response structure: {"chargeModels": ["FlatFee", "PerUnit", ...]}
    if isinstance(charge_models_data, dict):
        models = charge_models_data.get("chargeModels", [])
        # Models can be strings or dicts
        result = []
        for cm in models:
            if isinstance(cm, str):
                result.append(cm)
            elif isinstance(cm, dict):
                result.append(cm.get("name") or cm.get("chargeModel", ""))
        return result
    elif isinstance(charge_models_data, list):
        # Direct list of strings or dicts
        result = []
        for cm in charge_models_data:
            if isinstance(cm, str):
                result.append(cm)
            elif isinstance(cm, dict):
                result.append(cm.get("name") or cm.get("chargeModel", ""))
        return result
    return []


def get_available_billing_periods() -> List[str]:
    """Get list of billing periods enabled in this Zuora tenant."""
    settings = fetch_environment_settings()
    if "_error" in settings:
        return []

    billing_periods_data = settings.get("billing-periods", {})

    # Handle response structure: {"billingPeriods": ["Month", "Quarter", ...]}
    if isinstance(billing_periods_data, dict):
        periods = billing_periods_data.get("billingPeriods", [])
        result = []
        for bp in periods:
            if isinstance(bp, str):
                result.append(bp)
            elif isinstance(bp, dict):
                result.append(bp.get("name") or bp.get("billingPeriod", ""))
        return result
    elif isinstance(billing_periods_data, list):
        result = []
        for bp in billing_periods_data:
            if isinstance(bp, str):
                result.append(bp)
            elif isinstance(bp, dict):
                result.append(bp.get("name") or bp.get("billingPeriod", ""))
        return result
    return []


def get_available_billing_cycle_types() -> List[str]:
    """Get list of billing cycle types enabled in this Zuora tenant."""
    settings = fetch_environment_settings()
    if "_error" in settings:
        return []

    bct_data = settings.get("billing-cycle-types", {})

    # Handle response structure: {"billingCycleTypes": ["DefaultFromCustomer", ...]}
    if isinstance(bct_data, dict):
        types = bct_data.get("billingCycleTypes", [])
        result = []
        for b in types:
            if isinstance(b, str):
                result.append(b)
            elif isinstance(b, dict):
                result.append(b.get("name") or b.get("billCycleType", ""))
        return result
    elif isinstance(bct_data, list):
        result = []
        for b in bct_data:
            if isinstance(b, str):
                result.append(b)
            elif isinstance(b, dict):
                result.append(b.get("name") or b.get("billCycleType", ""))
        return result
    return []


def get_available_currencies() -> List[str]:
    """Get list of currencies enabled in this Zuora tenant."""
    settings = fetch_environment_settings()
    if "_error" in settings:
        return []

    currencies_data = settings.get("currencies", {})

    if isinstance(currencies_data, list):
        return [c.get("currencyCode") for c in currencies_data if c.get("active", True)]
    elif isinstance(currencies_data, dict):
        currencies = currencies_data.get("currencies", [])
        return [c.get("currencyCode") for c in currencies if c.get("active", True)]
    return []


def get_default_currency() -> str:
    """
    Get the default currency from Zuora environment settings.

    Returns the first active currency from the tenant, or "USD" as fallback.
    """
    currencies = get_available_currencies()
    if currencies:
        return currencies[0]
    return "USD"


def get_available_uoms() -> List[Dict[str, Any]]:
    """Get list of units of measure defined in this Zuora tenant.

    Returns full UOM objects with name, displayAs, precision, roundingMode,
    active status, usageLogFileLabel, and id.
    """
    settings = fetch_environment_settings()
    if "_error" in settings:
        return []

    uom_data = settings.get("units-of-measure", {})

    if isinstance(uom_data, dict):
        return uom_data.get("unitsOfMeasure", [])
    elif isinstance(uom_data, list):
        return uom_data
    return []


def get_available_uom_names() -> List[str]:
    """Get list of active UOM names (strings only) for validation."""
    uoms = get_available_uoms()
    return [uom.get("name", "") for uom in uoms if uom.get("active", True)]


def get_billing_rules() -> Dict[str, Any]:
    """Get billing rules configuration."""
    settings = fetch_environment_settings()
    if "_error" in settings:
        return {}
    return settings.get("billing-rules", {})


def get_subscription_settings() -> Dict[str, Any]:
    """Get subscription settings configuration."""
    settings = fetch_environment_settings()
    if "_error" in settings:
        return {}
    return settings.get("subscription-settings", {})


def get_raw_settings() -> Dict[str, Any]:
    """Get all raw settings data."""
    return fetch_environment_settings()


def is_settings_loaded() -> bool:
    """Check if settings have been successfully loaded."""
    return _cached_settings is not None


def get_fetch_error() -> Optional[str]:
    """Get the error message if settings fetch failed."""
    return _fetch_error


def get_environment_summary() -> str:
    """Get a formatted summary of the Zuora environment settings."""
    settings = fetch_environment_settings()

    if "_error" in settings:
        return f"Could not fetch Zuora settings: {settings['_error']}\nUsing default values."

    summary = "## Zuora Environment Settings\n\n"

    # Currencies
    currencies = get_available_currencies()
    summary += f"**Currencies ({len(currencies)}):** {', '.join(currencies[:10])}"
    if len(currencies) > 10:
        summary += f" ... and {len(currencies) - 10} more"
    summary += "\n\n"

    # Charge Models
    charge_models = get_available_charge_models()
    summary += f"**Charge Models ({len(charge_models)}):**\n"
    for cm in charge_models:
        summary += f"  - {cm}\n"
    summary += "\n"

    # Billing Periods
    billing_periods = get_available_billing_periods()
    summary += f"**Billing Periods ({len(billing_periods)}):**\n"
    for bp in billing_periods:
        summary += f"  - {bp}\n"
    summary += "\n"

    # Billing Cycle Types
    billing_cycle_types = get_available_billing_cycle_types()
    summary += f"**Billing Cycle Types ({len(billing_cycle_types)}):**\n"
    for bct in billing_cycle_types:
        summary += f"  - {bct}\n"
    summary += "\n"

    # Units of Measure
    uom_names = get_available_uom_names()
    summary += f"**Units of Measure ({len(uom_names)}):**\n"
    for uom in uom_names:
        summary += f"  - {uom}\n"
    summary += "\n"

    # Key Billing Rules
    billing_rules = get_billing_rules()
    if billing_rules:
        summary += "**Billing Rules:**\n"
        summary += f"  - Prorate recurring monthly: {billing_rules.get('prorateRecurringMonthlyCharges', 'N/A')}\n"
        summary += f"  - Days in month: {billing_rules.get('daysInMonth', 'N/A')}\n"
        summary += f"  - Proration unit: {billing_rules.get('prorationUnit', 'N/A')}\n"

    return summary


def get_environment_context_for_prompt() -> str:
    """
    Get a concise environment context string suitable for appending to system prompts.

    Returns a shorter format than get_environment_summary() for prompt efficiency.
    """
    settings = fetch_environment_settings()

    if "_error" in settings:
        return "\n## Zuora Environment\nSettings could not be loaded. Use default values.\n"

    lines = ["\n## Zuora Environment Context\n"]

    # Currencies (compact)
    currencies = get_available_currencies()
    if currencies:
        lines.append(f"**Currencies:** {', '.join(currencies[:5])}")
        if len(currencies) > 5:
            lines.append(f" (+{len(currencies) - 5} more)")
        lines.append("\n")

    # Charge Models (important for payload generation)
    charge_models = get_available_charge_models()
    if charge_models:
        lines.append(f"**Available Charge Models:** {', '.join(charge_models)}\n")

    # Billing Periods (important for payload generation)
    billing_periods = get_available_billing_periods()
    if billing_periods:
        lines.append(f"**Available Billing Periods:** {', '.join(billing_periods)}\n")

    # Billing Cycle Types
    billing_cycle_types = get_available_billing_cycle_types()
    if billing_cycle_types:
        lines.append(
            f"**Available Bill Cycle Types:** {', '.join(billing_cycle_types)}\n"
        )

    # Units of Measure (important for usage charge validation)
    uom_names = get_available_uom_names()
    if uom_names:
        lines.append(f"**Available UOMs:** {', '.join(uom_names)}\n")

    # Key billing rules
    billing_rules = get_billing_rules()
    if billing_rules:
        lines.append(
            f"**Proration:** {billing_rules.get('prorationUnit', 'N/A')}, "
            f"Days in Month: {billing_rules.get('daysInMonth', 'N/A')}\n"
        )

    lines.append("\nUse these values when generating payloads for this Zuora tenant.\n")

    return "".join(lines)


def clear_cache():
    """Clear the cached settings (for testing or refresh)."""
    global _cached_settings, _fetch_attempted, _fetch_error
    _cached_settings = None
    _fetch_attempted = False
    _fetch_error = None
