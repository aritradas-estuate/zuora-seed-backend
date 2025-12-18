import json
from typing import List
from agents.zuora_agent import get_default_agent
from agentcore_app import invoke


def print_response(response: dict):
    """Pretty print response with answer and payload count."""
    print(f"\nAnswer:\n{response.get('answer', 'No answer')}")
    payloads = response.get("zuora_api_payloads", [])
    if payloads:
        print(f"\nPayloads ({len(payloads)}):")
        print(json.dumps(payloads, indent=2))
    print("-" * 60)


def assert_response_valid(response: dict) -> bool:
    """Assert that response is valid (not None/empty and has an answer)."""
    assert response is not None, "Response should not be None"
    assert isinstance(response, dict), "Response should be a dict"
    answer = response.get("answer", "")
    assert answer, "Response should have a non-empty answer"
    return True


def assert_contains_keywords(
    response: dict, keywords: List[str], case_sensitive: bool = False
) -> bool:
    """Assert that response contains all specified keywords."""
    answer = response.get("answer", "")
    check_answer = answer if case_sensitive else answer.lower()
    missing = []
    for keyword in keywords:
        check_keyword = keyword if case_sensitive else keyword.lower()
        if check_keyword not in check_answer:
            missing.append(keyword)
    if missing:
        print(f"  [WARN] Missing keywords: {missing}")
        return False
    return True


def assert_not_contains_keywords(
    response: dict, keywords: List[str], case_sensitive: bool = False
) -> bool:
    """Assert that response does NOT contain any of the specified keywords."""
    answer = response.get("answer", "")
    check_answer = answer if case_sensitive else answer.lower()
    found = []
    for keyword in keywords:
        check_keyword = keyword if case_sensitive else keyword.lower()
        if check_keyword in check_answer:
            found.append(keyword)
    if found:
        print(f"  [WARN] Unexpected keywords found: {found}")
        return False
    return True


def print_assertion_result(passed: bool, test_name: str):
    """Print assertion result."""
    status = "PASS" if passed else "FAIL"
    print(f"\n[{status}] {test_name}")


# =============================================================================
# PRODUCT MANAGER TEST SCENARIOS
# =============================================================================


def test_pm_bundle_starter_suite():
    """PM Test: Bundle product combining multiple products."""
    print("\n" + "=" * 60)
    print("PM TEST: Bundle - Starter Suite")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": 'Create a bundle called "Starter Suite" that combines Core CRM and Analytics Pro together at $199 per month.',
        "conversation_id": "pm-bundle-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_pm_tiered_data_transfer():
    """PM Test: Tiered (Graduated) Usage pricing."""
    print("\n" + "=" * 60)
    print("PM TEST: Tiered Usage - Data Transfer")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": 'Create a "Data Transfer" plan with tiered pricing per GB: 0-10 TB @ $0.09/GB, 10-50 TB @ $0.07/GB, 50 TB+ @ $0.05/GB.',
        "conversation_id": "pm-tiered-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_pm_volume_seat_licensing():
    """PM Test: Volume Pricing based on total quantity."""
    print("\n" + "=" * 60)
    print("PM TEST: Volume Pricing - Seat Licensing")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": 'Create "Seat Licensing" with volume pricing per seat: 1-10 @ $20, 11-50 @ $18, 51+ @ $15 per month.',
        "conversation_id": "pm-volume-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_pm_usage_sms_pack():
    """PM Test: Per-Unit + Included Units + Overage."""
    print("\n" + "=" * 60)
    print("PM TEST: Usage with Overage - SMS Pack")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": 'Create "SMS Pack": $49/month base includes 1,000 SMS, overage $0.015/SMS after that.',
        "conversation_id": "pm-sms-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_pm_multicurrency_premium_support():
    """PM Test: Flat Recurring + One-Time Setup with Multi-Currency."""
    print("\n" + "=" * 60)
    print("PM TEST: Multi-Currency - Premium Support")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": 'Create "Premium Support" with $299/month and a one-time setup fee of $999. Add USD & EUR (EUR price €279, setup €949).',
        "conversation_id": "pm-multicurrency-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_pm_ramp_growth_bundle():
    """PM Test: Ramp Pricing with scheduled price changes."""
    print("\n" + "=" * 60)
    print("PM TEST: Ramp Pricing - Growth Bundle")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": 'Create "Growth Bundle (Ramp)": Months 1-3 @ $100/mo, Months 4-6 @ $150/mo, Months 7-12 @ $200/mo; then auto-renew at $200/mo.',
        "conversation_id": "pm-ramp-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_pm_prepaid_api_credits():
    """PM Test: Prepaid with Drawdown (Wallet)."""
    print("\n" + "=" * 60)
    print("PM TEST: Prepaid Drawdown - API Credits Wallet")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": 'Create "API Credits Wallet" with monthly prepayment $500 that loads 100,000 API_CALL credits into a wallet. Allow auto top-up and overage when credits run out. Support USD & EUR.',
        "conversation_id": "pm-prepaid-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


# =============================================================================
# PM WORKFLOW TESTS (PM-1 through PM-7)
# =============================================================================


def test_pm_1_connect_gate():
    """PM-1: Connection gate check."""
    print("\n" + "=" * 60)
    print("PM-1: Connect Gate")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": "Connect me to our Zuora sandbox for write operations and confirm OAuth is active. If not connected, block create/update actions and prompt me to authenticate.",
        "conversation_id": "pm-1-connect",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_pm_2_guided_creation():
    """PM-2: Guided creation with validation."""
    print("\n" + "=" * 60)
    print("PM-2: Guided Creation - Pro Starter")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": """Let's create a new product and catalog structure.

