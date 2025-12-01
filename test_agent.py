import json
from agents.zuora_agent import agent
from agentcore_app import invoke


def print_response(response: dict):
    """Pretty print response with answer and payload count."""
    print(f"\nAnswer:\n{response.get('answer', 'No answer')}")
    payloads = response.get('zuora_api_payloads', [])
    if payloads:
        print(f"\nPayloads ({len(payloads)}):")
        print(json.dumps(payloads, indent=2))
    print("-" * 60)


# =============================================================================
# PRODUCT MANAGER TEST SCENARIOS
# =============================================================================

def test_pm_bundle_starter_suite():
    """PM Test: Bundle product combining multiple products."""
    print("\n" + "=" * 60)
    print("PM TEST: Bundle - Starter Suite")
    print("=" * 60)

    request = {
        "persona": "ProjectManager",
        "message": 'Create a bundle called "Starter Suite" that combines Core CRM and Analytics Pro together at $199 per month.',
        "conversation_id": "pm-bundle-001"
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
        "persona": "ProjectManager",
        "message": 'Create a "Data Transfer" plan with tiered pricing per GB: 0-10 TB @ $0.09/GB, 10-50 TB @ $0.07/GB, 50 TB+ @ $0.05/GB.',
        "conversation_id": "pm-tiered-001"
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
        "persona": "ProjectManager",
        "message": 'Create "Seat Licensing" with volume pricing per seat: 1-10 @ $20, 11-50 @ $18, 51+ @ $15 per month.',
        "conversation_id": "pm-volume-001"
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
        "persona": "ProjectManager",
        "message": 'Create "SMS Pack": $49/month base includes 1,000 SMS, overage $0.015/SMS after that.',
        "conversation_id": "pm-sms-001"
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
        "persona": "ProjectManager",
        "message": 'Create "Premium Support" with $299/month and a one-time setup fee of $999. Add USD & EUR (EUR price €279, setup €949).',
        "conversation_id": "pm-multicurrency-001"
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
        "persona": "ProjectManager",
        "message": 'Create "Growth Bundle (Ramp)": Months 1-3 @ $100/mo, Months 4-6 @ $150/mo, Months 7-12 @ $200/mo; then auto-renew at $200/mo.',
        "conversation_id": "pm-ramp-001"
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
        "persona": "ProjectManager",
        "message": 'Create "API Credits Wallet" with monthly prepayment $500 that loads 100,000 API_CALL credits into a wallet. Allow auto top-up and overage when credits run out. Support USD & EUR.',
        "conversation_id": "pm-prepaid-001"
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
        "persona": "ProjectManager",
        "message": "Connect me to our Zuora sandbox for write operations and confirm OAuth is active. If not connected, block create/update actions and prompt me to authenticate.",
        "conversation_id": "pm-1-connect"
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
        "persona": "ProjectManager",
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
        "conversation_id": "pm-2-guided"
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
        "persona": "ProjectManager",
        "message": """Add a product "Pro Starter EU" with a monthly base fee and a usage add-on for API calls. Price the base at 49 and usage at 0.003 after 10k included.

Assume nothing else. Ask me to confirm:
- Currency (default USD? I also want EUR)
- Billing timing (advance vs arrears)
- Exact UOM name (api_call vs api_calls)
- Whether overage is same rate or different
Then finalize SeedSpec → validate → plan (no execution until I confirm).""",
        "conversation_id": "pm-3-oneshot"
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
        "persona": "ProjectManager",
        "message": 'Create product "Pro Global" with currencies USD and GBP, and a usage UOM named api_calls (plural). If GBP or api_calls aren\'t enabled in this tenant, propose safe auto-fixes (enable GBP, normalize UOM to api_call), show what will change, and re-validate before planning.',
        "conversation_id": "pm-4-tenant"
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
        "persona": "ProjectManager",
        "message": """Create "Pro Hybrid" with:
- Base recurring $49 (no billing period specified on purpose)
- Usage tiered pricing: 1-10k at $0.004, 10,001-50k at $0.0035, then $0.003 beyond
Let the validator catch the missing billing period and any tier gaps. Suggest minimal fixes only and show exactly what you changed before continuing.""",
        "conversation_id": "pm-5-business"
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
        "persona": "ProjectManager",
        "message": 'Create "Pro Suite Enterprise Limited Introductory Edition 2026 - Super Long Name" with two rate plans both named "Base". Enforce unique names and length limits; propose truncated names and "Base (1)/(2)". Show the diff, then proceed if I approve.',
        "conversation_id": "pm-6-duplicates"
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
        "persona": "ProjectManager",
        "message": "Everything looks good—execute: create the product, both rate plans, and charges. Return success with links to the created Product and Rate Plans in the tenant.",
        "conversation_id": "pm-7-execute"
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
        "persona": "ProjectManager",
        "message": "What can you help me with?",
        "conversation_id": "test-conv-001"
    }
    try:
        response = invoke(request_1)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")

    print("\n--- Chat API Test 2: With product payload ---")
    request_2 = {
        "persona": "ProjectManager",
        "message": "Please update the product name to 'Gold Tier Premium'",
        "conversation_id": "test-conv-002",
        "zuora_api_payloads": [
            {
                "payload": {
                    "name": "Gold Tier",
                    "sku": "GOLD-001",
                    "description": "Our gold tier product",
                    "effectiveStartDate": "2024-01-01"
                },
                "zuora_api_type": "product"
            }
        ]
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
        "persona": "ProjectManager",
        "message": "Connect me to our Zuora sandbox for write operations and confirm OAuth is active.",
        "conversation_id": "zuora-connect-001"
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
        "persona": "ProjectManager",
        "message": "Show me all products in the catalog.",
        "conversation_id": "zuora-view-all-001"
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
        "persona": "ProjectManager",
        "message": "I want to view details of a specific product. The product name is 'Solar Plan Premium'.",
        "conversation_id": "zuora-view-specific-001"
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
        "persona": "ProjectManager",
        "message": "Show me the rate plans and charges for 'Solar Plan Premium'.",
        "conversation_id": "zuora-view-rp-001"
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
        "persona": "ProjectManager",
        "message": "I want to update the product 'Solar Plan Basic'. Change the name to 'Solar Plan Premium'.",
        "conversation_id": "zuora-update-name-001"
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
        "persona": "ProjectManager",
        "message": "Update the end date of 'Solar Plan Basic' to 2027-12-31.",
        "conversation_id": "zuora-update-date-001"
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
        "persona": "ProjectManager",
        "message": "I need to update the 'Base Charge' price from $1,200 to $1,350 per year.",
        "conversation_id": "zuora-update-price-001"
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
        "persona": "ProjectManager",
        "message": "I want to change the charge model from Flat Fee Pricing to Tiered Pricing.",
        "conversation_id": "zuora-update-model-001"
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
        "conversation_id": "ba-prepaid-001"
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
        "conversation_id": "ba-topup-001"
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
        "conversation_id": "ba-notification-001"
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
        "conversation_id": "ba-transition-001"
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
        "conversation_id": "ba-map-001"
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
        "conversation_id": "ba-fieldlookup-001"
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
        "conversation_id": "ba-complete-prepaid-001"
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
        "conversation_id": "ba-deposit-001"
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
        "conversation_id": "ba-order-001"
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
        "conversation_id": "ba-docs-001"
    }
    try:
        response = invoke(request)
        print_response(response)
    except Exception as e:
        print(f"Error: {e}")


