# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

```bash
# Install dependencies
uv sync

# Run the agent locally
bedrock-agentcore run local

# Run tests interactively
python test_agent.py

# Run specific test
python test_agent.py ba1          # Single test by key
python test_agent.py a            # All PM tests
python test_agent.py z            # All Zuora API tests
python test_agent.py b            # All Billing Architect tests

# Deploy to AWS
bedrock-agentcore deploy
```

## Environment Configuration

Copy `.env.example` to `.env` and configure:
- `GEN_MODEL_ID` - Bedrock model ID (default: `us.meta.llama3-3-70b-instruct-v1:0`)
- `ZUORA_CLIENT_ID` / `ZUORA_CLIENT_SECRET` - Zuora OAuth credentials
- `ZUORA_ENV` - Environment: `sandbox`, `test`, `production`, `eu-sandbox`, `eu-production`
- `MAX_CONVERSATION_TURNS` - Conversation history limit (default: `3`) - see Conversation Management section below

## Architecture

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
- **Payload Management**: `get_payloads`, `update_payload`, `create_payload` - manipulate JSON payloads in agent state
- **Billing Architect Advisory**: `generate_prepaid_config`, `generate_workflow_config`, `generate_notification_rule`, `generate_order_payload`, `explain_field_lookup`, `generate_multi_attribute_pricing`

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
