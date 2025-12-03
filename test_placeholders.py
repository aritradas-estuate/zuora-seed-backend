"""
Test cases for placeholder functionality.
Tests the new placeholder generation and filling behavior.
"""

import json
from agentcore_app import invoke


def print_response(test_name: str, response: dict):
    """Pretty print test response."""
    print(f"\n{'=' * 70}")
    print(f"TEST: {test_name}")
    print("=" * 70)
    print(f"\nAnswer:\n{response.get('answer', 'No answer')}")

    payloads = response.get("zuora_api_payloads", [])
    if payloads:
        print(f"\nPayloads ({len(payloads)}):")
        for i, payload in enumerate(payloads):
            print(f"\n--- Payload {i + 1} ---")
            print(f"Type: {payload.get('zuora_api_type')}")
            print(f"ID: {payload.get('payload_id')}")
            if "_placeholders" in payload:
                print(f"Placeholders: {payload['_placeholders']}")
            print(f"Data: {json.dumps(payload.get('payload'), indent=2)}")
    print("-" * 70)


def test_partial_product_creation():
    """Test creating product with missing SKU - should generate placeholder."""
    print("\n🧪 Test 1: Partial Product (no SKU)")

    request = {
        "persona": "ProductManager",
        "message": "Create a product called 'Analytics Pro'",
        "conversation_id": "test-placeholder-001",
    }

    try:
        response = invoke(request)
        print_response("Partial Product Creation", response)

        # Verify placeholder was created
        payloads = response.get("zuora_api_payloads", [])
        assert len(payloads) > 0, "Should create at least one payload"

        payload = payloads[0]
        assert "_placeholders" in payload, "Should have placeholders"
        print("\n✅ Test passed: Placeholder generated for missing SKU")

        return response
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return None


def test_complete_product_creation():
    """Test creating product with all info - should NOT have placeholders."""
    print("\n🧪 Test 2: Complete Product")

    request = {
        "persona": "ProductManager",
        "message": "Create a product called 'Analytics Pro' with SKU 'ANALYTICS-PRO' starting today",
        "conversation_id": "test-placeholder-002",
    }

    try:
        response = invoke(request)
        print_response("Complete Product Creation", response)

        # Verify no placeholders
        payloads = response.get("zuora_api_payloads", [])
        assert len(payloads) > 0, "Should create at least one payload"

        payload = payloads[0]
        has_placeholders = (
            "_placeholders" in payload and len(payload["_placeholders"]) > 0
        )
        assert not has_placeholders, "Should NOT have placeholders"
        print("\n✅ Test passed: No placeholders for complete product")

        return response
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return None


def test_partial_rate_plan_creation():
    """Test creating rate plan without product ID - should generate placeholder."""
    print("\n🧪 Test 3: Partial Rate Plan (no product ID)")

    request = {
        "persona": "ProductManager",
        "message": "Create a rate plan called 'Standard Plan'",
        "conversation_id": "test-placeholder-003",
    }

    try:
        response = invoke(request)
        print_response("Partial Rate Plan Creation", response)

        # Verify placeholder was created
        payloads = response.get("zuora_api_payloads", [])
        assert len(payloads) > 0, "Should create at least one payload"

        payload = payloads[0]
        assert "_placeholders" in payload, (
            "Should have placeholders for missing product ID"
        )
        print("\n✅ Test passed: Placeholder generated for missing product ID")

        return response
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return None


def test_partial_charge_creation():
    """Test creating charge with minimal info - should generate placeholders."""
    print("\n🧪 Test 4: Partial Charge (missing multiple fields)")

    request = {
        "persona": "ProductManager",
        "message": "Create a recurring monthly charge called 'Monthly Fee'",
        "conversation_id": "test-placeholder-004",
    }

    try:
        response = invoke(request)
        print_response("Partial Charge Creation", response)

        # Verify placeholders were created
        payloads = response.get("zuora_api_payloads", [])
        assert len(payloads) > 0, "Should create at least one payload"

        payload = payloads[0]
        assert "_placeholders" in payload, "Should have placeholders"
        print(
            f"\n✅ Test passed: Placeholders generated: {payload.get('_placeholders')}"
        )

        return response
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return None


def test_update_payload_removes_placeholder():
    """Test that updating a placeholder field removes it from the list."""
    print("\n🧪 Test 5: Update Payload Removes Placeholder")

    # First create a partial product
    request1 = {
        "persona": "ProductManager",
        "message": "Create a product called 'Test Product'",
        "conversation_id": "test-placeholder-005",
    }

    try:
        response1 = invoke(request1)
        print_response("Step 1: Create partial product", response1)

        payloads = response1.get("zuora_api_payloads", [])
        assert len(payloads) > 0, "Should create payload"
        assert "_placeholders" in payloads[0], "Should have placeholders"

        # Now update the SKU field
        request2 = {
            "persona": "ProductManager",
            "message": "Update the product payload, set sku to 'TEST-PRODUCT'",
            "conversation_id": "test-placeholder-005",
            "zuora_api_payloads": payloads,
        }

        response2 = invoke(request2)
        print_response("Step 2: Update SKU field", response2)

        updated_payloads = response2.get("zuora_api_payloads", [])
        assert len(updated_payloads) > 0, "Should have updated payload"

        # Check if SKU placeholder was removed
        updated_payload = updated_payloads[0]
        placeholders = updated_payload.get("_placeholders", [])

        # Should not have 'sku' in placeholders anymore
        sku_still_placeholder = any("sku" in ph.lower() for ph in placeholders)
        assert not sku_still_placeholder, "SKU should no longer be a placeholder"

        print("\n✅ Test passed: Placeholder removed after update")

        return response2
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return None


def run_all_tests():
    """Run all placeholder tests."""
    print("\n" + "=" * 70)
    print("RUNNING PLACEHOLDER TESTS")
    print("=" * 70)

    tests = [
        ("Partial Product", test_partial_product_creation),
        ("Complete Product", test_complete_product_creation),
        ("Partial Rate Plan", test_partial_rate_plan_creation),
        ("Partial Charge", test_partial_charge_creation),
        ("Update Removes Placeholder", test_update_payload_removes_placeholder),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, "✅ PASS" if result else "❌ FAIL"))
        except Exception as e:
            results.append((name, f"❌ ERROR: {e}"))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    for name, status in results:
        print(f"{status} - {name}")

    passed = sum(1 for _, status in results if "✅" in status)
    total = len(results)
    print(f"\nPassed: {passed}/{total}")
    print("=" * 70)


if __name__ == "__main__":
    run_all_tests()
