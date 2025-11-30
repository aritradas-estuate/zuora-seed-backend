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
# TEST MENU
# =============================================================================

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


def show_menu():
    """Display test menu."""
    print("\n" + "=" * 60)
    print("ZUORA SEED - PRODUCT MANAGER TEST MENU")
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
    print("\n  a. Run ALL tests")
    print("  q. Quit")
    print("-" * 60)


def run_interactive():
    """Run tests interactively."""
    while True:
        show_menu()
        choice = input("\nSelect test (1-16, a, or q): ").strip().lower()

        if choice == 'q':
            print("Goodbye!")
            break
        elif choice == 'a':
            print("\nRunning ALL tests...")
            for key, (name, func) in PM_TESTS.items():
                func()
        elif choice in PM_TESTS:
            PM_TESTS[choice][1]()
        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Run specific test by number
        test_num = sys.argv[1]
        if test_num in PM_TESTS:
            PM_TESTS[test_num][1]()
        elif test_num == "all":
            for key, (name, func) in PM_TESTS.items():
                func()
        else:
            print(f"Unknown test: {test_num}")
            print(f"Available: {', '.join(PM_TESTS.keys())}, all")
    else:
        # Interactive menu
        run_interactive()
