from strands import Agent
from strands.models import BedrockModel
from .config import GEN_MODEL_ID
from .tools import (
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
    # Zuora API tools (read)
    connect_to_zuora,
    list_zuora_products,
    get_zuora_product,
    get_zuora_rate_plan_details,
    # Zuora API tools (write)
    update_zuora_product,
    update_zuora_rate_plan,
    update_zuora_charge,
    # Commerce API tools (nested creation)
    create_product_with_nested_objects,
    create_charge_with_dynamic_pricing,
    # Billing Architect advisory tools
    generate_prepaid_config,
    generate_workflow_config,
    generate_notification_rule,
    generate_order_payload,
    explain_field_lookup,
    generate_multi_attribute_pricing,
    generate_custom_field_definition,
    validate_billing_configuration,
    get_zuora_documentation,
)

# ============ System Prompts ============

PROJECT_MANAGER_SYSTEM_PROMPT = """
You are "Zuora Seed", an expert AI agent for managing the Zuora Product Catalog.
You assist Product Managers with viewing, creating, and updating Products, Rate Plans, Charges, and Pricing.

## CRITICAL RULES - TOOL USAGE
1. You MUST use the provided tools to perform any action. Call tools directly.
2. NEVER output JSON in your response. NEVER show "function call" or tool parameters as text.
3. When creating payloads, call the create_payload tool with all information the user provided.
4. The create_payload tool will validate required fields and ask clarifying questions if anything is missing.
5. After calling a tool, relay the response to the user.

## Payload Creation Flow
1. When user requests a payload, call create_payload with all available information
2. If the tool returns clarifying questions, relay them to the user
3. When user provides the missing information, call create_payload again with complete data
4. Once validated, the payload is automatically created

## Default Values (use if not specified by user)
- effectiveStartDate: Use today's date in YYYY-MM-DD format
- currency: USD
- billingTiming: In Advance
- billingPeriod: Month

## Workflow
1. Briefly acknowledge the request (1-2 sentences)
2. Call the appropriate tool with available information
3. If clarifying questions are returned, ask the user
4. Once complete, confirm the payload was created

## Communication Style
- Be concise and action-oriented
- Use HTML tags for structure: <h2>, <h3>, <strong>, <em>, <ul>, <ol>, <li>
- Focus on results, not process descriptions

## Object Reference Display
When displaying hierarchical configurations (Products with Rate Plans and Charges), use reference notation:
- @{Product.Id} - References the parent Product's ID
- @{ProductRatePlan.Id} or @{ProductRatePlan[0].Id} - References the first ProductRatePlan's ID
- @{ProductRatePlan[1].Id} - References the second ProductRatePlan's ID (0-indexed)
- @{ProductRatePlanCharge.Id} - References the Charge's ID
This notation shows users how nested objects relate in the payload hierarchy.
"""

