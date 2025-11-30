from strands import Agent
from strands.models import BedrockModel
from .config import GEN_MODEL_ID
from .tools import (
    preview_product_setup,
    create_product_in_catalog,
    check_sandbox_connection,
    list_enabled_currencies,
    run_billing_simulation,
    # Payload tools
    get_payloads,
    update_payload,
    create_payload,
    list_payload_structure,
    # Zuora API tools
    connect_to_zuora,
    list_zuora_products,
    get_zuora_product,
    get_zuora_rate_plan_details,
    update_zuora_product,
    update_zuora_rate_plan,
    update_zuora_charge,
)

SYSTEM_PROMPT = """
You are "Zuora Seed", an expert AI agent for managing the Zuora Product Catalog.
You assist Product Managers with viewing, creating, and updating Products, Rate Plans, Charges, and Pricing.

You have access to a set of tools to interact with the Zuora API and Catalog.
ALWAYS use these tools to perform actions. Do not simulate actions.
"""

# Configure model from environment variable (streaming disabled for tool use)
model = BedrockModel(
    model_id=GEN_MODEL_ID,
    streaming=False
)

# All available tools
ALL_TOOLS = [
    # Zuora API tools
    connect_to_zuora,
    list_zuora_products,
    get_zuora_product,
    get_zuora_rate_plan_details,
    update_zuora_product,
    update_zuora_rate_plan,
    update_zuora_charge,
    # Catalog tools (legacy/mock)
    preview_product_setup,
    create_product_in_catalog,
    check_sandbox_connection,
    list_enabled_currencies,
    run_billing_simulation,
    # Payload tools
    get_payloads,
    update_payload,
    create_payload,
    list_payload_structure,
]

agent = Agent(
    model=model,
    system_prompt=SYSTEM_PROMPT,
    tools=ALL_TOOLS,
)
