from strands import tool
from typing import Optional

# --- Mock Database ---
products_db = {}

# --- Product Manager Tools ---

@tool
def create_product(name: str, sku: str, effective_start: str, effective_end: Optional[str] = None, currency: str = "USD") -> str:
    """
    Creates a new product in the Zuora Product Catalog.
    
    Args:
        name: The name of the product.
        sku: The unique Stock Keeping Unit.
        effective_start: The start date of the product (YYYY-MM-DD).
        effective_end: (Optional) The end date of the product (YYYY-MM-DD).
        currency: The currency code (e.g., USD).
    """
    if sku in products_db:
        return f"Error: Product with SKU {sku} already exists."
    
    products_db[sku] = {
        "name": name,
        "sku": sku,
        "effective_start": effective_start,
        "effective_end": effective_end,
        "currency": currency,
        "description": "",
        "custom_fields": {},
        "rate_plans": []
    }
    return f"Product '{name}' (SKU: {sku}) created successfully."

@tool
def add_product_description(sku: str, description: str) -> str:
    """
    Adds or updates the description for a product.
    """
    if sku not in products_db:
        return f"Error: Product with SKU {sku} not found."
    
    products_db[sku]["description"] = description
    return f"Description added to product {sku}."

@tool
def add_custom_field(sku: str, field_name: str, field_value: str) -> str:
    """
    Adds a custom field to a product.
    """
    if sku not in products_db:
        return f"Error: Product with SKU {sku} not found."
    
    products_db[sku]["custom_fields"][field_name] = field_value
    return f"Custom field '{field_name}' set to '{field_value}' for product {sku}."

@tool
def add_rate_plan(product_sku: str, name: str, description: Optional[str] = None, effective_start: Optional[str] = None) -> str:
    """
    Adds a rate plan to an existing product.
    """
    if product_sku not in products_db:
        return f"Error: Product with SKU {product_sku} not found."
    
    rate_plan = {
        "name": name,
        "description": description,
        "effective_start": effective_start,
        "charges": []
    }
    products_db[product_sku]["rate_plans"].append(rate_plan)
    return f"Rate Plan '{name}' added to product {product_sku}."

@tool
def add_charge(product_sku: str, rate_plan_name: str, name: str, type: str, model: str, price: str, frequency: Optional[str] = None, trigger: Optional[str] = None) -> str:
    """
    Adds a charge to a specific rate plan.
    
    Args:
        product_sku: The SKU of the product.
        rate_plan_name: The name of the rate plan to add the charge to.
        name: Charge name.
        type: Charge type (Recurring, One-Time, Usage).
        model: Charge model (Flat Fee, Per Unit, etc.).
        price: Price string (e.g. "1200").
        frequency: Billing frequency (e.g. "Annual").
        trigger: Trigger condition (e.g. "Contract Effective").
    """
    if product_sku not in products_db:
        return f"Error: Product {product_sku} not found."
    
    product = products_db[product_sku]
    target_rp = None
    for rp in product["rate_plans"]:
        if rp["name"] == rate_plan_name:
            target_rp = rp
            break
    
    if not target_rp:
        return f"Error: Rate Plan '{rate_plan_name}' not found in product {product_sku}."
    
    charge = {
        "name": name,
        "type": type,
        "model": model,
        "price": price,
        "frequency": frequency,
        "trigger": trigger
    }
    target_rp["charges"].append(charge)
    return f"Charge '{name}' added to Rate Plan '{rate_plan_name}'."

@tool
def get_product_details(sku: str) -> str:
    """
    Retrieves full details of a product.
    """
    if sku not in products_db:
        # Try searching by name roughly
        for k, v in products_db.items():
            if v['name'].lower() == sku.lower():
                return str(v)
        return f"Product with SKU/Name {sku} not found."
    
    return str(products_db[sku])

@tool
def expire_product(sku: str, end_date: str) -> str:
    """
    Sets the end date for a product to expire it.
    """
    if sku not in products_db:
         # Try searching by name roughly
        found = False
        for k, v in products_db.items():
            if v['name'].lower() == sku.lower():
                sku = k
                found = True
                break
        if not found:
            return f"Product {sku} not found."

    products_db[sku]["effective_end"] = end_date
    return f"Product {sku} expired with end date {end_date}."

@tool
def update_product_field(sku: str, field: str, value: str) -> str:
    """
    Updates a top-level field of a product (name, sku, etc).
    """
    # Logic similar to expire
    if sku not in products_db:
        for k, v in products_db.items():
            if v['name'].lower() == sku.lower():
                sku = k
                break
        if sku not in products_db: return "Product not found."

    if field in products_db[sku]:
        products_db[sku][field] = value
        return f"Updated {field} to {value}."
    else:
        return f"Field {field} not found on product."

# --- Billing Architect Knowledge Tools ---
# Instead of tools, we'll put the knowledge in the system prompt to keep it simple and fast,
# but we could add a search_docs tool if the text was huge. The provided text is manageable in context.

