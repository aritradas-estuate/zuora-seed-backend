# ARCHITECTURE.md

Architecture and design documentation for the Zuora Seed Agent.

## Overview

### Framework Stack
- **AWS Bedrock AgentCore** - Deployment and runtime infrastructure
- **Strands Agents** - Agent framework for tool-based AI interactions
- **Pydantic** - Request/response validation and domain models

### Core Components

```
agentcore_app.py          # Entry point with @app.entrypoint decorator
agents/
  zuora_agent.py          # Agent factory with persona-specific system prompts
  tools.py                # All agent tools (~30 tools, 2400+ lines)
  models.py               # Pydantic models for API payloads and domain objects
  zuora_client.py         # Zuora API client with OAuth
  config.py               # Environment configuration
test_agent.py             # Interactive test harness (PM, Zuora API, Billing Architect tests)
```

### Persona System

The agent supports two personas selected via `ChatRequest.persona`:

1. **ProductManager** - Executes Zuora API operations (create/update products, rate plans, charges)
2. **BillingArchitect** - Advisory-only mode; generates configuration payloads without executing writes

Persona routing in `agentcore_app.py:get_agent_for_persona()` creates cached agents with persona-specific tools and system prompts.

### Tool Categories

Tools in `agents/tools.py` use the `@tool` decorator from strands. Key categories:

- **Zuora API (Read)**: `connect_to_zuora`, `list_zuora_products`, `get_zuora_product`, `get_zuora_rate_plan_details`
- **Zuora API (Write)**: `update_zuora_product`, `update_zuora_rate_plan`, `update_zuora_charge`
- **Payload Creation**: `create_product`, `create_rate_plan`, `create_charge` - generate payloads with smart defaults and placeholders
- **Payload Management**: `get_payloads`, `update_payload`, `create_payload` - manipulate JSON payloads in agent state
- **Billing Architect Advisory**: `generate_prepaid_config`, `generate_workflow_config`, `generate_notification_rule`, `generate_order_payload`, `explain_field_lookup`, `generate_multi_attribute_pricing`

### Placeholder System

The agent generates payloads **immediately** even with incomplete information using placeholders:

#### How It Works
- When users provide partial information, payloads are created with `<<PLACEHOLDER:FieldName>>` for missing required fields
- Smart defaults are applied automatically (e.g., today's date for `effectiveStartDate`, USD for currency)
- Users can fill placeholders iteratively using `update_payload(api_type, field_path, new_value)`
- Placeholders are automatically removed when fields are updated
- `get_payloads()` warns about remaining placeholders before execution

#### Example
```json
{
  "payload": {
    "name": "Analytics Pro",
    "sku": "<<PLACEHOLDER:sku>>",
    "effectiveStartDate": "2024-12-03"
  },
  "zuora_api_type": "product_create",
  "payload_id": "abc123",
  "_placeholders": ["sku"]
}
```

#### Benefits
- **Faster interaction**: No need to gather all info upfront
- **Progressive refinement**: Build payloads iteratively
- **Clear tracking**: `_placeholders` field shows what's missing
- **Validation**: Basic validation on update (dates, IDs)

#### Testing
Run placeholder tests: `python test_placeholders.py`

### State Management

Tools access shared state via the strands context:
```python
@tool(context=True)
def my_tool(context, ...):
    payloads = context.state.get(PAYLOADS_STATE_KEY)
    context.state.set(PAYLOADS_STATE_KEY, modified_payloads)
```

State keys: `PAYLOADS_STATE_KEY`, `ADVISORY_PAYLOADS_STATE_KEY`

### API Contract

Request (`ChatRequest`):
```json
{
  "persona": "ProductManager" | "BillingArchitect",
  "message": "User message",
  "conversation_id": "optional-session-id",
  "zuora_api_payloads": [{"payload": {...}, "zuora_api_type": "product"}]
}
```

Response (`ChatResponse`):
```json
{
  "conversation_id": "...",
  "answer": "Agent response",
  "citations": [...],
  "zuora_api_payloads": [...]
}
```

### Zuora API Client

`ZuoraClient` in `agents/zuora_client.py` handles:
- OAuth 2.0 token acquisition with automatic refresh
- Product catalog read operations via v1 Catalog API
- Multi-environment support (sandbox, production, EU regions)

Access via `get_zuora_client()` singleton.

## Conversation Management

The agent uses **session rotation** to limit conversation history for performance optimization:

### How It Works
- Conversation history is limited to ~3 recent turns (configurable via `MAX_CONVERSATION_TURNS`)
- Session IDs are rotated through N buckets using deterministic hashing
- Each bucket maintains independent conversation history
- After N turns, history naturally cycles and resets

### Performance Impact
- **Token reduction**: 70-90% decrease in input tokens for long conversations
- **Speed improvement**: 5-10x faster response times
- **Cost savings**: Significant reduction in API costs for multi-turn conversations

### Configuration
Set `MAX_CONVERSATION_TURNS` environment variable (default: 3):
```bash
MAX_CONVERSATION_TURNS=3  # Recommended for speed
MAX_CONVERSATION_TURNS=5  # More context, slower
```

### Implementation
- Function: `agentcore_app.py:get_bounded_session_id()`
- Strategy: Hash-based session ID rotation
- State: Agent state (payloads) persists independently of conversation history

### Trade-offs
- Context may reset after N turns
- Not a true "sliding window" but provides good balance of speed vs continuity
- State (payloads) is preserved across resets