# =============================================================================
# TEST MENU
# =============================================================================

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
    "z8": ("Update Charge Model (Restricted)", test_zuora_update_charge_model_restricted),
}


ALL_TESTS = {**PM_TESTS, **ZUORA_API_TESTS, **BA_TESTS}


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
    print("\n  a. Run ALL PM tests")
    print("  z. Run ALL Zuora API tests")
    print("  b. Run ALL Billing Architect tests")
    print("  q. Quit")
    print("-" * 60)


def run_interactive():
    """Run tests interactively."""
    while True:
        show_menu()
        choice = input("\nSelect test (1-16, z1-z8, ba1-ba10, a, z, b, or q): ").strip().lower()

        if choice == 'q':
            print("Goodbye!")
            break
        elif choice == 'a':
            print("\nRunning ALL PM tests...")
            for key, (name, func) in PM_TESTS.items():
                func()
        elif choice == 'z':
            print("\nRunning ALL Zuora API tests...")
            for key, (name, func) in ZUORA_API_TESTS.items():
                func()
        elif choice == 'b':
            print("\nRunning ALL Billing Architect tests...")
            for key, (name, func) in BA_TESTS.items():
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
        else:
            print(f"Unknown test: {test_num}")
            print(f"Available: {', '.join(ALL_TESTS.keys())}, a (all PM), z (all Zuora), b (all BA)")
    else:
        # Interactive menu
        run_interactive()
