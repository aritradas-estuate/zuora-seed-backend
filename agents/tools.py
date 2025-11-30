from strands import tool
from typing import Optional, List, Dict, Any
import datetime
from .models import ProductSpec

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