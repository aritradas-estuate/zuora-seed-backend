from bedrock_agentcore import BedrockAgentCoreApp
from typing import List, Dict, TYPE_CHECKING
import uuid
import time
from agents.observability import (
    initialize_observability,
    get_tracer,
    get_metrics_collector,
    trace_function,
)

# Lazy imports - these are slow due to strands library
# Only import when actually needed (inside invoke function)
if TYPE_CHECKING:
    from agents.zuora_agent import create_agent
    from agents.models import ChatRequest, ChatResponse, Citation, ZuoraApiPayload
    from agents.html_formatter import markdown_to_html

app = BedrockAgentCoreApp()

# Cache agents by persona for efficiency
_agent_cache: Dict[str, any] = {}

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


def generate_mock_citations(persona: str) -> List[dict]:
    """Generate mock citations based on persona (placeholder for future Bedrock KB integration)."""
    if persona == "BillingArchitect":
        return [
            {
                "id": "citation-billing-1",
                "title": "Zuora Prepaid with Drawdown Guide",
                "uri": "s3://zuora-kb/prepaid-drawdown-guide.pdf",
                "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices/Prepaid_with_Drawdown",
            },
            {
                "id": "citation-billing-2",
                "title": "Zuora Workflows Documentation",
                "uri": "s3://zuora-kb/workflows-guide.pdf",
                "url": "https://knowledgecenter.zuora.com/Zuora_Central_Platform/Workflow",
            },
            {
                "id": "citation-billing-3",
                "title": "Zuora Orders API Reference",
                "uri": "s3://zuora-kb/orders-api-reference.pdf",
                "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Manage_subscription_transactions/Orders",
            },
        ]
    else:
        # Default citations for ProductManager and other personas
        return [
            {
                "id": "citation-mock-1",
                "title": "Zuora Product Catalog Guide",
                "uri": "s3://zuora-kb/product-catalog-guide.pdf",
                "url": "https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices",
            }
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

            # Generate persona-specific citations
            citations = generate_mock_citations(persona)

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
