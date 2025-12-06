# ARCHITECTURE.md

Comprehensive architecture and design documentation for the Zuora Seed Agent.

## Table of Contents

1. [Overview](#1-overview)
2. [System Architecture Diagram](#2-system-architecture-diagram)
3. [Request Lifecycle](#3-request-lifecycle)
4. [Module Reference](#4-module-reference)
5. [Tool Reference](#5-tool-reference)
6. [Module Dependencies](#6-module-dependencies)
7. [Observability Architecture](#7-observability-architecture)
8. [Configuration Reference](#8-configuration-reference)
9. [Design Patterns](#9-design-patterns)
10. [Testing](#10-testing)

---

## 1. Overview

### 1.1 Framework Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Runtime | AWS Bedrock AgentCore | Deployment and HTTP infrastructure |
| Agent Framework | Strands Agents | Tool-based AI agent orchestration |
| LLM | Qwen 80B (via Bedrock) | Language model for reasoning |
| Validation | Pydantic | Request/response and domain models |
| HTTP Client | Requests | Zuora API communication |
| Observability | OpenTelemetry | Distributed tracing and metrics |

### 1.2 Core Components

```
zuora_seed_backend/
├── agentcore_app.py              # Entry point with @app.entrypoint decorator
├── agents/
│   ├── zuora_agent.py            # Agent factory with persona-specific prompts
│   ├── tools.py                  # 30+ LLM tools (~3,970 lines)
│   ├── models.py                 # Pydantic models (~520 lines)
│   ├── zuora_client.py           # Zuora REST API client (~610 lines)
│   ├── config.py                 # Environment configuration
│   ├── zuora_settings.py         # Dynamic tenant settings cache
│   ├── validation_schemas.py     # Payload validation & placeholders
│   ├── validation_utils.py       # Date/ID/SKU validators
│   ├── html_formatter.py         # Markdown to HTML conversion
│   ├── cache.py                  # TTL-based API response caching
│   └── observability.py          # OpenTelemetry tracing & metrics
├── test_agent.py                 # Interactive test harness
└── test_placeholders.py          # Placeholder system tests
```

### 1.3 Persona System

The agent supports two personas selected via `ChatRequest.persona`:

| Persona | Purpose | Tools Available |
|---------|---------|-----------------|
| **ProductManager** | Execute Zuora API operations | SHARED_TOOLS + PROJECT_MANAGER_TOOLS |
| **BillingArchitect** | Advisory-only configuration guidance | SHARED_TOOLS + BILLING_ARCHITECT_TOOLS |

---

## 2. System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              External Request                                    │
│                        (HTTP via AWS Bedrock AgentCore)                          │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                             agentcore_app.py                                     │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │ @app.entrypoint invoke(payload)                                          │    │
│  │ • get_bounded_session_id() ─── Session rotation for performance          │    │
│  │ • get_agent_for_persona() ──── Cached agent retrieval                    │    │
│  │ • generate_mock_citations() ── Knowledge base citations                  │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   │
            ┌──────────────────────┴──────────────────────┐
            │                                             │
            ▼                                             ▼
┌───────────────────────────┐               ┌───────────────────────────┐
│   ProductManager Persona   │               │  BillingArchitect Persona  │
│   (Executes API ops)       │               │   (Advisory only)          │
└─────────────┬─────────────┘               └─────────────┬─────────────┘
              │                                           │
              └─────────────────────┬─────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            agents/zuora_agent.py                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │ create_agent(persona) ─────────────────── Agent factory                  │    │
│  │ • _initialize_zuora_settings() ────────── Eager settings fetch           │    │
│  │ • get_default_agent() ─────────────────── Legacy compatibility           │    │
│  │ • SHARED_TOOLS ────────────────────────── Read-only tools                │    │
│  │ • PROJECT_MANAGER_TOOLS ───────────────── CRUD tools                     │    │
│  │ • BILLING_ARCHITECT_TOOLS ─────────────── Advisory tools                 │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              │                                         │
              ▼                                         ▼
┌───────────────────────────────────┐   ┌───────────────────────────────────┐
│       agents/tools.py             │   │      agents/zuora_client.py       │
│  ┌─────────────────────────────┐  │   │  ┌─────────────────────────────┐  │
│  │ 30+ @tool decorated funcs   │  │   │  │ ZuoraClient class           │  │
│  │ • Utility tools (2)         │──┼──▶│  │ • authenticate()            │  │
│  │ • Query tools (4)           │  │   │  │ • _request()                │  │
│  │ • Create tools (3)          │  │   │  │ • list_all_products()       │  │
│  │ • Update tools (3)          │  │   │  │ • get_product()             │  │
│  │ • Payload mgmt (4)          │  │   │  │ • get_settings_batch()      │  │
│  │ • Advisory tools (9)        │  │   │  └─────────────────────────────┘  │
│  └─────────────────────────────┘  │   └─────────────────┬─────────────────┘
└───────────────┬───────────────────┘                     │
                │                                         │
                │    ┌────────────────────────────────────┤
                │    │                                    │
                ▼    ▼                                    ▼
┌───────────────────────────────────┐   ┌───────────────────────────────────┐
│     Supporting Modules            │   │      Infrastructure               │
├───────────────────────────────────┤   ├───────────────────────────────────┤
│ models.py ─────── Pydantic models │   │ cache.py ──────── TTLCache        │
│ config.py ─────── Env vars        │   │ observability.py  OTel tracing    │
│ zuora_settings.py Tenant config   │   │                                   │
│ validation_schemas.py ─ Schemas   │   │        Zuora REST API             │
│ validation_utils.py ─── Validators│   │   POST /oauth/token               │
│ html_formatter.py ───── MD→HTML   │   │   GET  /v1/catalog/*              │
└───────────────────────────────────┘   │   POST /settings/batch-requests   │
                                        └───────────────────────────────────┘
```

---

## 3. Request Lifecycle

### 3.1 Complete Request Flow Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                           Complete Request Flow                                   │
└──────────────────────────────────────────────────────────────────────────────────┘

1. HTTP Request (via AWS Bedrock AgentCore)
   │
   ▼
2. agentcore_app.invoke(payload: dict)
   │
   ├─► initialize_observability()
   │
   ├─► Parse ChatRequest (Pydantic validation)
   │   └── Fields: persona, message, conversation_id, zuora_api_payloads
   │
   ├─► get_agent_for_persona(persona)
   │   └── zuora_agent.create_agent(persona)
   │       ├── _initialize_zuora_settings()
   │       │   └── zuora_settings.fetch_environment_settings()
   │       │       └── zuora_client.get_settings_batch()
   │       │
   │       ├── Create BedrockModel (Qwen 80B)
   │       │
   │       └── Create strands.Agent with:
   │           ├── System prompt (persona-specific)
   │           ├── Tools (SHARED + persona-specific)
   │           └── Environment context
   │
   ├─► Initialize Agent State
   │   └── agent.state.set(PAYLOADS_STATE_KEY, payloads_from_request)
   │
   ├─► Build Context-Aware Prompt
   │   └── "User (ProductManager): Create a product..."
   │       + "[Context: N payloads available...]"
   │
   ├─► get_bounded_session_id(conversation_id, max_turns)
   │   └── Hash-based session rotation for performance
   │
   ├─► Invoke Agent
   │   └── agent(prompt, session_id=bounded_session_id)
   │       │
   │       ├── LLM generates response with tool calls
   │       │
   │       └── Tools execute (examples):
   │           │
   │           ├── connect_to_zuora()
   │           │   └── zuora_client.check_connection()
   │           │       └── zuora_client.authenticate() [OAuth]
   │           │
   │           ├── create_product(name="Analytics Pro", ...)
   │           │   ├── Apply smart defaults (dates, SKU)
   │           │   ├── Validate fields
   │           │   └── create_payload()
   │           │       ├── validate_payload()
   │           │       ├── generate_placeholder_payload() [if missing]
   │           │       └── agent.state.set(PAYLOADS_STATE_KEY, [...])
   │           │
   │           └── get_payloads()
   │               └── Return payload summary table
   │
   ├─► Extract Payloads from Agent State
   │   └── agent.state.get(PAYLOADS_STATE_KEY)
   │
   ├─► Format Response
   │   ├── markdown_to_html(agent_response)
   │   ├── generate_placeholder_warning_html() [if placeholders exist]
   │   └── generate_mock_citations(persona, message)
   │
   └─► Return ChatResponse
       ├── conversation_id
       ├── answer (HTML)
       ├── citations
       └── zuora_api_payloads (modified payloads from state)
```

### 3.2 Step-by-Step Breakdown

| Step | Component | Function | Description |
|------|-----------|----------|-------------|
| 1 | AgentCore | HTTP Handler | Receives HTTP POST request |
| 2 | agentcore_app | `invoke()` | Main entry point decorated with `@app.entrypoint` |
| 3 | observability | `initialize_observability()` | Setup OpenTelemetry (idempotent) |
| 4 | models | `ChatRequest` | Pydantic validation of request |
| 5 | agentcore_app | `get_agent_for_persona()` | Get/create cached agent |
| 6 | zuora_agent | `create_agent()` | Factory creates persona-specific agent |
| 7 | zuora_settings | `fetch_environment_settings()` | Load tenant settings |
| 8 | Agent State | `state.set()` | Initialize payloads from request |
| 9 | agentcore_app | `get_bounded_session_id()` | Rotate session for performance |
| 10 | strands.Agent | `__call__()` | Invoke agent with prompt |
| 11 | tools | Various | Execute tool calls from LLM |
| 12 | html_formatter | `markdown_to_html()` | Format response |
| 13 | models | `ChatResponse` | Build and return response |

---

## 4. Module Reference

### 4.1 agentcore_app.py (Entry Point)

Main application entry point for AWS Bedrock AgentCore.

#### Functions

| Function | Purpose | Parameters | Returns | Called From |
|----------|---------|------------|---------|-------------|
| `invoke(payload)` | **Main entry point** - handles all requests | `payload: dict` | `dict` (ChatResponse) | AWS Bedrock runtime |
| `get_bounded_session_id(conversation_id, max_turns)` | Generate rotating session ID to limit history | `conversation_id: str`, `max_turns: int` | `str` | `invoke()` |
| `get_agent_for_persona(persona)` | Get or create cached agent by persona | `persona: str` | `Agent` | `invoke()` |
| `generate_mock_citations(persona, message)` | Generate content-aware citations | `persona: str`, `message: str` | `List[Citation]` | `invoke()` |

#### Global State

| Variable | Type | Purpose |
|----------|------|---------|
| `_agent_cache` | `Dict[str, Agent]` | Caches agents by persona |
| `PAYLOADS_STATE_KEY` | `str` | State key: `"zuora_api_payloads"` |
| `ADVISORY_PAYLOADS_STATE_KEY` | `str` | State key: `"advisory_payloads"` |

---

### 4.2 agents/zuora_agent.py (Agent Factory)

Creates and configures persona-specific Strands agents.

#### Functions

| Function | Purpose | Parameters | Returns | Called From |
|----------|---------|------------|---------|-------------|
| `create_agent(persona)` | **Agent factory** - creates persona-specific agent | `persona: str` | `Agent` | `agentcore_app.get_agent_for_persona()` |
| `_initialize_zuora_settings()` | Eagerly fetch Zuora tenant settings | None | None | `create_agent()` |
| `get_default_agent()` | Lazy initialization of default agent | None | `Agent` | Legacy/backwards compatibility |

#### Constants

| Constant | Contents | Used By |
|----------|----------|---------|
| `PROJECT_MANAGER_SYSTEM_PROMPT` | Instructions for ProductManager persona | `create_agent()` |
| `BILLING_ARCHITECT_SYSTEM_PROMPT` | Instructions for BillingArchitect persona | `create_agent()` |
| `SHARED_TOOLS` | `[get_current_date, get_zuora_environment_info, connect_to_zuora, list_zuora_products, get_zuora_product, get_zuora_rate_plan_details, get_payloads, list_payload_structure]` | `create_agent()` |
| `PROJECT_MANAGER_TOOLS` | `[create_product, create_rate_plan, create_charge, update_zuora_product, update_zuora_rate_plan, update_zuora_charge, update_payload, create_payload]` | `create_agent()` |
| `BILLING_ARCHITECT_TOOLS` | `[generate_prepaid_config, generate_workflow_config, generate_notification_rule, generate_order_payload, explain_field_lookup, generate_multi_attribute_pricing, generate_custom_field_definition, validate_billing_configuration, get_zuora_documentation]` | `create_agent()` |

---

### 4.3 agents/tools.py (LLM Tools) - ~3,970 lines

All tools available to the LLM agent, decorated with `@tool` from Strands.

#### Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `PAYLOADS_STATE_KEY` | `"zuora_api_payloads"` | State key for API payloads |
| `ADVISORY_PAYLOADS_STATE_KEY` | `"advisory_payloads"` | State key for advisory payloads |
| `CHARGE_MODEL_MAPPING` | `{"flat fee": "Flat Fee Pricing", ...}` | Maps friendly names to API values |

#### Helper Functions (Internal)

| Function | Line | Purpose | Parameters | Returns | Called From |
|----------|------|---------|------------|---------|-------------|
| `_find_existing_key(data, key)` | ~35 | Case-insensitive dict key lookup | `data: dict`, `key: str` | `Optional[str]` | `update_payload`, `create_payload` |
| `_to_crud_field_name(field)` | ~74 | Convert to PascalCase for CRUD API | `field: str` | `str` | `update_payload` |
| `_find_payload_by_name(payloads, name)` | ~90 | Fuzzy substring name matching | `payloads: List`, `name: str` | `Tuple[int, dict]` | `update_payload`, `update_zuora_*` |
| `_count_payloads_by_type(payloads, api_type)` | ~156 | Count payloads of specific type | `payloads: List`, `api_type: str` | `int` | `_get_product_object_reference` |
| `_get_product_object_reference(payloads, index)` | ~161 | Generate `@{Product[n].Id}` reference | `payloads: List`, `index: int` | `str` | `create_rate_plan` |
| `_get_rate_plan_object_reference(payloads, index)` | ~193 | Generate `@{ProductRatePlan[n].Id}` reference | `payloads: List`, `index: int` | `str` | `create_charge` |
| `_find_best_product_match(products, query)` | ~741 | Damerau-Levenshtein fuzzy matching | `products: List`, `query: str` | `Tuple[dict, float]` | `get_zuora_product` |
| `_format_product_details(product)` | ~795 | Format product for display | `product: dict` | `str` | `get_zuora_product` |
| `_normalize_charge_model(model)` | ~1363 | Map "flat fee" → "Flat Fee Pricing" | `model: str` | `str` | `create_charge` |
| `_validate_tier_boundaries(tiers)` | ~1371 | Check tier gaps/overlaps | `tiers: List[dict]` | `Tuple[bool, str]` | `create_charge` |
| `_normalize_tiers(tiers, model)` | ~1418 | Convert tier input to API format | `tiers: List`, `model: str` | `List[dict]` | `create_charge` |
| `_infer_charge_model_conservative(charge_type, tiers, price, uom, included, overage)` | ~1500 | Conservative charge model inference | Various | `Tuple[str, str]` | `create_charge` |
| `_normalize_uom(uom)` | ~1586 | Normalize UOM to valid tenant value | `uom: str` | `str` | `create_charge` |
| `_get_charge_model_inference_reason(model, charge_type, has_tiers, has_uom)` | ~1624 | Human-readable inference explanation | Various | `str` | `create_charge` |

#### Utility Tools

| Tool | Line | Purpose | Parameters | Returns | API Calls |
|------|------|---------|------------|---------|-----------|
| `get_current_date()` | ~224 | Get today's date in YYYY-MM-DD | None | `str` | None |
| `get_zuora_environment_info()` | ~231 | Get tenant settings summary | None | `str` | `check_connection()` |

#### Connection Tools

| Tool | Line | Purpose | Parameters | Returns | API Calls |
|------|------|---------|------------|---------|-----------|
| `connect_to_zuora()` | ~706 | Verify OAuth connection | None | `str` | `check_connection()` |

#### Query Tools

| Tool | Line | Purpose | Parameters | Returns | API Calls |
|------|------|---------|------------|---------|-----------|
| `list_zuora_products()` | ~718 | List last 20 products | None | `str` | `list_all_products()` |
| `get_zuora_product(identifier, identifier_type)` | ~841 | Get product by ID/name/SKU | `identifier: str`, `identifier_type: Literal["id","name","sku"]` | `str` | `get_product()`, `list_all_products()` |
| `get_zuora_rate_plan_details(product_id, rate_plan_name)` | ~924 | Get rate plan and charge details | `product_id: str`, `rate_plan_name: Optional[str]` | `str` | `get_product()` |

#### Payload Management Tools

| Tool | Line | Purpose | Parameters | Returns | State Access |
|------|------|---------|------------|---------|--------------|
| `get_payloads(api_type)` | ~262 | Retrieve stored payloads | `api_type: Optional[str]` | `str` | Read |
| `update_payload(api_type, field_path, new_value, payload_id, payload_name, payload_index)` | ~320 | Update field in existing payload | Various | `str` | Read/Write |
| `create_payload(api_type, payload_data, defaults_applied)` | ~553 | Create new payload with validation | `api_type: str`, `payload_data: dict`, `defaults_applied: List` | `str` | Read/Write |
| `list_payload_structure(api_type, payload_index)` | ~657 | Show payload field structure | `api_type: str`, `payload_index: int` | `str` | Read |

#### Creation Tools (ProductManager)

| Tool | Line | Purpose | Key Parameters | Returns | State Access |
|------|------|---------|----------------|---------|--------------|
| `create_product(name, sku, effective_start_date, description, effective_end_date)` | ~1101 | Generate product creation payload | `name: str`, `sku: Optional[str]` | `str` | Read/Write |
| `create_rate_plan(product_id, product_index, name, description, effective_start_date, effective_end_date)` | ~1216 | Generate rate plan creation payload | `product_id: Optional[str]`, `product_index: Optional[int]` | `str` | Read/Write |
| `create_charge(rate_plan_id, rate_plan_index, name, charge_type, charge_model, price, tiers, ...)` | ~1654 | Generate charge creation payload | Many (see source) | `str` | Read/Write |

#### Update Tools (ProductManager)

| Tool | Line | Purpose | Parameters | Returns | State Access |
|------|------|---------|------------|---------|--------------|
| `update_zuora_product(product_id, attribute, new_value)` | ~981 | Generate product update payload | `product_id: str`, `attribute: Literal[...]`, `new_value: str` | `str` | Read/Write |
| `update_zuora_rate_plan(rate_plan_id, attribute, new_value)` | ~1018 | Generate rate plan update payload | `rate_plan_id: str`, `attribute: Literal[...]`, `new_value: str` | `str` | Read/Write |
| `update_zuora_charge(charge_id, attribute, new_value)` | ~1055 | Generate charge update payload | `charge_id: str`, `attribute: str`, `new_value: Any` | `str` | Read/Write |

#### Advisory Tools (BillingArchitect)

| Tool | Line | Purpose | Key Parameters | Returns |
|------|------|---------|----------------|---------|
| `generate_prepaid_config(product_name, rate_plan_name, prepaid_uom, prepaid_amount, prepaid_quantity, ...)` | ~2137 | Generate Prepaid with Drawdown config | Many | `str` |
| `generate_workflow_config(workflow_name, trigger_type, description, schedule, event_type)` | ~2371 | Generate Zuora Workflow config | `workflow_name: str`, `trigger_type: Literal[...]` | `str` |
| `generate_notification_rule(rule_name, event_type, description, channel_type, endpoint_url)` | ~2578 | Generate notification rule config | `rule_name: str`, `event_type: str` | `str` |
| `generate_order_payload(action_type, subscription_number, add_rate_plan_id, ...)` | ~2737 | Generate Orders API payload | `action_type: Literal[...]` | `str` |
| `explain_field_lookup(object_type, field_name, use_case)` | ~3014 | Explain fieldLookup() function | `object_type: Literal[...]`, `field_name: str` | `str` |
| `generate_multi_attribute_pricing(charge_name, attributes, base_price)` | ~3232 | Generate MAP configuration | `charge_name: str`, `attributes: List` | `str` |
| `generate_custom_field_definition(field_name, field_label, field_type, object_type, ...)` | ~3449 | Generate custom field definition | `field_name: str`, `field_type: Literal[...]` | `str` |
| `validate_billing_configuration(config_type)` | ~3610 | Validate advisory payloads in session | `config_type: Literal[...]` | `str` |
| `get_zuora_documentation(topic)` | ~3760 | Get Zuora documentation links | `topic: Literal[...]` | `str` |

---

### 4.4 agents/zuora_client.py (API Client) - ~610 lines

OAuth 2.0 authenticated REST client for Zuora API operations.

#### Class: ZuoraClient

##### Initialization

| Method | Purpose | Parameters | Called From |
|--------|---------|------------|-------------|
| `__init__()` | Initialize client with OAuth credentials | None (uses config) | `get_zuora_client()` |
| `_create_session()` | Create HTTP session with connection pooling | None | `__init__()` |

##### Authentication Methods

| Method | Line | Purpose | Returns | Called From |
|--------|------|---------|---------|-------------|
| `authenticate()` | ~102 | Obtain OAuth 2.0 access token | `Dict[str, Any]` | `_ensure_authenticated()`, `check_connection()` |
| `_ensure_authenticated()` | ~193 | Ensure valid token before API calls | `bool` | `_request()` |

##### Core Request Method

| Method | Line | Purpose | Parameters | Returns | Called From |
|--------|------|---------|------------|---------|-------------|
| `_request(method, endpoint, data, params, use_cache)` | ~200 | Make authenticated requests | `method: str`, `endpoint: str`, `data: dict`, `params: dict`, `use_cache: bool` | `Dict[str, Any]` | All API methods |

##### Product Operations

| Method | Line | Endpoint | Purpose | Called From |
|--------|------|----------|---------|-------------|
| `query_products(filters)` | ~305 | `POST /v1/catalog/query/products` | Query with filters | Internal |
| `list_all_products(page_size)` | ~318 | `GET /v1/catalog/products` | List with pagination | `list_zuora_products` tool |
| `get_product(product_key)` | ~333 | `GET /v1/catalog/products/{key}` | Get by ID/key | `get_zuora_product` tool |
| `get_product_by_name(name)` | ~349 | `POST /v1/catalog/query/products` | Search by name | `get_zuora_product` tool |
| `update_product(product_id, data)` | ~368 | `PUT /v1/object/product/{id}` | Update attributes | Internal |

##### Rate Plan Operations

| Method | Line | Endpoint | Purpose | Called From |
|--------|------|----------|---------|-------------|
| `get_rate_plans(product_id)` | ~397 | (via `get_product`) | List rate plans | Internal |
| `get_rate_plan(rate_plan_id)` | ~414 | `GET /v1/catalog/product-rate-plans/{id}` | Get by ID | Internal |
| `update_rate_plan(rate_plan_id, data)` | ~430 | `PUT /v1/object/product-rate-plan/{id}` | Update attributes | Internal |

##### Charge Operations

| Method | Line | Endpoint | Purpose | Called From |
|--------|------|----------|---------|-------------|
| `get_charges(rate_plan_id)` | ~462 | (via `get_rate_plan`) | List charges | Internal |
| `get_charge(charge_id)` | ~482 | `GET /v1/catalog/product-rate-plan-charges/{id}` | Get by ID | Internal |
| `update_charge(charge_id, data)` | ~500 | `PUT /v1/object/product-rate-plan-charge/{id}` | Update attributes | Internal |

##### Utility Methods

| Method | Line | Purpose | Returns | Called From |
|--------|------|---------|---------|-------------|
| `check_connection()` | ~535 | Verify connection and authenticate | `Dict[str, Any]` | `connect_to_zuora` tool, `get_zuora_environment_info` tool |
| `get_settings_batch(requests)` | ~561 | Fetch multiple settings in batch | `Dict[str, Any]` | `fetch_environment_settings()` |

##### Singleton Factory

| Function | Purpose | Returns | Called From |
|----------|---------|---------|-------------|
| `get_zuora_client()` | Get or create global client instance | `ZuoraClient` | `tools.py`, `zuora_settings.py`, `benchmark.py` |

---

### 4.5 agents/models.py (Data Models) - ~520 lines

Pydantic models for API contracts and domain objects.

#### Core Product Catalog Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Tier` | Pricing tier for tiered/volume pricing | `Currency`, `Price`, `StartingUnit`, `EndingUnit`, `PriceFormat` |
| `Charge` | Product Rate Plan Charge | `name`, `type`, `model`, `billingPeriod`, `price`, `tiers`, `uom` |
| `RatePlan` | Product Rate Plan | `name`, `description`, `charges` |
| `Product` | Product entity | `name`, `sku`, `effectiveStartDate`, `ratePlans` |
| `ProductSpec` | Complete product specification | `product`, `comment` |

#### Zuora Enum Types

| Type Alias | Values |
|------------|--------|
| `ZUORA_CHARGE_MODELS` | Flat Fee Pricing, Per Unit Pricing, Volume Pricing, Tiered Pricing, Overage Pricing, etc. |
| `ZUORA_CHARGE_TYPES` | OneTime, Recurring, Usage |
| `ZUORA_BILLING_PERIODS` | Month, Quarter, Annual, Semi-Annual, Week, etc. |
| `ZUORA_BILL_CYCLE_TYPES` | DefaultFromCustomer, SpecificDayofMonth, SubscriptionStartDay, etc. |
| `ZUORA_TRIGGER_EVENTS` | ContractEffective, ServiceActivation, CustomerAcceptance |
| `ZUORA_BILLING_TIMING` | In Advance, In Arrears |
| `ZUORA_RATING_GROUP` | ByBillingPeriod, ByUsageStartDate, ByUsageRecord, etc. |

#### Chat API Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ZuoraApiType` | Enum of API operation types | PRODUCT, PRODUCT_CREATE, RATE_PLAN_CREATE, CHARGE_CREATE, etc. |
| `ZuoraApiPayload` | Payload container | `payload`, `zuora_api_type`, `payload_id` |
| `Citation` | Knowledge base citation | `id`, `title`, `uri`, `url` |
| `ChatRequest` | Incoming request | `persona`, `message`, `conversation_id`, `zuora_api_payloads` |
| `ChatResponse` | Outgoing response | `conversation_id`, `answer`, `citations`, `zuora_api_payloads` |

#### Persona Types

| Model | Values |
|-------|--------|
| `PersonaType` | PROJECT_MANAGER ("ProductManager"), BILLING_ARCHITECT ("BillingArchitect") |
| `BillingArchitectApiType` | WORKFLOW, NOTIFICATION_RULE, ORDER, ACCOUNT_CUSTOM_FIELD, etc. |

#### Workflow Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `WorkflowTrigger` | Workflow trigger config | `type`, `schedule`, `event_type` |
| `WorkflowCondition` | Workflow condition | `field`, `operator`, `value` |
| `WorkflowTask` | Workflow task | `name`, `type`, `api_endpoint`, `api_payload` |
| `WorkflowConfig` | Complete workflow | `name`, `trigger`, `tasks`, `active` |

#### Notification Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `NotificationEventType` | Event types enum | UsageRecordCreation, PaymentSuccess, InvoicePosted, etc. |
| `NotificationChannel` | Delivery channel | `type`, `endpoint`, `email_template_id` |
| `NotificationRule` | Notification rule | `name`, `event_type`, `channels`, `filter_conditions` |

#### Orders API Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `OrderActionType` | Order action types | AddProduct, RemoveProduct, UpdateProduct, Suspend, Resume |
| `OrderChargeOverride` | Charge override | `product_rate_plan_charge_id`, `price`, `quantity` |
| `OrderAction` | Order action | `type`, `add_product`, `remove_product`, `charge_overrides` |
| `OrderConfig` | Order configuration | `subscription_number`, `order_date`, `actions` |

#### Prepaid Balance Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `PrepaidDrawdownConfig` | Drawdown configuration | `charge_name`, `prepaid_uom`, `prepaid_quantity` |
| `TopUpConfig` | Auto top-up config | `enabled`, `threshold_type`, `threshold_value` |
| `PrepaidBalanceConfig` | Complete prepaid config | `product_name`, `drawdown_charge`, `top_up_config` |

#### Other Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CustomFieldDefinition` | Custom field definition | `name`, `label`, `type`, `object_type` |
| `PriceAttribute` | MAP pricing attribute | `name`, `values` |
| `MultiAttributePricingConfig` | MAP configuration | `charge_name`, `pricing_attributes`, `price_matrix` |
| `AdvisoryPayload` | Advisory payload container | `payload`, `api_type`, `api_endpoint`, `http_method` |

---

### 4.6 agents/config.py (Configuration)

Environment configuration loaded from `.env` files.

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `APP_NAME` | str | `"zuora-seed-agent"` | Application identifier |
| `GEN_MODEL_ID` | str | `"qwen.qwen3-next-80b-a3b"` | Bedrock LLM model ID |
| `ZUORA_CLIENT_ID` | str | *required* | Zuora OAuth client ID |
| `ZUORA_CLIENT_SECRET` | str | *required* | Zuora OAuth client secret |
| `ZUORA_ENV` | str | `"sandbox"` | Environment (sandbox/production) |
| `OTEL_SERVICE_NAME` | str | `"zuora-seed-agent"` | OpenTelemetry service name |
| `OTEL_ENABLED` | bool | `True` | Enable observability |
| `ZUORA_API_CACHE_ENABLED` | bool | `True` | Enable response caching |
| `ZUORA_API_CACHE_TTL_SECONDS` | int | `300` | Cache TTL (5 minutes) |
| `ZUORA_API_RETRY_ATTEMPTS` | int | `1` | Retry attempts |
| `ZUORA_API_RETRY_BACKOFF_FACTOR` | float | `0.5` | Backoff factor |
| `ZUORA_API_CONNECTION_POOL_SIZE` | int | `10` | Connection pool size |
| `ZUORA_API_REQUEST_TIMEOUT` | int | `15` | Request timeout (seconds) |
| `ZUORA_OAUTH_TIMEOUT` | int | `10` | OAuth timeout (seconds) |
| `MAX_CONVERSATION_TURNS` | int | `3` | Session rotation buckets |

---

### 4.7 agents/zuora_settings.py (Tenant Settings) - ~320 lines

Dynamic fetching and caching of Zuora tenant-specific settings.

#### Module State

| Variable | Type | Purpose |
|----------|------|---------|
| `_cached_settings` | `Optional[Dict[str, Any]]` | Session-level cache |
| `_fetch_attempted` | `bool` | Prevents repeated failed fetches |
| `_fetch_error` | `Optional[str]` | Stores last fetch error |

#### Functions

| Function | Purpose | Returns | Called From |
|----------|---------|---------|-------------|
| `fetch_environment_settings(force_refresh)` | Fetch and cache Zuora settings | `Dict[str, Any]` | `_initialize_zuora_settings()` |
| `get_available_charge_models()` | Get enabled charge models | `List[str]` | `validation_schemas.py` |
| `get_available_billing_periods()` | Get enabled billing periods | `List[str]` | `validation_schemas.py` |
| `get_available_billing_cycle_types()` | Get enabled billing cycle types | `List[str]` | `validation_schemas.py` |
| `get_available_currencies()` | Get active currencies | `List[str]` | `validation_schemas.py` |
| `get_default_currency()` | Get default currency | `str` | `tools.py` |
| `get_available_uoms()` | Get full UOM objects | `List[Dict[str, Any]]` | Internal |
| `get_available_uom_names()` | Get active UOM names | `List[str]` | `tools.py` |
| `get_billing_rules()` | Get billing rules config | `Dict[str, Any]` | Internal |
| `get_subscription_settings()` | Get subscription settings | `Dict[str, Any]` | Internal |
| `get_raw_settings()` | Get all raw settings | `Dict[str, Any]` | Internal |
| `is_settings_loaded()` | Check if settings loaded | `bool` | `create_agent()` |
| `get_fetch_error()` | Get fetch error message | `Optional[str]` | Internal |
| `get_environment_summary()` | Get formatted summary | `str` | `get_zuora_environment_info` tool |
| `get_environment_context_for_prompt()` | Get concise context | `str` | `create_agent()` |
| `clear_cache()` | Clear cached settings | None | Internal |

#### Settings Fetched from Zuora

| Endpoint | Purpose |
|----------|---------|
| `/billing-rules` | Billing rules configuration |
| `/accounting-rules` | Accounting rules |
| `/currencies` | Active currencies |
| `/charge-models` | Enabled charge models |
| `/billing-cycle-types` | Billing cycle types |
| `/billing-periods` | Billing periods |
| `/units-of-measure` | Units of measure |
| `/subscription-settings` | Subscription settings |
| ... | (16 total settings) |

---

### 4.8 agents/validation_schemas.py (Validation) - ~590 lines

Defines validation schemas and placeholder generation for Zuora API payloads.

#### Constants

| Constant | Purpose |
|----------|---------|
| `FRIENDLY_LABELS` | Maps technical Zuora values to readable text |
| `COMMON_DEFAULTS` | Default values for common fields |
| `REQUIRED_FIELDS` | Schema dictionary per entity type |

#### Functions

| Function | Purpose | Returns | Called From |
|----------|---------|---------|-------------|
| `get_friendly_label(value)` | Convert technical value to readable | `str` | Internal |
| `get_friendly_options(options, max_show)` | Convert options to friendly text | `str` | `_get_placeholder_question()` |
| `_get_nested_value(data, path)` | Get nested dict value | `Any` | `_check_field_exists()` |
| `_check_field_exists(data, field)` | Check field exists (case-insensitive) | `bool` | `validate_payload()` |
| `validate_payload(api_type, payload_data)` | Validate against required fields | `Tuple[bool, List]` | `create_payload` tool |
| `format_validation_questions(api_type, missing_fields)` | Format as HTML questions | `str` | `create_payload` tool |
| `generate_placeholder_value(field_name, description)` | Generate `<<PLACEHOLDER:...>>` | `str` | `generate_placeholder_payload()` |
| `generate_placeholder_payload(api_type, payload_data, missing_fields)` | Insert placeholders for missing | `Tuple[Dict, List]` | `create_payload` tool |
| `_get_env_options(option_type)` | Get environment-specific options | `List[str]` | `_get_placeholder_question()` |
| `_get_placeholder_question(field_name, api_type)` | Generate question and examples | `Tuple[str, List]` | `format_placeholder_warning()` |
| `format_placeholder_warning(api_type, placeholder_list, payload, ...)` | Format HTML warning | `str` | `tools.py` |

---

### 4.9 agents/validation_utils.py (Validation Utilities) - ~320 lines

Reusable validation functions for dates, IDs, SKUs, and uniqueness.

#### Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `MAX_NAME_LENGTH` | `60` | Maximum allowed name length |

#### Functions

| Function | Purpose | Returns | Called From |
|----------|---------|---------|-------------|
| `validate_date_format(date_str, field_name)` | Validate YYYY-MM-DD format | `Tuple[bool, Optional[str]]` | `create_product`, `create_rate_plan` |
| `validate_date_range(start_date, end_date)` | Validate end > start | `Tuple[bool, Optional[str]]` | `create_product`, `create_rate_plan` |
| `validate_zuora_id(id_str, id_type)` | Validate ID or object reference | `Tuple[bool, Optional[str]]` | `create_rate_plan`, `create_charge` |
| `is_object_reference(id_str)` | Check if `@{Object.Id}` format | `bool` | `validate_zuora_id()` |
| `validate_sku_format(sku)` | Validate SKU characters | `Tuple[bool, Optional[str]]` | `create_product` |
| `format_error_message(title, detail)` | Format validation error | `str` | Various tools |
| `validate_name_length(name, field_type)` | Validate name length | `Tuple[bool, Optional[str]]` | `create_product`, `create_rate_plan`, `create_charge` |
| `validate_product_name_unique(name, existing_payloads)` | Check product name uniqueness | `Tuple[bool, Optional[str]]` | `create_product` |
| `validate_rate_plan_name_unique(name, product_id, existing_payloads)` | Check rate plan uniqueness | `Tuple[bool, Optional[str]]` | `create_rate_plan` |
| `validate_charge_name_unique(name, rate_plan_id, existing_payloads)` | Check charge uniqueness | `Tuple[bool, Optional[str]]` | `create_charge` |

---

### 4.10 agents/html_formatter.py (Response Formatting) - ~560 lines

Converts markdown to HTML for agent responses.

#### Functions

| Function | Purpose | Returns | Called From |
|----------|---------|---------|-------------|
| `html_escape(text)` | Escape HTML special characters | `str` | Various |
| `_extract_code_blocks(text)` | Extract code blocks to placeholders | `Tuple[str, List]` | `markdown_to_html()` |
| `_restore_code_blocks(text, code_blocks)` | Restore with `<pre><code>` | `str` | `markdown_to_html()` |
| `_extract_inline_code(text)` | Extract inline backticks | `Tuple[str, List]` | `markdown_to_html()` |
| `_restore_inline_code(text, inline_codes)` | Restore with `<code>` | `str` | `markdown_to_html()` |
| `_convert_headers(text)` | Convert `#` to `<h1>`-`<h6>` | `str` | `markdown_to_html()` |
| `_convert_bold(text)` | Convert `**bold**` to `<strong>` | `str` | `markdown_to_html()` |
| `_convert_italic(text)` | Convert `*italic*` to `<em>` | `str` | `markdown_to_html()` |
| `_convert_horizontal_rule(text)` | Convert `---` to `<hr>` | `str` | `markdown_to_html()` |
| `_convert_unordered_lists(text)` | Convert `-`/`*` to `<ul><li>` | `str` | `markdown_to_html()` |
| `_convert_ordered_lists(text)` | Convert `1.` to `<ol><li>` | `str` | `markdown_to_html()` |
| `_convert_tables(text)` | Convert markdown tables to `<table>` | `str` | `markdown_to_html()` |
| `_convert_checkboxes(text)` | Convert `- [x]` to checkboxes | `str` | `markdown_to_html()` |
| `_wrap_paragraphs(text)` | Wrap text in `<p>` tags | `str` | `markdown_to_html()` |
| `markdown_to_html(text)` | **Main function**: Full conversion | `str` | `agentcore_app.invoke()` |
| `generate_reference_documentation(payload_structure)` | Generate `@{Reference}` docs | `str` | `tools.py` |
| `format_payload_with_references(objects)` | Format payloads with refs | `str` | Internal |
| `highlight_placeholders_in_json(json_str)` | Highlight `<<PLACEHOLDER>>` | `str` | `tools.py` |
| `format_defaults_applied_html(defaults)` | Generate defaults table | `str` | `tools.py` |
| `generate_placeholder_warning_html(payloads_with_placeholders)` | Generate warning table | `str` | `agentcore_app.invoke()` |

---

### 4.11 agents/cache.py (Caching) - ~260 lines

TTL-based in-memory caching for Zuora API responses.

#### Classes

##### CacheEntry (dataclass)

| Field | Type | Purpose |
|-------|------|---------|
| `value` | `Any` | Cached value |
| `expires_at` | `float` | Expiration timestamp |
| `created_at` | `float` | Creation timestamp |

| Method | Purpose |
|--------|---------|
| `is_expired()` | Check if entry expired |

##### TTLCache

| Method | Purpose | Returns | Called From |
|--------|---------|---------|-------------|
| `__init__(default_ttl_seconds)` | Initialize with TTL | None | `get_cache()` |
| `_make_key(method, endpoint, params, data)` | Generate cache key | `str` | `get()`, `set()` |
| `get(method, endpoint, params, data)` | Retrieve cached value | `Optional[Any]` | `ZuoraClient._request()` |
| `set(method, endpoint, value, params, data, ttl)` | Store value | None | `ZuoraClient._request()` |
| `invalidate(method, endpoint)` | Invalidate entries | `int` | Internal |
| `clear()` | Clear all entries | None | Tests |
| `stats()` | Get cache statistics | `Dict[str, Any]` | Debugging |
| `cleanup_expired()` | Remove expired entries | `int` | Internal |

#### Factory Function

| Function | Purpose | Returns | Called From |
|----------|---------|---------|-------------|
| `get_cache()` | Get or create global cache | `TTLCache` | `ZuoraClient.__init__()`, `benchmark.py` |

---

### 4.12 agents/observability.py (Tracing & Metrics) - ~320 lines

OpenTelemetry integration for distributed tracing and metrics.

#### Global Variables

| Variable | Type | Purpose |
|----------|------|---------|
| `_tracer` | `Optional[trace.Tracer]` | Singleton tracer |
| `_meter` | `Optional[metrics.Meter]` | Singleton meter |
| `_metrics_collector` | `Optional[MetricsCollector]` | Singleton collector |
| `_initialized` | `bool` | Initialization flag |

#### Functions

| Function | Purpose | Returns | Called From |
|----------|---------|---------|-------------|
| `initialize_observability()` | Initialize OTel infrastructure | None | `agentcore_app.invoke()` |
| `_parse_otlp_headers(env_var_name)` | Parse OTLP headers | `Dict[str, str]` | `initialize_observability()` |
| `get_tracer()` | Get global tracer | `trace.Tracer` | Various |
| `get_meter()` | Get global meter | `metrics.Meter` | `MetricsCollector` |
| `get_metrics_collector()` | Get global collector | `MetricsCollector` | Various |
| `trace_function(span_name, attributes)` | **Decorator** for function tracing | `Callable` | Various functions |

#### Class: MetricsCollector

| Method | Purpose | Attributes Recorded |
|--------|---------|---------------------|
| `record_request(persona, duration_ms, success)` | Record HTTP request | persona, success |
| `record_agent_invocation(persona, duration_ms, success)` | Record agent invocation | persona, success |
| `record_tool_execution(tool_name, category, duration_ms, success)` | Record tool execution | tool_name, category, success |
| `record_api_call(method, endpoint, duration_ms, success)` | Record Zuora API call | method, endpoint, success |
| `record_api_error(method, endpoint, error_type)` | Record API error | method, endpoint, error_type |
| `record_cache_hit(operation)` | Record cache hit | operation |
| `record_cache_miss(operation)` | Record cache miss | operation |

#### Metrics Defined

| Metric Name | Type | Unit | Description |
|-------------|------|------|-------------|
| `requests_total` | Counter | 1 | Total requests processed |
| `request_duration_ms` | Histogram | ms | Request duration |
| `errors_total` | Counter | 1 | Total errors |
| `agent_invocations_total` | Counter | 1 | Agent invocations |
| `agent_invocation_duration_ms` | Histogram | ms | Agent invocation duration |
| `tool_executions_total` | Counter | 1 | Tool executions |
| `tool_execution_duration_ms` | Histogram | ms | Tool execution duration |
| `api_calls_total` | Counter | 1 | Zuora API calls |
| `api_call_duration_ms` | Histogram | ms | API call duration |
| `api_errors_total` | Counter | 1 | API errors |
| `cache_hits_total` | Counter | 1 | Cache hits |
| `cache_misses_total` | Counter | 1 | Cache misses |

---

## 5. Tool Reference

### 5.1 Tool Categories Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              TOOL CATEGORIES                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────────────┐   │
│  │   SHARED TOOLS    │  │  PM TOOLS (CRUD)  │  │   BA TOOLS (Advisory)     │   │
│  │   (Both Personas) │  │  (ProductManager) │  │  (BillingArchitect)       │   │
│  ├───────────────────┤  ├───────────────────┤  ├───────────────────────────┤   │
│  │ get_current_date  │  │ create_product    │  │ generate_prepaid_config   │   │
│  │ get_zuora_env_info│  │ create_rate_plan  │  │ generate_workflow_config  │   │
│  │ connect_to_zuora  │  │ create_charge     │  │ generate_notification_rule│   │
│  │ list_zuora_product│  │ update_zuora_*    │  │ generate_order_payload    │   │
│  │ get_zuora_product │  │ update_payload    │  │ explain_field_lookup      │   │
│  │ get_rate_plan_deta│  │ create_payload    │  │ generate_multi_attr_price │   │
│  │ get_payloads      │  │                   │  │ generate_custom_field_def │   │
│  │ list_payload_struc│  │                   │  │ validate_billing_config   │   │
│  │                   │  │                   │  │ get_zuora_documentation   │   │
│  └───────────────────┘  └───────────────────┘  └───────────────────────────┘   │
│         8 tools               8 tools                    9 tools                │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Shared Tools (Read-Only)

Available to both ProductManager and BillingArchitect personas.

| Tool | Purpose | API Dependency |
|------|---------|----------------|
| `get_current_date()` | Get today's date in YYYY-MM-DD format | None |
| `get_zuora_environment_info()` | Get tenant settings (charge models, currencies, UOMs) | OAuth |
| `connect_to_zuora()` | Verify OAuth connection | OAuth |
| `list_zuora_products()` | List last 20 products sorted by update time | Catalog API |
| `get_zuora_product(identifier, identifier_type)` | Get product by ID, name, or SKU with fuzzy matching | Catalog API |
| `get_zuora_rate_plan_details(product_id, rate_plan_name)` | Get rate plan and charge details | Catalog API |
| `get_payloads(api_type)` | Retrieve payloads from agent state | State |
| `list_payload_structure(api_type, payload_index)` | Show payload field structure | State |

### 5.3 ProductManager Tools (CRUD)

Execute Zuora API operations (create/update products, rate plans, charges).

| Tool | Purpose | Generates |
|------|---------|-----------|
| `create_product(name, sku, ...)` | Generate product creation payload | `product_create` payload |
| `create_rate_plan(product_id, name, ...)` | Generate rate plan creation payload | `rate_plan_create` payload |
| `create_charge(rate_plan_id, name, charge_type, ...)` | Generate charge creation payload | `charge_create` payload |
| `update_zuora_product(product_id, attribute, new_value)` | Generate product update payload | `product_update` payload |
| `update_zuora_rate_plan(rate_plan_id, attribute, new_value)` | Generate rate plan update payload | `rate_plan_update` payload |
| `update_zuora_charge(charge_id, attribute, new_value)` | Generate charge update payload | `charge_update` payload |
| `update_payload(api_type, field_path, new_value, ...)` | Update field in existing payload | Modified payload |
| `create_payload(api_type, payload_data, defaults_applied)` | Create new payload with validation | New payload |

### 5.4 BillingArchitect Tools (Advisory)

Advisory-only mode for complex configurations.

| Tool | Purpose | Output |
|------|---------|--------|
| `generate_prepaid_config(...)` | Generate Prepaid with Drawdown configuration guide | Implementation guide |
| `generate_workflow_config(...)` | Generate Zuora Workflow configuration | Workflow payload |
| `generate_notification_rule(...)` | Generate notification rule configuration | Notification payload |
| `generate_order_payload(...)` | Generate Orders API payload | Orders API payload |
| `explain_field_lookup(...)` | Explain fieldLookup() for dynamic pricing | Documentation |
| `generate_multi_attribute_pricing(...)` | Generate MAP configuration guide | MAP configuration |
| `generate_custom_field_definition(...)` | Generate custom field definition | Field definition |
| `validate_billing_configuration(...)` | Validate advisory payloads in session | Validation results |
| `get_zuora_documentation(topic)` | Get Zuora documentation links | Doc links |

---

## 6. Module Dependencies

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           MODULE DEPENDENCY GRAPH                                │
└─────────────────────────────────────────────────────────────────────────────────┘

agentcore_app.py
├── bedrock_agentcore.BedrockAgentCoreApp
├── agents.zuora_agent
│   └── create_agent
├── agents.models
│   ├── ChatRequest
│   ├── ChatResponse
│   └── ZuoraApiPayload
├── agents.html_formatter
│   ├── markdown_to_html
│   └── generate_placeholder_warning_html
└── agents.observability
    ├── initialize_observability
    ├── get_tracer
    ├── get_metrics_collector
    └── trace_function

agents/zuora_agent.py
├── strands
│   ├── Agent
│   └── models.BedrockModel
├── agents.config
│   └── GEN_MODEL_ID
├── agents.observability
│   ├── trace_function
│   └── get_tracer
├── agents.zuora_settings
│   ├── fetch_environment_settings
│   ├── is_settings_loaded
│   └── get_environment_context_for_prompt
└── agents.tools
    └── (all tool functions)

agents/tools.py
├── strands.tool
├── agents.models
│   └── ProductSpec
├── agents.zuora_client
│   └── get_zuora_client
├── agents.observability
│   └── trace_function
├── agents.validation_schemas
│   ├── validate_payload
│   ├── format_validation_questions
│   ├── generate_placeholder_payload
│   └── format_placeholder_warning
├── agents.validation_utils
│   ├── validate_date_format
│   ├── validate_date_range
│   ├── validate_zuora_id
│   ├── validate_sku_format
│   ├── validate_name_length
│   ├── validate_product_name_unique
│   ├── validate_rate_plan_name_unique
│   └── validate_charge_name_unique
├── agents.zuora_settings
│   ├── get_available_uom_names
│   └── get_default_currency
└── agents.html_formatter
    ├── generate_reference_documentation
    └── format_defaults_applied_html

agents/zuora_client.py
├── requests
├── agents.config
│   ├── ZUORA_CLIENT_ID
│   ├── ZUORA_CLIENT_SECRET
│   ├── ZUORA_ENV
│   ├── ZUORA_API_CACHE_ENABLED
│   ├── ZUORA_API_CACHE_TTL_SECONDS
│   ├── ZUORA_API_RETRY_ATTEMPTS
│   ├── ZUORA_API_REQUEST_TIMEOUT
│   └── ZUORA_OAUTH_TIMEOUT
├── agents.cache
│   └── get_cache
└── agents.observability
    ├── get_tracer
    ├── get_metrics_collector
    └── trace_function

agents/zuora_settings.py
└── agents.zuora_client
    └── get_zuora_client

agents/validation_schemas.py
└── agents.zuora_settings (lazy import)
    ├── get_available_charge_models
    ├── get_available_billing_periods
    ├── get_available_currencies
    └── get_available_uoms

agents/html_formatter.py
└── (stdlib only: re, typing)

agents/cache.py
└── (stdlib only: time, hashlib, json, threading, typing, dataclasses)

agents/observability.py
├── opentelemetry.trace
├── opentelemetry.metrics
├── opentelemetry.sdk.*
└── agents.config
    ├── OTEL_ENABLED
    └── OTEL_SERVICE_NAME
```

---

## 7. Observability Architecture

### 7.1 Trace Hierarchy

```
agentcore.invoke
│
├── request.parse
│   └── Pydantic validation
│
├── agent.get_or_create
│   └── agent.create
│       ├── agent.create.settings
│       │   └── zuora.settings.fetch
│       │       └── zuora.api.request (batch settings)
│       ├── agent.create.model
│       │   └── BedrockModel initialization
│       └── agent.create.configure
│           └── Tool registration
│
├── state.initialize
│   └── Payload initialization from request
│
├── prompt.build
│   └── Context-aware prompt construction
│
├── agent.invoke
│   └── LLM invocation
│       └── (tool executions)
│           │
│           ├── zuora.connection.check
│           │   └── zuora.api.request
│           │       └── POST /oauth/token
│           │
│           ├── zuora.products.list
│           │   └── zuora.api.request
│           │       └── GET /v1/catalog/products
│           │
│           ├── zuora.products.get
│           │   └── zuora.api.request
│           │       └── GET /v1/catalog/products/{id}
│           │
│           └── (payload operations)
│               └── State updates
│
└── response.build
    ├── markdown_to_html
    └── Citation generation
```

### 7.2 Metrics Collected

| Category | Metric | Type | Labels |
|----------|--------|------|--------|
| **Requests** | `requests_total` | Counter | persona, success |
| | `request_duration_ms` | Histogram | persona |
| | `errors_total` | Counter | persona, error_type |
| **Agent** | `agent_invocations_total` | Counter | persona, success |
| | `agent_invocation_duration_ms` | Histogram | persona |
| **Tools** | `tool_executions_total` | Counter | tool_name, category, success |
| | `tool_execution_duration_ms` | Histogram | tool_name, category |
| **API** | `api_calls_total` | Counter | method, endpoint, success |
| | `api_call_duration_ms` | Histogram | method, endpoint |
| | `api_errors_total` | Counter | method, endpoint, error_type |
| **Cache** | `cache_hits_total` | Counter | operation |
| | `cache_misses_total` | Counter | operation |

---

## 8. Configuration Reference

### 8.1 Environment Variables

#### Application Settings

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `APP_NAME` | str | `"zuora-seed-agent"` | Application identifier |
| `GEN_MODEL_ID` | str | `"qwen.qwen3-next-80b-a3b"` | AWS Bedrock LLM model ID |
| `MAX_CONVERSATION_TURNS` | int | `3` | Session rotation bucket count |

#### Zuora Credentials

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ZUORA_CLIENT_ID` | str | *required* | OAuth client ID |
| `ZUORA_CLIENT_SECRET` | str | *required* | OAuth client secret |
| `ZUORA_ENV` | str | `"sandbox"` | Environment (sandbox, production, eu, etc.) |

#### Performance Settings

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ZUORA_API_CACHE_ENABLED` | bool | `True` | Enable response caching |
| `ZUORA_API_CACHE_TTL_SECONDS` | int | `300` | Cache TTL (5 minutes) |
| `ZUORA_API_RETRY_ATTEMPTS` | int | `1` | Retry attempts on failure |
| `ZUORA_API_RETRY_BACKOFF_FACTOR` | float | `0.5` | Exponential backoff factor |
| `ZUORA_API_CONNECTION_POOL_SIZE` | int | `10` | HTTP connection pool size |
| `ZUORA_API_REQUEST_TIMEOUT` | int | `15` | Request timeout (seconds) |
| `ZUORA_OAUTH_TIMEOUT` | int | `10` | OAuth timeout (seconds) |

#### Observability Settings

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OTEL_ENABLED` | bool | `True` | Enable OpenTelemetry |
| `OTEL_SERVICE_NAME` | str | `"zuora-seed-agent"` | Service name in traces |
| `DEPLOYMENT_ENV` | str | `"development"` | Deployment environment tag |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | str | `""` | OTLP collector endpoint |
| `OTEL_EXPORTER_OTLP_TRACES_HEADERS` | str | `""` | Headers for trace export |
| `OTEL_EXPORTER_OTLP_METRICS_HEADERS` | str | `""` | Headers for metrics export |
| `OTEL_METRIC_EXPORT_INTERVAL` | str | `"60000"` | Metric export interval (ms) |
| `OTEL_RESOURCE_ATTRIBUTES` | str | `""` | Additional resource attributes |

---

## 9. Design Patterns

### 9.1 Placeholder System

The agent generates payloads **immediately** even with incomplete information.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           PLACEHOLDER FLOW                                       │
└─────────────────────────────────────────────────────────────────────────────────┘

User: "Create a product called Analytics Pro"
                │
                ▼
┌─────────────────────────────────────────┐
│ create_product(name="Analytics Pro")    │
│                                         │
│ 1. Apply smart defaults:                │
│    - EffectiveStartDate = today         │
│    - EffectiveEndDate = today + 10 years│
│                                         │
│ 2. Validate payload                     │
│    - Missing: SKU                       │
│                                         │
│ 3. Generate placeholder:                │
│    - sku = "<<PLACEHOLDER:sku>>"        │
│                                         │
│ 4. Store in state with _placeholders    │
└─────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│ {                                       │
│   "payload": {                          │
│     "Name": "Analytics Pro",            │
│     "SKU": "<<PLACEHOLDER:sku>>",       │
│     "EffectiveStartDate": "2024-12-06", │
│     "EffectiveEndDate": "2034-12-06"    │
│   },                                    │
│   "zuora_api_type": "product_create",   │
│   "_placeholders": ["sku"]              │
│ }                                       │
└─────────────────────────────────────────┘
                │
                ▼
User: "Set the SKU to ANALYTICS-PRO-001"
                │
                ▼
┌─────────────────────────────────────────┐
│ update_payload(                         │
│   api_type="product_create",            │
│   field_path="SKU",                     │
│   new_value="ANALYTICS-PRO-001"         │
│ )                                       │
│                                         │
│ 1. Find payload by type                 │
│ 2. Update field (case-insensitive)      │
│ 3. Remove from _placeholders list       │
└─────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│ {                                       │
│   "payload": {                          │
│     "Name": "Analytics Pro",            │
│     "SKU": "ANALYTICS-PRO-001",         │
│     "EffectiveStartDate": "2024-12-06", │
│     "EffectiveEndDate": "2034-12-06"    │
│   },                                    │
│   "zuora_api_type": "product_create",   │
│   "_placeholders": []  ← Now empty!     │
│ }                                       │
└─────────────────────────────────────────┘
```

### 9.2 Object References

Batch creation uses `@{Object[index].Id}` syntax for entity relationships.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         OBJECT REFERENCE SYSTEM                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

Batch Create Example:
┌─────────────────────────────────────────┐
│ Product[0]:                             │
│   Name: "Analytics Pro"                 │
│   Id: (auto-generated at execution)     │
└─────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│ RatePlan[0]:                            │
│   Name: "Standard Plan"                 │
│   ProductId: "@{Product[0].Id}" ◄───────┼── Reference to Product[0]
└─────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│ Charge[0]:                              │
│   Name: "Monthly Fee"                   │
│   ProductRatePlanId:                    │
│     "@{ProductRatePlan[0].Id}" ◄────────┼── Reference to RatePlan[0]
└─────────────────────────────────────────┘

At execution time, Zuora resolves references:
  @{Product[0].Id}         → "8a8080..."
  @{ProductRatePlan[0].Id} → "8a8081..."
```

### 9.3 Smart Defaults

Tools apply intelligent defaults to minimize required user input.

| Field | Default Logic |
|-------|---------------|
| `EffectiveStartDate` | Today's date |
| `EffectiveEndDate` | Start date + 10 years |
| `BillingTiming` | "In Arrears" for Usage, "In Advance" otherwise |
| `BillCycleType` | "DefaultFromCustomer" |
| `TriggerEvent` | "ContractEffective" |
| `Currency` | Tenant default (usually "USD") |
| `RatingGroup` | "ByBillingPeriod" for tiered/volume usage |

### 9.4 Session Rotation

Limits conversation history for performance optimization.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          SESSION ROTATION                                        │
└─────────────────────────────────────────────────────────────────────────────────┘

MAX_CONVERSATION_TURNS = 3

conversation_id = "user-123-conv-456"
                │
                ▼
┌─────────────────────────────────────────┐
│ get_bounded_session_id(conv_id, 3)      │
│                                         │
│ 1. Hash conversation_id                 │
│ 2. hash % 3 = bucket (0, 1, or 2)       │
│ 3. Return: "{conv_id}_bucket_{bucket}"  │
└─────────────────────────────────────────┘
                │
                ▼
Turn 1: session = "user-123-conv-456_bucket_0"
Turn 2: session = "user-123-conv-456_bucket_1"
Turn 3: session = "user-123-conv-456_bucket_2"
Turn 4: session = "user-123-conv-456_bucket_0" ← Cycles back!

Benefits:
• 70-90% token reduction for long conversations
• 5-10x faster response times
• State (payloads) persists independently
```

### 9.5 Conservative Charge Model Inference

Charge model inferred only when context is unambiguous.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    CHARGE MODEL INFERENCE RULES                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────┐     ┌─────────────────────────────────┐
│ Input Context                   │     │ Inferred Model                  │
├─────────────────────────────────┤     ├─────────────────────────────────┤
│ tiers provided (2+ tiers)       │ ──▶ │ Tiered Pricing                  │
│ charge_type=Usage + UOM         │ ──▶ │ Per Unit Pricing                │
│ price only (no tiers, no UOM)   │ ──▶ │ Flat Fee Pricing                │
│ included_units + overage_price  │ ──▶ │ Overage Pricing                 │
│ Ambiguous or mixed signals      │ ──▶ │ <<PLACEHOLDER:ChargeModel>>     │
└─────────────────────────────────┘     └─────────────────────────────────┘

Principle: When in doubt, use a placeholder rather than guess wrong.
```

---

## 10. Testing

### 10.1 test_agent.py

Interactive test harness with categorized test scenarios.

```bash
# Run interactive menu
python test_agent.py

# Run single test by key
python test_agent.py ba1    # Billing Architect test 1
python test_agent.py pm1    # Product Manager test 1
python test_agent.py z1     # Zuora API test 1
```

#### Test Categories

| Category | Key Prefix | Description |
|----------|------------|-------------|
| Product Manager | `pm*` | Product/rate plan/charge creation |
| Zuora API | `z*` | API connection and queries |
| Billing Architect | `ba*` | Advisory configuration generation |

### 10.2 test_placeholders.py

Tests for the placeholder system.

```bash
python test_placeholders.py
```

Tests include:
- Placeholder generation for missing fields
- Placeholder removal on update
- Validation with placeholders
- Smart default application

### 10.3 benchmark.py

Performance benchmarking for cache and API operations.

```bash
python benchmark.py
```

Measures:
- Cold vs warm cache performance
- API response times
- Token usage per conversation turn

---

## Appendix: API Contract

### Request (ChatRequest)

```json
{
  "persona": "ProductManager",
  "message": "Create a product called Analytics Pro with SKU ANALYTICS-001",
  "conversation_id": "optional-session-id",
  "zuora_api_payloads": [
    {
      "payload": {"Name": "Existing Product"},
      "zuora_api_type": "product_create",
      "payload_id": "abc123"
    }
  ]
}
```

### Response (ChatResponse)

```json
{
  "conversation_id": "generated-or-provided-id",
  "answer": "<p>I've created a product payload for Analytics Pro...</p>",
  "citations": [
    {
      "id": "cite-1",
      "title": "Zuora Product Catalog Guide",
      "url": "https://knowledgecenter.zuora.com/..."
    }
  ],
  "zuora_api_payloads": [
    {
      "payload": {
        "Name": "Analytics Pro",
        "SKU": "ANALYTICS-001",
        "EffectiveStartDate": "2024-12-06",
        "EffectiveEndDate": "2034-12-06"
      },
      "zuora_api_type": "product_create",
      "payload_id": "def456"
    }
  ]
}
```

---

*Generated: December 2024*
*Version: 2.0*