Product: Pro Starter
SKU: PRO-STARTER-001
Currencies: USD, EUR

Rate plan 1: Base
- Charge: Recurring, Monthly, $49, billed in advance

Rate plan 2: API Usage
- Charge: Usage, Per-unit, UOM = api_call
- Included units: 10,000 per month
- Overage: enabled at $0.003 per call after included units

Build the SeedSpec, show the human summary, then the Raw JSON, and run full validation. If valid, generate planning payloads and I'll press Create Product.""",
        "conversation_id": "pm-2-guided",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_pm_3_oneshot_clarifications():
    """PM-3: One-shot with smart clarifications."""
    print("\n" + "=" * 60)
    print("PM-3: One-Shot with Clarifications")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": """Add a product "Pro Starter EU" with a monthly base fee and a usage add-on for API calls. Price the base at 49 and usage at 0.003 after 10k included.

Assume nothing else. Ask me to confirm:
- Currency (default USD? I also want EUR)
- Billing timing (advance vs arrears)
- Exact UOM name (api_call vs api_calls)
- Whether overage is same rate or different
Then finalize SeedSpec → validate → plan (no execution until I confirm).""",
        "conversation_id": "pm-3-oneshot",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_pm_4_tenant_checks():
    """PM-4: Tenant checks with auto-fix proposals."""
    print("\n" + "=" * 60)
    print("PM-4: Tenant Checks + Auto-Fix")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": 'Create product "Pro Global" with currencies USD and GBP, and a usage UOM named api_calls (plural). If GBP or api_calls aren\'t enabled in this tenant, propose safe auto-fixes (enable GBP, normalize UOM to api_call), show what will change, and re-validate before planning.',
        "conversation_id": "pm-4-tenant",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_pm_5_business_rules_edge():
    """PM-5: Business rules edge cases."""
    print("\n" + "=" * 60)
    print("PM-5: Business Rules Edge Cases")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": """Create "Pro Hybrid" with:
