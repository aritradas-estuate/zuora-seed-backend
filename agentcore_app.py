from bedrock_agentcore import BedrockAgentCoreApp
from typing import List, Dict, Any, TYPE_CHECKING
import uuid
import time
import random
import logging
from agents.observability import (
    initialize_observability,
    get_tracer,
    get_metrics_collector,
    trace_function,
)

logger = logging.getLogger(__name__)

# Lazy imports - these are slow due to strands library
# Only import when actually needed (inside invoke function)
if TYPE_CHECKING:
    from agents.zuora_agent import create_agent
    from agents.models import ChatRequest, ChatResponse, Citation, ZuoraApiPayload
    from agents.html_formatter import markdown_to_html

app = BedrockAgentCoreApp()

# Cache agents by persona for efficiency
_agent_cache: Dict[str, Any] = {}

# State keys (hardcoded to avoid import)
PAYLOADS_STATE_KEY = "zuora_api_payloads"
ADVISORY_PAYLOADS_STATE_KEY = "advisory_payloads"


def get_bounded_session_id(conversation_id: str, max_turns: int = 3) -> str:
    """
    Generate rotating session IDs to limit conversation history.

    This function creates bounded session IDs by hashing the conversation_id and
    mapping it to one of N buckets. This limits conversation history accumulation
    while maintaining continuity within each bucket.

    Args:
        conversation_id: Original conversation ID from request
        max_turns: Number of turn buckets to rotate through (default: 3)

    Returns:
        Bounded session ID that rotates through max_turns buckets

    Example:
        For conversation_id="abc123" and max_turns=3:
        - Always maps to same bucket (0, 1, or 2)
        - Limits total history to max_turns conversation contexts
        - Provides ~70-90% token reduction for long conversations
    """
    if not conversation_id:
        return str(uuid.uuid4())

    import hashlib

    # Create deterministic hash from conversation_id
    hash_val = int(hashlib.md5(conversation_id.encode()).hexdigest(), 16)
    bucket = hash_val % max_turns
    return f"{conversation_id}_b{bucket}"


def get_agent_for_persona(persona: str):
    """Get or create an agent for the specified persona."""
    if persona not in _agent_cache:
        from agents.zuora_agent import create_agent

        _agent_cache[persona] = create_agent(persona)
    return _agent_cache[persona]


