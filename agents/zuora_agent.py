import logging
from strands import Agent
from strands.models import BedrockModel
from .config import GEN_MODEL_ID
from .observability import trace_function, get_tracer
from .zuora_settings import (
    fetch_environment_settings,
    is_settings_loaded,
    get_fetch_error,
    get_environment_context_for_prompt,
)
from .tools import (
    # Utility tools
    get_current_date,
    get_zuora_environment_info,
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

logger = logging.getLogger(__name__)


# ============ Settings Initialization ============


def _initialize_zuora_settings() -> None:
    """
    Eagerly fetch Zuora environment settings on agent startup.
    Warns but continues if fetch fails.
    """
    logger.info("Initializing Zuora environment settings...")

    try:
        settings = fetch_environment_settings()

        if "_error" in settings:
            logger.warning(
                f"Could not fetch Zuora settings: {settings['_error']}. "
                "Agent will continue with default values."
            )
        else:
            logger.info(
                f"Loaded Zuora settings: {len(settings)} setting groups fetched."
            )
    except Exception as e:
        logger.warning(
            f"Exception during Zuora settings initialization: {e}. "
            "Agent will continue with default values."
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
3. **Ask Clarifying Questions**: If payloads have placeholders, ASK the user natural language questions to gather the missing information.
4. **Fill Placeholders**: When the user provides answers, YOU call `update_payload()` to fill in the values, then confirm what you did.
5. **Execute EFFICIENTLY**: Follow Rule 4 tool sequence. Minimize tool calls.

## Placeholder Handling - CRITICAL
- When users provide partial information, payloads are created with <<PLACEHOLDER:FieldName>> for missing required fields
- **NEVER tell users to run tool commands** - users CANNOT execute tools, only YOU can
- When placeholders exist, ASK CLARIFYING QUESTIONS in natural, conversational language:
  - "What pricing model would you like for this charge? Options from your Zuora environment: Flat Fee, Per Unit, Tiered, Volume, etc."
  - "What billing period should this use? Your environment supports: Month, Quarter, Annual, etc."
- When the user answers, YOU call `update_payload()` yourself to fill in the values
- After updating, CONFIRM what you did: "Done! I've set the charge model to Flat Fee Pricing and the billing period to Month."
- Show the updated payload summary so the user can verify
- Use `get_payloads()` ONCE at the end to show all payloads and their status

## Smart Inference (Conservative)
When creating charges, you MAY infer the charge model ONLY when the context is very clear:
- User explicitly says "flat fee" or "fixed monthly price" with a dollar amount and NO unit of measure → Flat Fee Pricing
- User explicitly says "per unit" or "per call" or "per API call" with a UOM → Per Unit Pricing
- User explicitly says "tiered pricing" or "volume tiers" → Tiered Pricing or Volume Pricing

When in doubt, DO NOT assume - create a placeholder and ask the user to clarify.

## Object References for Batch Creation
When creating multiple related objects in one request (Product → Rate Plan → Charge):
- The tools automatically generate object references: @{Object[index].Id}
- Examples:
  - Rate Plan referencing Product: "ProductId": "@{Product[0].Id}"
  - Charge referencing Rate Plan: "ProductRatePlanId": "@{ProductRatePlan[0].Id}"
- The index is 0-based and refers to the order of creation in the current batch
- For existing Zuora objects, provide the actual Zuora ID (e.g., "8a1234567890abcd")
- **NEVER use internal payload_id values** (like "b90ed37c") as foreign keys - always use object references or real Zuora IDs

## Formatting
- Use HTML: <h3> for sections, <strong> for key terms, <ol>/<ul> for lists.
- Field names use PascalCase to match Zuora v1 CRUD API (e.g., ProductId, ChargeType, BillingPeriod)

## Default Values (Apply these automatically)
- EffectiveStartDate: Today (YYYY-MM-DD). Currency: USD. Billing: In Advance, Month.
- EffectiveEndDate: 10 years from start date
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
    # Utility tools
    get_current_date,
    get_zuora_environment_info,
    # Zuora connection and read tools
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

    # Eagerly fetch Zuora settings (warn but continue on failure)
    with tracer.start_as_current_span("agent.create.settings") as span:
        _initialize_zuora_settings()
        span.set_attribute("settings_loaded", is_settings_loaded())
        if get_fetch_error():
            span.set_attribute("settings_error", get_fetch_error())

    # Get environment context to append to system prompts
    environment_context = get_environment_context_for_prompt()

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
            # Append environment context to system prompt
            system_prompt = BILLING_ARCHITECT_SYSTEM_PROMPT + environment_context
            return Agent(
                model=model,
                system_prompt=system_prompt,
                tools=tools,
            )
        else:  # Default to ProductManager
            tools = SHARED_TOOLS + PROJECT_MANAGER_TOOLS
            span.set_attribute("num_tools", len(tools))
            span.set_attribute("system_prompt_type", "product_manager")
            # Append environment context to system prompt
            system_prompt = PROJECT_MANAGER_SYSTEM_PROMPT + environment_context
            return Agent(
                model=model,
                system_prompt=system_prompt,
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
        # Initialize settings on first agent creation
        _initialize_zuora_settings()
        environment_context = get_environment_context_for_prompt()

        model = BedrockModel(
            model_id=GEN_MODEL_ID,
            streaming=False,  # Frontend cannot handle streaming
            temperature=0.1,  # Lower temperature = more deterministic, faster
            max_tokens=2000,  # Reasonable limit for responses
            top_p=0.9,  # More focused token sampling
        )
        _default_agent = Agent(
            model=model,
            system_prompt=PROJECT_MANAGER_SYSTEM_PROMPT + environment_context,
            tools=ALL_TOOLS,
        )
    return _default_agent
