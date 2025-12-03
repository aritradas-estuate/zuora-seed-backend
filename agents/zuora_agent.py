from strands import Agent
from strands.models import BedrockModel
from .config import GEN_MODEL_ID
from .observability import trace_function, get_tracer
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
    # Zuora API tools (create - payload generation)
    create_product,
    create_rate_plan,
    create_charge,
    # Zuora API tools (update - payload generation)
    update_zuora_product,
    update_zuora_rate_plan,
    update_zuora_charge,
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

## CRITICAL RULES
1. USE TOOLS for all actions.
2. NEVER output JSON directly. NEVER show tool parameters.
3. For payloads, use `create_payload` with user data. It validates and asks clarifying questions if needed.
4. Relay tool responses to the user.

## Workflow
1. **Understand**: Restate request (<h3>Understanding Your Request</h3>). Summarize changes.
2. **Clarify**: Proactively ask questions (<h3>Questions for Clarification</h3>) for ambiguities (currency, dates, definitions). Use <ol>.
3. **Execute**: Call tools. Confirm results.

## Formatting
- Use HTML: <h3> for sections, <strong> for key terms, <ol>/<ul> for lists.
- **Object References**: @{Product.Id}, @{ProductRatePlan.Id}, @{ProductRatePlanCharge.Id}.

## Default Values (Ask if unsure)
- StartDate: Today (YYYY-MM-DD). Currency: USD. Billing: In Advance, Month.
"""

BILLING_ARCHITECT_SYSTEM_PROMPT = """
You are "Zuora Seed - Billing Architect", an expert advisory AI for Zuora billing configuration.

## Role: Advisory-Only
You DO NOT execute write API calls. You GENERATE payloads and implementation guides for:
- Prepaid/Drawdown, Multi-Attribute Pricing, Workflows, Notifications, Orders.

## Workflow
1. **Understand**: Restate scenario (<h3>Understanding Your Request</h3>).
2. **Clarify**: Ask about preferences/edge cases (<h3>Questions for Clarification</h3>).
3. **Advise**: Provide detailed response:
   <ol>
     <li><strong>Overview</strong></li>
     <li><strong>Prerequisites</strong></li>
     <li><strong>Configuration Payloads</strong> (JSON in code blocks)</li>
     <li><strong>Implementation Steps</strong></li>
     <li><strong>Validation</strong></li>
   </ol>

## Formatting
- Use HTML tags. Preserve JSON in <code> blocks.
- **Object References**: @{Product.Id}, @{ProductRatePlan.Id}, @{ProductRatePlanCharge.Id}.

## Expertise
- Prepaid/Drawdown (Wallet, Auto-topup)
- Dynamic Pricing (fieldLookup)
- Workflows (Automation)
- Notifications (Events)
- Orders API (Subscription changes)
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
    # Create operations (payload generation)
    create_product,
    create_rate_plan,
    create_charge,
    # Update operations (payload generation)
    update_zuora_product,
    update_zuora_rate_plan,
    update_zuora_charge,
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

@trace_function(span_name="agent.create", attributes={"component": "agent_factory"})
def create_agent(persona: str) -> Agent:
    """
    Create an agent configured for the specified persona.

    Args:
        persona: The persona type ("ProductManager" or "BillingArchitect")

    Returns:
        Agent instance configured with appropriate system prompt and tools
    """
    tracer = get_tracer()

    with tracer.start_as_current_span("agent.create.model") as span:
        span.set_attribute("model_id", GEN_MODEL_ID)
        model = BedrockModel(
            model_id=GEN_MODEL_ID,
            streaming=False
        )

    with tracer.start_as_current_span("agent.create.configure") as span:
        span.set_attribute("persona", persona)

        if persona == "BillingArchitect":
            tools = SHARED_TOOLS + BILLING_ARCHITECT_TOOLS
            span.set_attribute("num_tools", len(tools))
            span.set_attribute("system_prompt_type", "billing_architect")
            return Agent(
                model=model,
                system_prompt=BILLING_ARCHITECT_SYSTEM_PROMPT,
                tools=tools,
            )
        else:  # Default to ProductManager
            tools = SHARED_TOOLS + PROJECT_MANAGER_TOOLS
            span.set_attribute("num_tools", len(tools))
            span.set_attribute("system_prompt_type", "product_manager")
            return Agent(
                model=model,
                system_prompt=PROJECT_MANAGER_SYSTEM_PROMPT,
                tools=tools,
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
