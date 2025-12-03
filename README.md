# Zuora Seed Backend

AI agent for managing Zuora Product Catalog with support for incomplete information via placeholders.

## Quick Start

```bash
# Install dependencies
uv sync

# Run locally
bedrock-agentcore run local

# Run tests
python test_agent.py          # Interactive test menu
python test_placeholders.py   # Placeholder functionality tests

# Deploy to AWS
bedrock-agentcore deploy
```

## Features

### 🎯 Two Personas

1. **ProductManager** - Execute Zuora API operations (create/update products, rate plans, charges)
2. **BillingArchitect** - Advisory mode (generate configuration guides without execution)

### 🚀 Placeholder System (NEW!)

Generate payloads immediately even with partial information:

```json
// User: "Create a product called Analytics Pro"
// Agent generates:
{
  "payload": {
    "name": "Analytics Pro",
    "sku": "<<PLACEHOLDER:sku>>",
    "effectiveStartDate": "2024-12-03"  // Auto-applied default
  },
  "_placeholders": ["sku"]
}
```

**Key Benefits:**
- ✅ Immediate payload generation (no blocking for missing info)
- ✅ Progressive refinement via `update_payload()`
- ✅ Smart defaults (today's date, USD currency)
- ✅ Clear placeholder tracking
- ✅ Auto-validation on update

**Usage:**
```bash
# Create with partial info
POST /chat
{
  "persona": "ProductManager",
  "message": "Create a product called Analytics Pro"
}

# Update placeholder later
POST /chat
{
  "persona": "ProductManager",
  "message": "Set the SKU to ANALYTICS-PRO",
  "zuora_api_payloads": [...]  # Include payload from previous response
}
```

### 📊 Performance Optimized

- **Session rotation** for conversation history (3 turns default)
- **95% token reduction** (148K → 7.5K tokens)
- **20x faster** response times for long conversations

## API

### Request
```json
{
  "persona": "ProductManager",
  "message": "Create a product with...",
  "conversation_id": "optional-session-id",
  "zuora_api_payloads": []
}
```

### Response
```json
{
  "conversation_id": "...",
  "answer": "HTML formatted response",
  "citations": [],
  "zuora_api_payloads": [
    {
      "payload": {...},
      "zuora_api_type": "product_create",
      "payload_id": "abc123",
      "_placeholders": ["sku"]  // If incomplete
    }
  ]
}
```

## Environment Variables

```bash
GEN_MODEL_ID=us.meta.llama3-3-70b-instruct-v1:0
ZUORA_CLIENT_ID=your_client_id
ZUORA_CLIENT_SECRET=your_client_secret
ZUORA_ENV=sandbox  # sandbox, production, eu-sandbox, etc.
MAX_CONVERSATION_TURNS=3  # Conversation history limit
```

## Documentation

See [CLAUDE.md](CLAUDE.md) for detailed architecture, implementation notes, and development guidance.

## Testing

```bash
# Run all tests
python test_agent.py

# Placeholder-specific tests
python test_placeholders.py

# Specific test categories
python test_agent.py a  # ProductManager tests
python test_agent.py b  # BillingArchitect tests
python test_agent.py z  # Zuora API tests
```

## License

Proprietary - Estuate