- Base recurring $49 (no billing period specified on purpose)
- Usage tiered pricing: 1-10k at $0.004, 10,001-50k at $0.0035, then $0.003 beyond
Let the validator catch the missing billing period and any tier gaps. Suggest minimal fixes only and show exactly what you changed before continuing.""",
        "conversation_id": "pm-5-business",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_pm_6_duplicate_names():
    """PM-6: Duplicate names and length limits."""
    print("\n" + "=" * 60)
    print("PM-6: Duplicate Names + Length Limits")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": 'Create "Pro Suite Enterprise Limited Introductory Edition 2026 - Super Long Name" with two rate plans both named "Base". Enforce unique names and length limits; propose truncated names and "Base (1)/(2)". Show the diff, then proceed if I approve.',
        "conversation_id": "pm-6-duplicates",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_pm_7_execute():
    """PM-7: Execute and return links."""
    print("\n" + "=" * 60)
    print("PM-7: Execute Creation")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": "Everything looks good—execute: create the product, both rate plans, and charges. Return success with links to the created Product and Rate Plans in the tenant.",
        "conversation_id": "pm-7-execute",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


# =============================================================================
# LEGACY TESTS
# =============================================================================


def test_agent_direct():
    """Test the agent directly (legacy mode)."""
    agent = get_default_agent()

    print("\n--- Test 1: Capability Check ---")
    try:
        response = agent("Hi, what can you do?", stream=False)
        print(f"Agent Response: {response}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n--- Test 2: Create Product Preview ---")
    prompt = """
    Create a product called "Enterprise Cloud" with SKU "ENT-CLOUD-001".
    It should have a monthly recurring charge of $1000 called "Base License".
    Run a preview validation first.
    """
    try:
        response = agent(prompt, stream=False)
        print(f"Agent Response: {response}")
    except Exception as e:
        print(f"Error: {e}")


def test_chat_api_basic():
    """Basic Chat API tests."""
    print("\n--- Chat API Test 1: Simple message (no payloads) ---")
    request_1 = {
        "persona": "ProductManager",
        "message": "What can you help me with?",
        "conversation_id": "test-conv-001",
    }
    try:
        response = invoke(request_1)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")

    print("\n--- Chat API Test 2: With product payload ---")
    request_2 = {
        "persona": "ProductManager",
        "message": "Please update the product name to 'Gold Tier Premium'",
        "conversation_id": "test-conv-002",
        "zuora_api_payloads": [
            {
                "payload": {
                    "name": "Gold Tier",
                    "sku": "GOLD-001",
                    "description": "Our gold tier product",
                    "effectiveStartDate": "2024-01-01",
                },
                "zuora_api_type": "product",
            }
        ],
    }
    try:
        response = invoke(request_2)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


# =============================================================================
# ZUORA API VIEW/UPDATE TESTS
# =============================================================================


def test_zuora_connect():
    """Test: Connect to Zuora sandbox."""
    print("\n" + "=" * 60)
    print("ZUORA API: Connect to Sandbox")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": "Connect me to our Zuora sandbox for write operations and confirm OAuth is active.",
        "conversation_id": "zuora-connect-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_zuora_view_all_products():
    """Test: View all products in catalog."""
    print("\n" + "=" * 60)
    print("ZUORA API: View All Products")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": "Show me all products in the catalog.",
        "conversation_id": "zuora-view-all-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_zuora_view_specific_product():
    """Test: View a specific product by name."""
    print("\n" + "=" * 60)
    print("ZUORA API: View Specific Product")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": "I want to view details of a specific product. The product name is 'Solar Plan Premium'.",
        "conversation_id": "zuora-view-specific-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_zuora_view_rate_plans():
    """Test: View rate plans for a product."""
    print("\n" + "=" * 60)
    print("ZUORA API: View Rate Plans")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": "Show me the rate plans and charges for 'Solar Plan Premium'.",
        "conversation_id": "zuora-view-rp-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_zuora_update_product_name():
    """Test: Update product name workflow."""
    print("\n" + "=" * 60)
    print("ZUORA API: Update Product Name")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": "I want to update the product 'Solar Plan Basic'. Change the name to 'Solar Plan Premium'.",
        "conversation_id": "zuora-update-name-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_zuora_update_product_date():
    """Test: Update product end date."""
    print("\n" + "=" * 60)
    print("ZUORA API: Update Product End Date")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": "Update the end date of 'Solar Plan Basic' to 2027-12-31.",
        "conversation_id": "zuora-update-date-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_zuora_update_charge_price():
    """Test: Update charge price."""
    print("\n" + "=" * 60)
    print("ZUORA API: Update Charge Price")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": "I need to update the 'Base Charge' price from $1,200 to $1,350 per year.",
        "conversation_id": "zuora-update-price-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_zuora_update_charge_model_restricted():
    """Test: Attempt to update charge model (should be restricted)."""
    print("\n" + "=" * 60)
    print("ZUORA API: Update Charge Model (Restricted)")
    print("=" * 60)

    request = {
        "persona": "ProductManager",
        "message": "I want to change the charge model from Flat Fee Pricing to Tiered Pricing.",
        "conversation_id": "zuora-update-model-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


# =============================================================================
# BILLING ARCHITECT TEST SCENARIOS
# =============================================================================


def test_ba_prepaid_drawdown_setup():
    """BA Test: Configure Prepaid with Drawdown for API credits."""
    print("\n" + "=" * 60)
    print("BA TEST: Prepaid with Drawdown Setup")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """Help me configure a Prepaid with Drawdown setup for API credits:
        - Product: API Platform
        - Rate Plan: Enterprise Credits
        - Prepaid: $500/month loads 100,000 API_CALL credits
        - Auto top-up when balance falls below 20%
        - Customer-specific top-up amounts using fieldLookup
        - Account custom field: TopUpAmount__c

        Generate all the configuration payloads and step-by-step instructions.""",
        "conversation_id": "ba-prepaid-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_ba_auto_topup_workflow():
    """BA Test: Configure auto top-up workflow."""
    print("\n" + "=" * 60)
    print("BA TEST: Auto Top-Up Workflow")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """Create a workflow configuration for auto top-up:
        - Trigger: When prepaid balance falls below 20%
        - Action: Create order to add more prepaid credits
        - Use the customer's TopUpAmount__c field for the amount
        - Send notification when top-up is triggered

        Provide the complete workflow configuration and notification rule.""",
        "conversation_id": "ba-topup-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_ba_usage_notification():
    """BA Test: Configure usage event notification."""
    print("\n" + "=" * 60)
    print("BA TEST: Usage Record Notification")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """Set up a notification rule for usage record creation:
        - Event: Usage Record Creation
        - Channel: Webhook to https://api.example.com/zuora-webhook
        - Include: Account ID, Usage amount, UOM, timestamp

        Generate the notification configuration and webhook payload format.""",
        "conversation_id": "ba-notification-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_ba_scheduled_transition():
    """BA Test: Scheduled product transition (Pay-as-you-go to Prepaid)."""
    print("\n" + "=" * 60)
    print("BA TEST: Scheduled Product Transition")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """Design a scheduled transition for deposit customers:

        Scenario:
        - Customer currently on "Pay-as-you-go" rate plan
        - Deposit amount stored in Account.DepositAmount__c
        - On May 1st, automatically:
          1. Remove Pay-as-you-go rate plan
          2. Add Prepaid Drawdown rate plan
          3. Use deposit amount for initial prepaid balance

        Generate:
        1. Account custom field definition for deposit
        2. Scheduled workflow for May 1st
        3. Orders API payload for the transition
        4. Step-by-step implementation guide""",
        "conversation_id": "ba-transition-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_ba_multi_attribute_pricing():
    """BA Test: Multi-attribute pricing with fieldLookup."""
    print("\n" + "=" * 60)
    print("BA TEST: Multi-Attribute Pricing")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """Configure Multi-Attribute Pricing for compute credits:
        - Base price: $0.10 per unit
        - Attributes:
          * Region: US, EU, APAC
          * Tier: Standard, Premium, Enterprise
        - US is base price, EU +10%, APAC +20%
        - Premium +15%, Enterprise +30%

        Should we use:
        A) Native MAP in Zuora
        B) fieldLookup() with custom fields

        Recommend the best approach and generate configuration.""",
        "conversation_id": "ba-map-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_ba_field_lookup_explanation():
    """BA Test: Explain fieldLookup for dynamic pricing."""
    print("\n" + "=" * 60)
    print("BA TEST: fieldLookup() Explanation")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """The top-up amount differs for each customer. How can Zuora automatically use a customer-specific top-up value?

        I need to understand how to use fieldLookup() for this scenario.""",
        "conversation_id": "ba-fieldlookup-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_ba_complete_prepaid_customer():
    """BA Test: Complete prepaid customer setup (Use Case 1)."""
    print("\n" + "=" * 60)
    print("BA TEST: Complete Prepaid Customer Setup")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """Design complete billing architecture for prepaid customers:

        Requirements:
        1. Prepaid with Drawdown charge model for SMS credits
        2. Custom top-up amounts per customer (use fieldLookup)
        3. Minimum balance threshold triggers top-up
        4. Notification when usage records are created
        5. Workflow for automated top-up when balance is low

        Provide:
        - All required configurations (charges, custom fields, notifications, workflows)
        - Complete JSON payloads for each component
        - Implementation sequence with dependencies
        - Validation checklist""",
        "conversation_id": "ba-complete-prepaid-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_ba_deposit_customer_workflow():
    """BA Test: Deposit customer with scheduled transition (Use Case 2)."""
    print("\n" + "=" * 60)
    print("BA TEST: Deposit Customer Workflow")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """Design billing architecture for deposit customers:

        Requirements:
        1. Store deposit amount in Account custom field
        2. Customer starts on Pay-as-you-go rate plan
        3. Scheduled workflow executes on May 1st
        4. Transition: Remove Pay-as-you-go, Add Prepaid Drawdown
        5. Use deposit amount as initial prepaid balance via Orders API

        Provide:
        - Account custom field definition
        - Workflow configuration for May 1st execution
        - Orders API payload for rate plan transition
        - Complete implementation guide""",
        "conversation_id": "ba-deposit-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_ba_order_transition_payload():
    """BA Test: Generate Orders API payload for product transition."""
    print("\n" + "=" * 60)
    print("BA TEST: Orders API Transition Payload")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """Generate an Orders API payload to transition a customer:
        - Remove rate plan ID: rp-paygo-12345
        - Add rate plan ID: rp-prepaid-67890
        - Effective date: 2024-05-01
        - Use fieldLookup for deposit amount from Account.DepositAmount__c

        Include complete payload with charge overrides.""",
        "conversation_id": "ba-order-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_ba_documentation_lookup():
    """BA Test: Get Zuora documentation reference."""
    print("\n" + "=" * 60)
    print("BA TEST: Documentation Lookup")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": "I need documentation and API references for Prepaid with Drawdown. What are the key concepts and endpoints?",
        "conversation_id": "ba-docs-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


# =============================================================================
# ARCHITECT DEMO SCENARIOS (Arch-0 through Arch-7)
# =============================================================================


def test_arch_0_solution_selection():
    """Arch-0: Solution selection flow (PM-1 style for Architect)."""
    print("\n" + "=" * 60)
    print("ARCH-0: Solution Selection Flow")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """Set up a customer where they pay upfront for a pool of value 
        that can be used over time. As the customer uses the service, the cost is 
        automatically deducted from this prepaid amount. Each bill should clearly 
        show how much was used, how much was deducted, and how much prepaid value 
        remains. If the prepaid amount is fully used, the customer can either add 
        more funds or be billed for additional usage, based on the agreed terms.""",
        "conversation_id": "arch-0-solution-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_arch_1_pwd_spec_draft():
    """Arch-1: One-shot PWD spec with validation and placeholders."""
    print("\n" + "=" * 60)
    print("ARCH-1: PWD SeedSpec Draft (One-Shot)")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """Create a SeedSpec draft (no execution) for a prepaid drawdown wallet:

