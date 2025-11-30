from bedrock_agentcore import BedrockAgentCoreApp
from typing import List
import uuid

from agents.zuora_agent import agent
from agents.models import (
    ChatRequest,
    ChatResponse,
    Citation,
    ZuoraApiPayload,
)
from agents.tools import PAYLOADS_STATE_KEY

app = BedrockAgentCoreApp()


def generate_mock_citations() -> List[Citation]:
    """Generate mock citations (placeholder for future Bedrock KB integration)."""
    return [
        Citation(
            id="citation-mock-1",
            title="Zuora Product Catalog Guide",
            uri="s3://zuora-kb/product-catalog-guide.pdf",
            url="https://knowledgecenter.zuora.com/Zuora_Billing/Build_products_and_prices"
        )
    ]


@app.entrypoint
def invoke(payload: dict) -> dict:
    """
    AgentCore entry point for Zuora Seed Agent with /chat API contract.

    Expected payload (ChatRequest):
    {
        "persona": "ProjectManager",
        "message": "I want to create a product called Gold Tier",
        "conversation_id": "1234",
        "zuora_api_payloads": [
            {"payload": {...}, "zuora_api_type": "product"},
            ...
        ]
    }

    Returns (ChatResponse):
    {
        "conversation_id": "1234",
        "answer": "Agent response...",
        "citations": [...],
        "zuora_api_payloads": [...]
    }
    """
    try:
        # Parse and validate request
        request = ChatRequest(**payload)
    except Exception as e:
        # Return error response matching ChatResponse structure
        error_conversation_id = payload.get("conversation_id") or str(uuid.uuid4())
        return {
            "conversation_id": error_conversation_id,
            "answer": f"Error: Invalid request format - {str(e)}",
            "citations": [],
            "zuora_api_payloads": payload.get("zuora_api_payloads", [])
        }

    # Generate or use existing conversation ID
    conversation_id = request.conversation_id or str(uuid.uuid4())

    # Initialize agent state with payloads
    payloads_data = [p.model_dump() for p in request.zuora_api_payloads]
    agent.state.set(PAYLOADS_STATE_KEY, payloads_data)

    # Build context-aware prompt
    prompt_parts = [f"User ({request.persona}): {request.message}"]

    if request.zuora_api_payloads:
        payload_types = set(p.zuora_api_type.value for p in request.zuora_api_payloads)
        prompt_parts.append(
            f"\n[Context: {len(request.zuora_api_payloads)} Zuora API payload(s) are available. "
            f"Types: {', '.join(payload_types)}. Use get_payloads() to view them.]"
        )

    full_prompt = "\n".join(prompt_parts)

    # Invoke agent
    try:
        response = agent(full_prompt, session_id=conversation_id)
        answer = str(response)
    except Exception as e:
        answer = f"Error processing request: {str(e)}"

    # Extract modified payloads from agent state
    modified_payloads_data = agent.state.get(PAYLOADS_STATE_KEY) or []
    modified_payloads = []
    for p in modified_payloads_data:
        try:
            modified_payloads.append(ZuoraApiPayload(**p))
        except Exception:
            # If payload doesn't validate, include as-is with raw data
            modified_payloads.append(ZuoraApiPayload(
                payload=p.get("payload", {}),
                zuora_api_type=p.get("zuora_api_type", "product"),
                payload_id=p.get("payload_id")
            ))

    # Generate mock citations
    citations = generate_mock_citations()

    # Build and return response
    chat_response = ChatResponse(
        conversation_id=conversation_id,
        answer=answer,
        citations=citations,
        zuora_api_payloads=modified_payloads
    )

    return chat_response.model_dump()


if __name__ == "__main__":
    app.run()