# Citation pools for content-aware selection
PRODUCT_MANAGER_CITATIONS = [
    {
        "id": "pm-1",
        "title": "Zuora Product Catalog Guide",
        "uri": "s3://zuora-kb/product-catalog-guide.pdf",
        "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices",
        "keywords": ["product", "catalog", "setup", "create"],
    },
    {
        "id": "pm-2",
        "title": "Charge Models Overview",
        "uri": "s3://zuora-kb/charge-models.pdf",
        "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/Charge_Models",
        "keywords": ["charge model", "flat fee", "per unit", "pricing model"],
    },
    {
        "id": "pm-3",
        "title": "Create Product Rate Plan Charges",
        "uri": "s3://zuora-kb/rate-plan-charges.pdf",
        "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/Create_product_rate_plan_charges",
        "keywords": ["rate plan", "charge", "create", "add"],
    },
    {
        "id": "pm-4",
        "title": "Tiered and Volume Pricing",
        "uri": "s3://zuora-kb/tiered-volume-pricing.pdf",
        "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/Tiered_and_Volume_Pricing",
        "keywords": ["tiered", "volume", "tier", "pricing", "graduated"],
    },
    {
        "id": "pm-5",
        "title": "Usage-Based Billing",
        "uri": "s3://zuora-kb/usage-billing.pdf",
        "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/Usage_Based_Billing",
        "keywords": ["usage", "metered", "consumption", "uom", "unit of measure"],
    },
    {
        "id": "pm-6",
        "title": "Product Catalog API Reference",
        "uri": "s3://zuora-kb/catalog-api.pdf",
        "url": "https://developer.zuora.com/v1-api-reference/api/tag/Catalog/",
        "keywords": ["api", "catalog", "list", "get", "products"],
    },
    {
        "id": "pm-7",
        "title": "Discount Charge Models",
        "uri": "s3://zuora-kb/discount-models.pdf",
        "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/Discount_Charge_Models",
        "keywords": ["discount", "percentage", "fixed amount", "promo"],
    },
    {
        "id": "pm-8",
        "title": "Billing Period Settings",
        "uri": "s3://zuora-kb/billing-period.pdf",
        "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/Billing_Period",
        "keywords": ["billing period", "month", "annual", "quarter", "recurring"],
    },
    {
        "id": "pm-9",
        "title": "Bill Cycle Day Configuration",
        "uri": "s3://zuora-kb/bill-cycle-day.pdf",
        "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/Bill_Cycle_Day",
        "keywords": ["bill cycle", "bcd", "billing day", "cycle"],
    },
    {
        "id": "pm-10",
        "title": "Product Effective Dates",
        "uri": "s3://zuora-kb/effective-dates.pdf",
        "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/Product_Effective_Dates",
        "keywords": ["effective date", "start date", "end date", "active"],
    },
    {
        "id": "pm-11",
        "title": "Multi-Currency Configuration",
        "uri": "s3://zuora-kb/currency.pdf",
        "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/Currency",
        "keywords": ["currency", "usd", "eur", "multi-currency", "price"],
    },
    {
        "id": "pm-12",
        "title": "Units of Measure (UOM)",
        "uri": "s3://zuora-kb/uom.pdf",
        "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/Units_of_Measure",
        "keywords": ["uom", "unit", "measure", "usage", "quantity"],
    },
    {
        "id": "pm-13",
        "title": "One-Time Charges",
        "uri": "s3://zuora-kb/one-time-charges.pdf",
        "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/One_Time_Charges",
        "keywords": ["one-time", "onetime", "setup fee", "activation"],
    },
    {
        "id": "pm-14",
        "title": "Recurring Charges",
        "uri": "s3://zuora-kb/recurring-charges.pdf",
        "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/Recurring_Charges",
        "keywords": ["recurring", "subscription", "monthly", "annual"],
    },
    {
        "id": "pm-15",
        "title": "Product Rate Plan Charge Tiers API",
        "uri": "s3://zuora-kb/charge-tiers-api.pdf",
        "url": "https://developer.zuora.com/v1-api-reference/api/tag/Product-Rate-Plan-Charge-Tiers/",
        "keywords": ["tier", "pricing tier", "api", "charge tier"],
    },
    {
        "id": "pm-16",
        "title": "Usage Billing - Prepayment, Credits and Commitment",
        "uri": "s3://zuora-kb/usage-prepayment-credits.pdf",
        "url": "https://docs.zuora.com/en/zuora-billing/bill-your-customer/usage-billing/usage-billing---prepayment-credits-and-commitment",
        "keywords": [
            "prepayment",
            "credits",
            "commitment",
            "prepaid",
            "drawdown",
            "usage",
            "wallet",
        ],
    },
    {
        "id": "pm-17",
        "title": "Usage Billing Overview",
        "uri": "s3://zuora-kb/usage-billing-overview.pdf",
        "url": "https://docs.zuora.com/en/zuora-billing/bill-your-customer/usage-billing/usage",
        "keywords": [
            "usage",
            "billing",
            "metered",
            "consumption",
            "usage charge",
            "usage-based",
        ],
    },
]

BILLING_ARCHITECT_CITATIONS = [
    {
        "id": "ba-1",
        "title": "Zuora Prepaid with Drawdown Guide",
        "uri": "s3://zuora-kb/prepaid-drawdown-guide.pdf",
        "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/Prepaid_with_Drawdown",
        "keywords": ["prepaid", "drawdown", "wallet", "credits", "balance"],
    },
    {
        "id": "ba-2",
        "title": "Zuora Workflows Documentation",
        "uri": "s3://zuora-kb/workflows-guide.pdf",
        "url": "https://knowledgecenter.zuora.com/Zuora_Central_Platform/Workflow",
        "keywords": ["workflow", "automation", "trigger", "task"],
    },
    {
        "id": "ba-3",
        "title": "Zuora Orders API Reference",
        "uri": "s3://zuora-kb/orders-api-reference.pdf",
        "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Manage_subscription_transactions/Orders",
        "keywords": ["order", "subscription", "add product", "remove"],
    },
]


def generate_mock_citations(persona: str, message: str = "") -> List[dict]:
    """
    Generate mock citations based on persona and message content.

    Uses content-aware selection to pick relevant citations based on keywords
    in the user's message, then fills remaining slots with random picks.
    Returns max 3 citations.

    Args:
        persona: User persona (ProductManager, BillingArchitect, etc.)
        message: User's message for content-aware keyword matching

    Returns:
        List of up to 3 citation dicts with id, title, uri, url fields
    """
    # Select citation pool based on persona
    if persona == "BillingArchitect":
        pool = BILLING_ARCHITECT_CITATIONS
    else:
        # ProductManager and other personas use product manager citations
        pool = PRODUCT_MANAGER_CITATIONS

    message_lower = message.lower()

    # Score citations by keyword matches in message
    scored = []
    for citation in pool:
        keywords = citation.get("keywords", [])
        score = sum(1 for kw in keywords if kw in message_lower)
        scored.append((score, random.random(), citation))  # random for tie-breaking

    # Sort by score (descending), then by random value for ties
    scored.sort(key=lambda x: (-x[0], x[1]))

    # Take top 3 citations
    selected = [c for _, _, c in scored[:3]]

    # Return without internal keywords field
    return [
        {
            "id": c["id"],
            "title": c["title"],
            "uri": c["uri"],
            "url": c["url"],
        }
        for c in selected
    ]