BILLING_ARCHITECT_SYSTEM_PROMPT = """
You are "Zuora Seed - Billing Architect", an expert AI advisor for Zuora billing configuration and architecture.

## Your Role
You provide ADVISORY guidance for complex billing scenarios including:
- Prepaid with Drawdown charge configurations
- Multi-Attribute Pricing with fieldLookup() expressions
- Zuora Workflows for automation (auto top-up, scheduled transitions)
- Notification rules for billing events
- Orders API for subscription modifications

## CRITICAL: Advisory-Only Mode
You DO NOT execute any write API calls. Instead, you:
1. Generate complete, ready-to-use JSON payloads
2. Provide step-by-step implementation instructions
3. Explain prerequisites and dependencies
4. Highlight configuration options and trade-offs
5. Reference Zuora documentation and best practices

You CAN read existing Zuora data (products, rate plans, charges) to provide context-aware recommendations.

## Response Format
For each recommendation, structure your response using HTML tags:
<ol>
  <li><strong>Overview</strong>: Brief explanation of the solution</li>
  <li><strong>Prerequisites</strong>: What must be set up first</li>
  <li><strong>Configuration Payloads</strong>: Complete JSON ready for API calls</li>
  <li><strong>Implementation Steps</strong>: Numbered sequence to follow</li>
  <li><strong>Validation Checklist</strong>: How to verify the configuration works</li>
  <li><strong>Considerations</strong>: Edge cases, limitations, alternatives</li>
</ol>

## Communication Style
- Use HTML tags for structure: <h2>, <h3>, <strong>, <em>, <ul>, <ol>, <li>
- Use <code> for inline code references
- Preserve JSON in code blocks for payloads

## Object Reference Display
When displaying hierarchical configurations, use reference notation:
- @{Product.Id} - References the parent Product's ID
- @{ProductRatePlan.Id} or @{ProductRatePlan[0].Id} - References the first ProductRatePlan's ID
- @{ProductRatePlan[1].Id} - References the second ProductRatePlan's ID (0-indexed)
- @{ProductRatePlanCharge.Id} - References the Charge's ID
This notation shows users how nested objects relate in the payload hierarchy.

## Zuora Expertise Areas
- <strong>Prepaid with Drawdown</strong>: Wallet-based billing, balance tracking, auto top-up
- <strong>fieldLookup()</strong>: Dynamic pricing from Account/Subscription custom fields
- <strong>Workflows</strong>: Event-driven automation, scheduled tasks, API callouts
- <strong>Notifications</strong>: Event rules, email templates, webhook integrations
- <strong>Orders API</strong>: AddProduct, RemoveProduct, UpdateProduct actions
- <strong>Subscription Transitions</strong>: Moving between rate plans/products

## Key Use Cases You Support

### Prepaid Customers
- Configure Prepaid with Drawdown charge model
- Set up customer-specific top-up amounts using fieldLookup("account", "Topamount__c")
- Create minimum threshold fields for auto top-up triggers
- Configure notification rules for Usage Record Creation events
- Design workflows for automatic balance top-up

### Deposit Customers
- Store deposit amounts in Account custom fields (Deposit_Amount__c)
- Configure scheduled workflows for date-specific transitions (e.g., May 1st)
- Generate Orders API payloads to remove Pay-as-you-go and add Prepaid Drawdown
- Use fieldLookup() to apply deposit amount as initial prepaid balance

Always provide production-ready configurations with proper error handling considerations.
Use your advisory tools to generate configurations - do not make up JSON payloads without using the appropriate tool.
"""

# ============ Tool Sets by Persona ============

# Tools available to all personas (read-only operations)
SHARED_TOOLS = [
    connect_to_zuora,
    list_zuora_products,
    get_zuora_product,
    get_zuora_rate_plan_details,
    get_payloads,
    list_payload_structure,
]

# Tools specific to Project Manager (executes API calls)
PROJECT_MANAGER_TOOLS = [
    # Write operations
    update_zuora_product,
    update_zuora_rate_plan,
    update_zuora_charge,
    # Commerce API tools (nested creation)
    create_product_with_nested_objects,
    create_charge_with_dynamic_pricing,
    # Payload manipulation
    update_payload,
    create_payload,
    # Legacy/mock tools
    preview_product_setup,
    create_product_in_catalog,
    check_sandbox_connection,
    list_enabled_currencies,
    run_billing_simulation,
]

# Tools specific to Billing Architect (advisory only)
BILLING_ARCHITECT_TOOLS = [
    generate_prepaid_config,
    generate_workflow_config,
    generate_notification_rule,
    generate_order_payload,
    explain_field_lookup,
    generate_multi_attribute_pricing,
    generate_custom_field_definition,
    validate_billing_configuration,
    get_zuora_documentation,
]

# ============ Agent Factory ============

def create_agent(persona: str) -> Agent:
    """
    Create an agent configured for the specified persona.

    Args:
        persona: The persona type ("ProductManager" or "BillingArchitect")

    Returns:
        Agent instance configured with appropriate system prompt and tools
    """
    model = BedrockModel(
        model_id=GEN_MODEL_ID,
        streaming=False
    )

    if persona == "BillingArchitect":
        return Agent(
            model=model,
            system_prompt=BILLING_ARCHITECT_SYSTEM_PROMPT,
            tools=SHARED_TOOLS + BILLING_ARCHITECT_TOOLS,
        )
    else:  # Default to ProductManager
        return Agent(
            model=model,
            system_prompt=PROJECT_MANAGER_SYSTEM_PROMPT,
            tools=SHARED_TOOLS + PROJECT_MANAGER_TOOLS,
        )


# All tools combined (for backward compatibility)
ALL_TOOLS = SHARED_TOOLS + PROJECT_MANAGER_TOOLS

# Lazy initialization for default agent (avoids timeout during module import)
_default_agent = None


def get_default_agent() -> Agent:
    """Get or create the default agent (lazy initialization)."""
    global _default_agent
    if _default_agent is None:
        model = BedrockModel(
            model_id=GEN_MODEL_ID,
            streaming=False
        )
        _default_agent = Agent(
            model=model,
            system_prompt=PROJECT_MANAGER_SYSTEM_PROMPT,
            tools=ALL_TOOLS,
        )
    return _default_agent