Product: API Credits Wallet (SKU API-WALLET-100)
Plans:
1) Wallet Monthly
   - Recurring prepayment $500 USD / €460 EUR monthly
   - Loads 100,000 API_CALL credits each month
   - Trigger: Service Activation; Co-term to account anniversary
   - Wallet policies: Account-level pooling (POOL-DEFAULT), rollover 20% capped at 50,000, 
     rollover expires after 1 month, auto top-up when balance < 10,000 credits → add 100,000 and bill $500/€460
2) Top-Up Pack
   - One-time 200,000 credits at $900 / €820

Overage: If auto top-up is OFF and wallet hits 0, charge $0.007 / €0.0065 per API_CALL (monthly).

Validate with PWD rules. Show summary + raw JSON at the end. If valid, generate planned Zuora payloads with placeholders only (no apply).""",
        "conversation_id": "arch-1-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_arch_2_tenant_autofix():
    """Arch-2: Tenant checks and auto-fix proposals."""
    print("\n" + "=" * 60)
    print("ARCH-2: Tenant Checks + Auto-Fix")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """Use the same wallet model but intentionally set UOM = API_CALLS (plural) 
        and currencies = USD, GBP. Detect tenant issues and propose auto-fixes 
        (normalize UOM to api_call; enable GBP or swap to EUR). 
        Show the exact changes before re-validating.""",
        "conversation_id": "arch-2-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_arch_3_invalid_thresholds():
    """Arch-3: Invalid threshold detection and fix."""
    print("\n" + "=" * 60)
    print("ARCH-3: Invalid Thresholds")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """Create "API Credits Wallet (Test Thresholds)" with monthly prepay 
        that loads 50,000 credits, but set auto-top-up threshold to 75,000. 
        The validator should fail and recommend a threshold below the monthly load. 
        Re-run validation after fixing and display the resolution.""",
        "conversation_id": "arch-3-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_arch_4_rollover_defaults():
    """Arch-4: Auto-default rollover cap."""
    print("\n" + "=" * 60)
    print("ARCH-4: Rollover Defaults")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """Create a wallet where rollover_pct = 25 but no rollover_cap provided. 
        Auto-default the cap to monthly_load × rollover_pct and explain the assumption. 
        Re-validate and show the final policy in the summary.""",
        "conversation_id": "arch-4-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_arch_5_planning_export():
    """Arch-5: Planning payloads with placeholder map."""
    print("\n" + "=" * 60)
    print("ARCH-5: Planning Payloads + Export")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """For the validated PWD spec, generate only the planning payloads 
        (Product, Rate Plans, Charges, Orders examples) with placeholder IDs. 
        Show the placeholder map ({{PRODUCT_ID}}, {{RP_WALLET_MONTHLY_ID}}, etc.) 
        and show the plan as JSON at the end. Do not execute.""",
        "conversation_id": "arch-5-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_arch_6_kb_summary():
    """Arch-6: KB summary with links and checklist."""
    print("\n" + "=" * 60)
    print("ARCH-6: Knowledge Base Summary")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """Summarize Zuora's recommended approach for Prepaid with Drawdown:
        - how the wallet is represented,
        - why drawdown rating price is 0,
        - how rollover, top-ups, and overage are modeled,
        - why charge model changes are blocked after go-live.
        Include 2–3 relevant KC links and a 6-bullet implementation checklist.""",
        "conversation_id": "arch-6-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


def test_arch_7_pm_handoff():
    """Arch-7: Generate PM handoff prompt after selecting PPDD option."""
    print("\n" + "=" * 60)
    print("ARCH-7: PM Handoff Prompt Generation")
    print("=" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """I want to use PPDD (Option 1). Here are my requirements:
        - Product name: API Credits Wallet
        - SKU: API-CREDITS-10K
        - Prepaid quantity: 10,000 credits
        - Currencies: USD and EUR
        - Prices: $99 USD, €90 EUR per month
        - UOM: credit
        - Include overage at $0.01 USD / €0.009 EUR per credit
        - No rollover, no top-up pack
        
        Generate the ProductManager prompt I can copy and paste.""",
        "conversation_id": "arch-7-pm-handoff-001",
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


# =============================================================================
# BILLING ARCHITECT 4-STAGE FLOW TESTS
# =============================================================================


def test_ba_flow_stage1_initial_request():
    """BA Flow Stage 1: Initial prepaid request - should show options only."""
    print("\n" + "=" * 60)
    print("BA FLOW STAGE 1: Initial Request (Options Only)")
    print("=" * 60)
    print("Expected: Show Option 1 (PPDD) and Option 2 (Standard)")
    print("Expected: Ask 'Which option?' - NOT ask for product details")
    print("-" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """Set up a customer where they pay upfront for a pool of value 
        that can be used over time. As the customer uses the service, the cost is 
        automatically deducted from this prepaid amount. Each bill should clearly 
        show how much was used, how much was deducted, and how much prepaid value 
        remains. If the prepaid amount is fully used, the customer can either add 
        more funds or be billed for additional usage, based on the agreed terms.""",
        "conversation_id": "ba-flow-stage1-001",
    }
    try:
        response = invoke(request)
        print_response(response)

        # Assertions
        passed = True
        passed &= assert_response_valid(response)
        passed &= assert_contains_keywords(
            response, ["option 1", "option 2", "which option"]
        )
        # Should NOT have "selected" or ask for product details in Stage 1
        passed &= assert_not_contains_keywords(
            response, ["you've selected", "product name", "sku"]
        )
        print_assertion_result(passed, "Stage 1: Options Only")
    except Exception as e:
        print(f"Error: {e}")
        print_assertion_result(False, "Stage 1: Options Only")


def test_ba_flow_stage2_option_selection():
    """BA Flow Stage 2: User selects Option 1 - should acknowledge and offer prompt."""
    print("\n" + "=" * 60)
    print("BA FLOW STAGE 2: Option Selection")
    print("=" * 60)
    print("Expected: Acknowledge 'Option 1: PPDD'")
    print("Expected: Offer to create PM prompt - NOT ask for product details yet")
    print("-" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": "Option 1",
        "conversation_id": "ba-flow-stage2-001",
    }
    try:
        response = invoke(request)
        print_response(response)

        # Assertions
        passed = True
        passed &= assert_response_valid(response)
        # Should acknowledge option selection or offer prompt
        passed &= assert_contains_keywords(response, ["option 1"])
        # Should NOT ask for product details yet
        passed &= assert_not_contains_keywords(response, ["sku", "prepaid quantity"])
        print_assertion_result(passed, "Stage 2: Option Selection")
    except Exception as e:
        print(f"Error: {e}")
        print_assertion_result(False, "Stage 2: Option Selection")


def test_ba_flow_stage2_option2_selection():
    """BA Flow Stage 2: User selects Option 2 - should acknowledge Standard."""
    print("\n" + "=" * 60)
    print("BA FLOW STAGE 2: Option 2 Selection")
    print("=" * 60)
    print("Expected: Acknowledge 'Option 2: Standard Workaround'")
    print("Expected: Offer to create PM prompt - NOT ask for product details yet")
    print("-" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": "Option 2",
        "conversation_id": "ba-flow-stage2-opt2-001",
    }
    try:
        response = invoke(request)
        print_response(response)

        # Assertions
        passed = True
        passed &= assert_response_valid(response)
        # Should acknowledge option 2 selection
        passed &= assert_contains_keywords(response, ["option 2"])
        # Should NOT ask for product details yet
        passed &= assert_not_contains_keywords(response, ["sku", "prepaid quantity"])
        print_assertion_result(passed, "Stage 2: Option 2 Selection")
    except Exception as e:
        print(f"Error: {e}")
        print_assertion_result(False, "Stage 2: Option 2 Selection")


def test_ba_flow_stage3_prompt_request():
    """BA Flow Stage 3: User asks for prompt - should ask for ALL requirements."""
    print("\n" + "=" * 60)
    print("BA FLOW STAGE 3: Prompt Request (Gather Requirements)")
    print("=" * 60)
    print("Expected: Ask for ALL 10 requirements in ONE message")
    print("Expected: Product name, SKU, quantity, currencies, prices, UOM, etc.")
    print("-" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": "Create a prompt for me Option 1",
        "conversation_id": "ba-flow-stage3-001",
    }
    try:
        response = invoke(request)
        print_response(response)

        # Assertions
        passed = True
        passed &= assert_response_valid(response)
        # Should ask for all requirements
        passed &= assert_contains_keywords(
            response, ["product name", "sku", "currencies", "prices"]
        )
        print_assertion_result(passed, "Stage 3: Prompt Request")
    except Exception as e:
        print(f"Error: {e}")
        print_assertion_result(False, "Stage 3: Prompt Request")


def test_ba_flow_stage3_opt2_prompt_request():
    """BA Flow Stage 3: User asks for Option 2 prompt."""
    print("\n" + "=" * 60)
    print("BA FLOW STAGE 3: Option 2 Prompt Request")
    print("=" * 60)
    print("Expected: Ask for ALL requirements for Standard approach")
    print("-" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": "Create a prompt for me Option 2",
        "conversation_id": "ba-flow-stage3-opt2-001",
    }
    try:
        response = invoke(request)
        print_response(response)

        # Assertions
        passed = True
        passed &= assert_response_valid(response)
        # Should ask for requirements
        passed &= assert_contains_keywords(
            response, ["product name", "sku", "currencies"]
        )
        print_assertion_result(passed, "Stage 3: Option 2 Prompt Request")
    except Exception as e:
        print(f"Error: {e}")
        print_assertion_result(False, "Stage 3: Option 2 Prompt Request")


def test_ba_flow_stage4_generate_ppdd_prompt():
    """BA Flow Stage 4: User provides values - should generate detailed PPDD prompt."""
    print("\n" + "=" * 60)
    print("BA FLOW STAGE 4: Generate PPDD Prompt")
    print("=" * 60)
    print("Expected: Complete ProductManager prompt in code block")
    print("Expected: Detailed narrative format matching example")
    print("-" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """I've chosen Option 1 (PPDD) and want you to generate the ProductManager prompt. Here are my requirements:
        - Product name: Credit Top-Up Monthly
        - SKU: CREDIT-10K-MONTHLY
        - Prepaid quantity: 10,000 credits
        - Currencies: USD
        - Prices: $99 USD per month
        - UOM: credit
        - Overage: Yes, $1.00 per credit
        - Rollover: No
        - Top-up packs: No
        - Auto-top-up: No
        
        Please generate the ProductManager prompt now.""",
        "conversation_id": "ba-flow-stage4-001",
    }
    try:
        response = invoke(request)
        print_response(response)

        # Assertions
        passed = True
        passed &= assert_response_valid(response)
        # Should contain the product info from user's request
        passed &= assert_contains_keywords(
            response, ["credit top-up", "CREDIT-10K-MONTHLY", "prepaid"]
        )
        # Should have code block with prompt (markdown code fence or HTML pre/code)
        answer = response.get("answer", "")
        has_code_block = (
            "```" in answer or "<pre><code>" in answer or "<code>" in answer
        )
        if not has_code_block:
            print("  [WARN] Expected code block (``` or <pre><code>) in response")
            passed = False
        print_assertion_result(passed, "Stage 4: Generate PPDD Prompt")
    except Exception as e:
        print(f"Error: {e}")
        print_assertion_result(False, "Stage 4: Generate PPDD Prompt")


def test_ba_flow_stage4_generate_standard_prompt():
    """BA Flow Stage 4: Generate Standard workaround prompt with disadvantages."""
    print("\n" + "=" * 60)
    print("BA FLOW STAGE 4: Generate Standard Prompt (with disadvantages)")
    print("=" * 60)
    print("Expected: Complete PM prompt for Standard approach")
    print("Expected: Disadvantages table")
    print("Expected: 'Why PPDD is Preferred' section")
    print("-" * 60)

    request = {
        "persona": "BillingArchitect",
        "message": """I want the Standard approach (Option 2). Here are my details:
        - Product name: Prepaid Credits Standard
        - SKU: PREPAID-STD-001
        - Prepaid quantity: 5,000 credits
        - Currencies: USD, EUR
        - Prices: $50 USD, €45 EUR per month
        - UOM: credit
        - Overage: Yes, $0.02 per credit
        - Rollover: No""",
        "conversation_id": "ba-flow-stage4-standard-001",
    }
    try:
        response = invoke(request)
        print_response(response)

        # Assertions
        passed = True
        passed &= assert_response_valid(response)
        # Should contain the product info
        passed &= assert_contains_keywords(
            response, ["prepaid credits standard", "PREPAID-STD-001"]
        )
        # Should mention disadvantages for standard approach
        passed &= assert_contains_keywords(response, ["disadvantage"])
        print_assertion_result(passed, "Stage 4: Generate Standard Prompt")
    except Exception as e:
        print(f"Error: {e}")
        print_assertion_result(False, "Stage 4: Generate Standard Prompt")


def test_ba_flow_full_conversation_ppdd():
    """BA Flow: Full 4-stage conversation for PPDD (simulated)."""
    print("\n" + "=" * 60)
    print("BA FLOW: Full PPDD Conversation (All 4 Stages)")
    print("=" * 60)
    print("This test simulates the complete user journey:")
    print("  Stage 1: Initial request → Options")
    print("  Stage 2: 'Option 1' → Acknowledge + offer prompt")
    print("  Stage 3: 'Create a prompt for me Option 1' → Gather requirements")
    print("  Stage 4: Provide values → Generate prompt")
    print("-" * 60)

    # Note: In a real test, we'd need conversation history support
    # This test just verifies Stage 4 with full context
    request = {
        "persona": "BillingArchitect",
        "message": """I've selected Option 1 (PPDD) and want to create the ProductManager prompt.

        Here are all my requirements:
        - Product name: API Credits Wallet
        - SKU: API-CREDITS-10K
        - Prepaid quantity: 10,000 credits
        - Currencies: USD and EUR
        - Prices: $99 USD, €90 EUR per month
        - UOM: credit
        - Overage billing: Yes at $0.01 USD / €0.009 EUR per credit
        - Rollover: Yes, for 1 period
        - Top-up packs: Yes, 5,000 credits for $50 USD / €45 EUR
        - Auto-top-up: Yes, trigger at 1,000 credits threshold""",
        "conversation_id": "ba-flow-full-ppdd-001",
    }
    try:
        response = invoke(request)
        print_response(response)

        # Assertions
        passed = True
        passed &= assert_response_valid(response)
        # Should contain all the key product details
        passed &= assert_contains_keywords(
            response, ["api credits wallet", "API-CREDITS-10K", "rollover", "top-up"]
        )
        print_assertion_result(passed, "Full PPDD Conversation")
    except Exception as e:
        print(f"Error: {e}")
        print_assertion_result(False, "Full PPDD Conversation")


def test_ba_flow_alternate_triggers():
    """BA Flow: Test alternate trigger phrases for Stage 2 and Stage 3."""
    print("\n" + "=" * 60)
    print("BA FLOW: Alternate Trigger Phrases")
    print("=" * 60)
    print("Testing various ways users might select options:")
    print("  - 'go with option 1'")
    print("  - 'I choose PPDD'")
    print("  - 'generate the prompt'")
    print("-" * 60)

    # Test "go with option 1"
    request = {
        "persona": "BillingArchitect",
        "message": "go with option 1",
        "conversation_id": "ba-flow-alt-001",
    }
    try:
        response = invoke(request)
        print("\n--- Response to 'go with option 1' ---")
        print_response(response)

        # Assertions
        passed = True
        passed &= assert_response_valid(response)
        # Should recognize the option selection
        passed &= assert_contains_keywords(response, ["option 1"])
        print_assertion_result(passed, "Alternate Triggers")
    except Exception as e:
        print(f"Error: {e}")
        print_assertion_result(False, "Alternate Triggers")


# =============================================================================
# TEST MENU
# =============================================================================

BA_FLOW_TESTS = {
    "bf1": ("Stage 1: Initial Request", test_ba_flow_stage1_initial_request),
    "bf2": ("Stage 2: Option 1 Selection", test_ba_flow_stage2_option_selection),
    "bf2b": ("Stage 2: Option 2 Selection", test_ba_flow_stage2_option2_selection),
    "bf3": ("Stage 3: Prompt Request", test_ba_flow_stage3_prompt_request),
    "bf3b": ("Stage 3: Opt 2 Prompt Request", test_ba_flow_stage3_opt2_prompt_request),
    "bf4": ("Stage 4: Generate PPDD Prompt", test_ba_flow_stage4_generate_ppdd_prompt),
    "bf4b": (
        "Stage 4: Generate Standard Prompt",
        test_ba_flow_stage4_generate_standard_prompt,
    ),
    "bf5": ("Full PPDD Conversation", test_ba_flow_full_conversation_ppdd),
    "bf6": ("Alternate Triggers", test_ba_flow_alternate_triggers),
}

ARCH_TESTS = {
    "arch0": ("Solution Selection Flow", test_arch_0_solution_selection),
    "arch1": ("Arch-1: PWD Spec Draft", test_arch_1_pwd_spec_draft),
    "arch2": ("Arch-2: Tenant Auto-Fix", test_arch_2_tenant_autofix),
    "arch3": ("Arch-3: Invalid Thresholds", test_arch_3_invalid_thresholds),
    "arch4": ("Arch-4: Rollover Defaults", test_arch_4_rollover_defaults),
    "arch5": ("Arch-5: Planning Export", test_arch_5_planning_export),
    "arch6": ("Arch-6: KB Summary", test_arch_6_kb_summary),
    "arch7": ("Arch-7: PM Handoff Prompt", test_arch_7_pm_handoff),
}

BA_TESTS = {
    "ba1": ("Prepaid Drawdown Setup", test_ba_prepaid_drawdown_setup),
    "ba2": ("Auto Top-Up Workflow", test_ba_auto_topup_workflow),
    "ba3": ("Usage Notification", test_ba_usage_notification),
    "ba4": ("Scheduled Transition", test_ba_scheduled_transition),
    "ba5": ("Multi-Attribute Pricing", test_ba_multi_attribute_pricing),
    "ba6": ("fieldLookup() Explanation", test_ba_field_lookup_explanation),
    "ba7": ("Complete Prepaid Customer", test_ba_complete_prepaid_customer),
    "ba8": ("Deposit Customer Workflow", test_ba_deposit_customer_workflow),
    "ba9": ("Orders API Transition", test_ba_order_transition_payload),
    "ba10": ("Documentation Lookup", test_ba_documentation_lookup),
}

PM_TESTS = {
    "1": ("Bundle - Starter Suite", test_pm_bundle_starter_suite),
    "2": ("Tiered Usage - Data Transfer", test_pm_tiered_data_transfer),
    "3": ("Volume Pricing - Seat Licensing", test_pm_volume_seat_licensing),
    "4": ("Usage + Overage - SMS Pack", test_pm_usage_sms_pack),
    "5": ("Multi-Currency - Premium Support", test_pm_multicurrency_premium_support),
    "6": ("Ramp Pricing - Growth Bundle", test_pm_ramp_growth_bundle),
    "7": ("Prepaid Drawdown - API Credits", test_pm_prepaid_api_credits),
    "8": ("PM-1: Connect Gate", test_pm_1_connect_gate),
    "9": ("PM-2: Guided Creation", test_pm_2_guided_creation),
    "10": ("PM-3: One-Shot Clarifications", test_pm_3_oneshot_clarifications),
    "11": ("PM-4: Tenant Checks", test_pm_4_tenant_checks),
    "12": ("PM-5: Business Rules Edge", test_pm_5_business_rules_edge),
    "13": ("PM-6: Duplicate Names", test_pm_6_duplicate_names),
    "14": ("PM-7: Execute", test_pm_7_execute),
    "15": ("Legacy: Direct Agent", test_agent_direct),
    "16": ("Legacy: Basic Chat API", test_chat_api_basic),
}

ZUORA_API_TESTS = {
    "z1": ("Connect to Zuora", test_zuora_connect),
    "z2": ("View All Products", test_zuora_view_all_products),
    "z3": ("View Specific Product", test_zuora_view_specific_product),
    "z4": ("View Rate Plans", test_zuora_view_rate_plans),
    "z5": ("Update Product Name", test_zuora_update_product_name),
    "z6": ("Update Product Date", test_zuora_update_product_date),
    "z7": ("Update Charge Price", test_zuora_update_charge_price),
    "z8": (
        "Update Charge Model (Restricted)",
        test_zuora_update_charge_model_restricted,
    ),
}


ALL_TESTS = {**PM_TESTS, **ZUORA_API_TESTS, **BA_TESTS, **ARCH_TESTS, **BA_FLOW_TESTS}


def show_menu():
    """Display test menu."""
    print("\n" + "=" * 60)
    print("ZUORA SEED - TEST MENU")
    print("=" * 60)
    print("\nPricing Model Tests:")
    for key in ["1", "2", "3", "4", "5", "6", "7"]:
        print(f"  {key}. {PM_TESTS[key][0]}")
    print("\nWorkflow Tests (PM-1 to PM-7):")
    for key in ["8", "9", "10", "11", "12", "13", "14"]:
        print(f"  {key}. {PM_TESTS[key][0]}")
    print("\nLegacy Tests:")
    for key in ["15", "16"]:
        print(f"  {key}. {PM_TESTS[key][0]}")
    print("\n--- ZUORA API TESTS (Real API) ---")
    for key in ["z1", "z2", "z3", "z4", "z5", "z6", "z7", "z8"]:
        print(f"  {key}. {ZUORA_API_TESTS[key][0]}")
    print("\n--- BILLING ARCHITECT TESTS (Advisory) ---")
    for key in ["ba1", "ba2", "ba3", "ba4", "ba5", "ba6", "ba7", "ba8", "ba9", "ba10"]:
        print(f"  {key}. {BA_TESTS[key][0]}")
    print("\n--- ARCHITECT DEMO SCENARIOS (Arch-0 to Arch-7) ---")
    for key in ["arch0", "arch1", "arch2", "arch3", "arch4", "arch5", "arch6", "arch7"]:
        print(f"  {key}. {ARCH_TESTS[key][0]}")
    print("\n--- BA 4-STAGE FLOW TESTS (bf1-bf6) ---")
    for key in ["bf1", "bf2", "bf2b", "bf3", "bf3b", "bf4", "bf4b", "bf5", "bf6"]:
        print(f"  {key}. {BA_FLOW_TESTS[key][0]}")
    print("\n  a. Run ALL PM tests")
    print("  z. Run ALL Zuora API tests")
    print("  b. Run ALL Billing Architect tests")
    print("  arch. Run ALL Architect demo scenarios")
    print("  bf. Run ALL BA 4-Stage Flow tests")
    print("  q. Quit")
    print("-" * 60)


def run_interactive():
    """Run tests interactively."""
    while True:
        show_menu()
        choice = (
            input(
                "\nSelect test (1-16, z1-z8, ba1-ba10, arch0-arch7, bf1-bf6, a, z, b, arch, bf, or q): "
            )
            .strip()
            .lower()
        )

        if choice == "q":
            print("Goodbye!")
            break
        elif choice == "a":
            print("\nRunning ALL PM tests...")
            for key, (name, func) in PM_TESTS.items():
                func()
        elif choice == "z":
            print("\nRunning ALL Zuora API tests...")
            for key, (name, func) in ZUORA_API_TESTS.items():
                func()
        elif choice == "b":
            print("\nRunning ALL Billing Architect tests...")
            for key, (name, func) in BA_TESTS.items():
                func()
        elif choice == "bf":
            print("\nRunning ALL BA 4-Stage Flow tests...")
            for key, (name, func) in BA_FLOW_TESTS.items():
                func()
        elif choice == "arch":
            print("\nRunning ALL Architect demo scenarios...")
            for key, (name, func) in ARCH_TESTS.items():
                func()
        elif choice in ALL_TESTS:
            ALL_TESTS[choice][1]()
        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Run specific test by number
        test_num = sys.argv[1]
        if test_num in ALL_TESTS:
            ALL_TESTS[test_num][1]()
        elif test_num == "all" or test_num == "a":
            for key, (name, func) in PM_TESTS.items():
                func()
        elif test_num == "z":
            for key, (name, func) in ZUORA_API_TESTS.items():
                func()
        elif test_num == "b":
            for key, (name, func) in BA_TESTS.items():
                func()
        elif test_num == "arch":
            for key, (name, func) in ARCH_TESTS.items():
                func()
        elif test_num == "bf":
            for key, (name, func) in BA_FLOW_TESTS.items():
                func()
        else:
            print(f"Unknown test: {test_num}")
            print(
                f"Available: {', '.join(ALL_TESTS.keys())}, a (all PM), z (all Zuora), b (all BA), arch (all Architect), bf (all BA Flow)"
            )
    else:
        # Interactive menu
        run_interactive()
