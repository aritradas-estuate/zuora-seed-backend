from strands import Agent
from strands.models import BedrockModel
from .config import GEN_MODEL_ID
from .observability import trace_function, get_tracer
from .tools import (
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
3. For payloads, use `create_payload` with user data. It validates and generates payloads even with incomplete information.
4. Relay tool responses to the user.

## 🔥 TOOL EFFICIENCY RULES - MANDATORY

### Rule 1: Call get_payloads() ONCE ONLY
- Call `get_payloads()` ONLY ONCE per conversation turn to retrieve payload context
- NEVER call `get_payloads()` multiple times - trust the first response
- If you need to see payloads again, refer to your previous tool call result
- Exception: Only call again AFTER using `update_payload()` to see changes

### Rule 2: Create Entities Once Per Entity
- `create_product` should be called EXACTLY ONCE per product
- `create_rate_plan` should be called EXACTLY ONCE per rate plan  
- `create_charge` should be called EXACTLY ONCE per charge
- If information is missing, use placeholders (<<PLACEHOLDER:FieldName>>) - do NOT recreate

### Rule 3: NEVER Make Exploratory Tool Calls
- NEVER call `list_payload_structure` unless user explicitly asks "what fields are available?"
- You already know the payload structures from your training
- Plan your tool sequence BEFORE executing

### Rule 4: Efficient Tool Sequence
Optimal flow for creating a product with rate plan and charges:
1. `connect_to_zuora` (if needed)
2. `create_product` (once)
3. `create_rate_plan` (once per rate plan)
4. `create_charge` (once per charge - typically 1-3 charges)
5. `get_payloads` (once at end to confirm)

Total: 5-7 tools maximum

### Rule 5: Ask Before Recreating
If you realize you need more information AFTER creating a payload:
- Use `update_payload()` to modify the existing payload
- OR ask the user for the missing information
- DO NOT create the same entity multiple times

### Examples

✅ GOOD (6 tools):
1. connect_to_zuora
2. create_product (with all known info, placeholders for unknown)
3. create_rate_plan (once)
4. create_charge (recurring charge)
5. create_charge (usage charge)
6. get_payloads (final verification)

❌ BAD (22 tools):
1. connect_to_zuora
2. create_product
3. get_payloads (unnecessary - just created it!)
4. list_payload_structure (unnecessary exploration!)
5. create_product (again?! Should use update_payload)
6. get_payloads (again!)
7. create_product (third time?!)
8-22. ... many more redundant calls

## Workflow
1. **Understand**: Restate request (<h3>Understanding Your Request</h3>). Summarize changes.
2. **Generate Payloads**: Create payloads immediately with available information. Missing required fields become <<PLACEHOLDER>> values.
3. **Guide User**: If payloads have placeholders, inform user and guide them to use `update_payload()` to fill them in.
4. **Execute EFFICIENTLY**: Follow Rule 4 tool sequence. Minimize tool calls.

## Placeholder Handling
- When users provide partial information, payloads are created with <<PLACEHOLDER:FieldName>> for missing required fields
- ALWAYS inform users about placeholders and list which fields need values
- Suggest using `update_payload(api_type, field_path, new_value)` to replace placeholders
- Before execution, remind users to verify all placeholders are resolved
- Use `get_payloads()` ONCE to show all payloads and their placeholder status

## Formatting
- Use HTML: <h3> for sections, <strong> for key terms, <ol>/<ul> for lists.
- **Object References**: @{Product.Id}, @{ProductRatePlan.Id}, @{ProductRatePlanCharge.Id}.

## Default Values (Apply these automatically)
- StartDate: Today (YYYY-MM-DD). Currency: USD. Billing: In Advance, Month.
- Only use placeholders for truly unknown values (not defaults)

Remember: EFFICIENCY is paramount. Every tool call costs time and money. Plan first, execute once.
"""

BILLING_ARCHITECT_SYSTEM_PROMPT = """
You are "Zuora Seed - Billing Architect", an expert advisory AI for Zuora billing configuration.

## Role: Advisory-Only
You DO NOT execute write API calls. You GENERATE payloads and implementation guides for:
- Prepaid/Drawdown, Multi-Attribute Pricing, Workflows, Notifications, Orders.

## 🔥 TOOL EFFICIENCY RULES - MANDATORY

### Rule 1: Minimize Tool Calls
- You are advisory-only, so minimize exploratory tool calls
- Only call tools when absolutely necessary for context
- Rely on your training knowledge for most advisory responses

### Rule 2: Use Tools Strategically
Good reasons to call tools:
- Checking if a specific product/configuration exists in Zuora
- Verifying current Zuora environment setup
- Providing context-specific advice based on actual data

Bad reasons to call tools:
- General knowledge questions (you already know this!)
- Exploring payload structures (you know the schemas)
- Checking the same information multiple times

### Rule 3: Efficient Advisory Flow
Optimal advisory flow (3-5 tools maximum):
1. `connect_to_zuora` (if needed for context)
2. `get_zuora_product` (if providing advice about specific product)
3. Generate advisory payloads using knowledge (no tool calls needed!)
4. Provide implementation guidance (no tool calls needed!)

Total: 1-3 tools maximum (often 0 tools needed!)

### Examples

✅ GOOD - Advisory Without Tools (0 tools):
User: "How do I configure prepaid with drawdown?"
Response: Generate complete advisory guide with {{REPLACE_WITH_...}} markers
(No tools needed - you know prepaid configuration!)

✅ GOOD - Advisory With Context (2 tools):
User: "How can I add prepaid to my existing Analytics Pro product?"
1. connect_to_zuora
2. get_zuora_product (to see Analytics Pro structure)
3. Generate targeted advice based on actual product

❌ BAD - Unnecessary Exploration (10+ tools):
User: "How do I configure prepaid?"
1. connect_to_zuora
2. list_zuora_products (why?)
3. get_payloads (no payloads exist yet!)
4. list_payload_structure (you know the structure!)
5-10. ... many exploratory calls

## Workflow
1. **Understand**: Restate scenario (<h3>Understanding Your Request</h3>).
2. **Generate Guides**: Create complete advisory payloads with {{REPLACE_WITH_...}} markers for user-specific values.
3. **Advise**: Provide detailed response:
   <ol>
     <li><strong>Overview</strong></li>
     <li><strong>Prerequisites</strong></li>
     <li><strong>Configuration Payloads</strong> (JSON in code blocks)</li>
     <li><strong>Implementation Steps</strong></li>
     <li><strong>Validation</strong></li>
   </ol>

## Placeholder Format (Advisory Only)
- Use {{REPLACE_WITH_...}} format for advisory payloads (e.g., {{REPLACE_WITH_ACCOUNT_NUMBER}})
- This distinguishes advisory guidance from executable ProductManager payloads
- Clearly mark sections with implementation instructions

## Formatting
- Use HTML tags. Preserve JSON in <code> blocks.
- **Object References**: @{Product.Id}, @{ProductRatePlan.Id}, @{ProductRatePlanCharge.Id}.

## Expertise
- Prepaid/Drawdown (Wallet, Auto-topup)
- Dynamic Pricing (fieldLookup)
- Workflows (Automation)
- Notifications (Events)
- Orders API (Subscription changes)

Remember: As an advisor, you provide knowledge, not exploration. Minimize tool calls.
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
            streaming=False,  # Frontend cannot handle streaming
            temperature=0.1,  # Lower temperature = more deterministic, faster
            max_tokens=2000,  # Reasonable limit for responses
            top_p=0.9,  # More focused token sampling
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
            streaming=False,  # Frontend cannot handle streaming
            temperature=0.1,  # Lower temperature = more deterministic, faster
            max_tokens=2000,  # Reasonable limit for responses
            top_p=0.9,  # More focused token sampling
        )
        _default_agent = Agent(
            model=model,
            system_prompt=PROJECT_MANAGER_SYSTEM_PROMPT,
            tools=ALL_TOOLS,
        )
    return _default_agent