@app.entrypoint
@trace_function(span_name="agentcore.invoke", attributes={"component": "entrypoint"})
def invoke(payload: dict) -> dict:
    """
    AgentCore entry point for Zuora Seed Agent with /chat API contract.
    Supports multiple personas: ProductManager, BillingArchitect
    """
    # Initialize observability (safe to call multiple times)
    initialize_observability()
    tracer = get_tracer()
    metrics = get_metrics_collector()
    start_time = time.time()

    # Lazy import - only load heavy modules when actually invoked
    from agents.models import ChatRequest, ChatResponse, ZuoraApiPayload

    persona = payload.get("persona", "unknown")

    try:
        # Phase 1: Parse and validate request
        with tracer.start_as_current_span("request.parse") as span:
            try:
                request = ChatRequest(**payload)
                span.set_attribute("persona", request.persona)
                span.set_attribute("has_payloads", len(request.zuora_api_payloads) > 0)
                span.set_attribute("message_length", len(request.message))
                persona = request.persona
            except Exception as e:
                span.set_attribute("error", True)
                span.record_exception(e)
                # Return error response matching ChatResponse structure
                error_conversation_id = payload.get("conversation_id") or str(
                    uuid.uuid4()
                )
                total_duration_ms = (time.time() - start_time) * 1000
                metrics.record_request(persona, total_duration_ms, success=False)
                return {
                    "conversation_id": error_conversation_id,
                    "answer": f"Error: Invalid request format - {str(e)}",
                    "citations": [],
                    "zuora_api_payloads": payload.get("zuora_api_payloads", []),
                }

        # Generate or use existing conversation ID
        conversation_id = request.conversation_id or str(uuid.uuid4())

        # Phase 2: Get persona-specific agent
        with tracer.start_as_current_span("agent.get_or_create") as span:
            span.set_attribute("persona", persona)
            span.set_attribute("conversation_id", conversation_id)
            agent = get_agent_for_persona(persona)

        # Phase 3: Initialize agent state
        with tracer.start_as_current_span("state.initialize") as span:
            payloads_data = [p.model_dump() for p in request.zuora_api_payloads]
            span.set_attribute("num_payloads", len(payloads_data))
            agent.state.set(PAYLOADS_STATE_KEY, payloads_data)

            # Clear advisory payloads for Billing Architect sessions
            if persona == "BillingArchitect":
                agent.state.set(ADVISORY_PAYLOADS_STATE_KEY, [])

        # Phase 4: Build context-aware prompt
        with tracer.start_as_current_span("prompt.build") as span:
            prompt_parts = [f"User ({persona}): {request.message}"]

            if request.zuora_api_payloads:
                payload_types = set(
                    p.zuora_api_type.value for p in request.zuora_api_payloads
                )
                prompt_parts.append(
                    f"\n[Context: {len(request.zuora_api_payloads)} Zuora API payload(s) are available. "
                    f"Types: {', '.join(payload_types)}. Use get_payloads() to view them.]"
                )

            # Add persona-specific context hints
            if persona == "BillingArchitect":
                prompt_parts.append(
                    "\n[Mode: Advisory Only - Generate configurations and guidance. Do NOT execute write API calls.]"
                )

            full_prompt = "\n".join(prompt_parts)
            span.set_attribute("prompt_length", len(full_prompt))

        # Phase 5: Invoke agent (CRITICAL SPAN)
        with tracer.start_as_current_span("agent.invoke") as span:
            span.set_attribute("persona", persona)
            span.set_attribute("conversation_id", conversation_id)

            # Import MAX_CONVERSATION_TURNS for history limiting
            from agents.config import MAX_CONVERSATION_TURNS

            bounded_session_id = get_bounded_session_id(
                conversation_id, max_turns=MAX_CONVERSATION_TURNS
            )
            span.set_attribute("bounded_session_id", bounded_session_id)

            invoke_start = time.time()
            try:
                response = agent(full_prompt, session_id=bounded_session_id)
                invoke_duration_ms = (time.time() - invoke_start) * 1000
                span.set_attribute("duration_ms", invoke_duration_ms)
                span.set_attribute("success", True)

                # Record successful agent invocation
                metrics.record_agent_invocation(
                    persona, invoke_duration_ms, success=True
                )

                # Log tool usage for debugging - check if response has tool call info
                # This helps diagnose when the model describes actions without calling tools
                if hasattr(response, "tool_calls"):
                    tool_names = (
                        [tc.get("name", "unknown") for tc in response.tool_calls]
                        if response.tool_calls
                        else []
                    )
                    logger.info(
                        f"[AGENT] Tools called: {tool_names if tool_names else 'none'}"
                    )
                elif hasattr(response, "message") and hasattr(
                    response.message, "tool_calls"
                ):
                    tool_names = (
                        [
                            tc.get("name", "unknown")
                            for tc in response.message.tool_calls
                        ]
                        if response.message.tool_calls
                        else []
                    )
                    logger.info(
                        f"[AGENT] Tools called: {tool_names if tool_names else 'none'}"
                    )
                else:
                    # Log response length as a proxy for whether tools were called
                    # Very short responses with phrases like "I'll update" may indicate no tool was called
                    raw_answer_preview = str(response)[:200]
                    intent_phrases = [
                        "I'll update",
                        "Let me set",
                        "I'll change",
                        "Updating",
                        "I will update",
                        "Let me update",
                    ]
                    has_intent_phrase = any(
                        phrase in raw_answer_preview for phrase in intent_phrases
                    )
                    if has_intent_phrase:
                        logger.warning(
                            f"[AGENT] Response contains intent phrases but tool call info not available. "
                            f"Preview: {raw_answer_preview}..."
                        )
                    logger.info(
                        f"[AGENT] Invocation completed in {invoke_duration_ms:.0f}ms"
                    )

                raw_answer = str(response)
                # Convert markdown to HTML for formatted output
                from agents.html_formatter import markdown_to_html

                answer = markdown_to_html(raw_answer)

            except Exception as e:
                invoke_duration_ms = (time.time() - invoke_start) * 1000
                span.set_attribute("duration_ms", invoke_duration_ms)
                span.set_attribute("error", True)
                span.record_exception(e)

                # Record failed agent invocation
                metrics.record_agent_invocation(
                    persona, invoke_duration_ms, success=False
                )

                answer = f"<p>Error processing request: {str(e)}</p>"

        # Phase 6: Build response
        with tracer.start_as_current_span("response.build") as span:
            # Extract modified payloads from agent state
            modified_payloads_data = agent.state.get(PAYLOADS_STATE_KEY) or []
            modified_payloads = []
            for p in modified_payloads_data:
                try:
                    modified_payloads.append(ZuoraApiPayload(**p))
                except Exception:
                    # If payload doesn't validate, include as-is with raw data
                    modified_payloads.append(
                        ZuoraApiPayload(
                            payload=p.get("payload", {}),
                            zuora_api_type=p.get("zuora_api_type", "product"),
                            payload_id=p.get("payload_id"),
                        )
                    )

            # Check for payloads with placeholders and generate warning
            payloads_with_placeholders = [
                p for p in modified_payloads_data if p.get("_placeholders")
            ]
            if payloads_with_placeholders:
                from agents.html_formatter import generate_placeholder_warning_html

                placeholder_warning = generate_placeholder_warning_html(
                    payloads_with_placeholders
                )
                answer = placeholder_warning + answer

            # Add call-to-action at the end when payloads exist
            if modified_payloads_data:
                from agents.html_formatter import generate_payload_action_cta

                has_placeholders = len(payloads_with_placeholders) > 0
                action_cta = generate_payload_action_cta(has_placeholders)
                answer = answer + action_cta

            # Generate persona-specific citations (content-aware based on user message)
            citations = generate_mock_citations(persona, request.message)

            # Build and return response
            chat_response = ChatResponse(
                conversation_id=conversation_id,
                answer=answer,
                citations=citations,
                zuora_api_payloads=modified_payloads,
            )

            span.set_attribute("num_modified_payloads", len(modified_payloads))
            span.set_attribute("num_citations", len(citations))

        # Record successful request
        total_duration_ms = (time.time() - start_time) * 1000
        metrics.record_request(persona, total_duration_ms, success=True)

        return chat_response.model_dump()

    except Exception as e:
        # Record failed request
        total_duration_ms = (time.time() - start_time) * 1000
        metrics.record_request(persona, total_duration_ms, success=False)
        raise


if __name__ == "__main__":
    app.run()
