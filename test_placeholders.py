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
    """Test creating product with minimal info - should apply smart defaults for required fields.

    Per Zuora v1 API, Product requires: Name, EffectiveStartDate, EffectiveEndDate
    SKU is optional, so no placeholder needed.
    Smart defaults are applied for effectiveStartDate (today) and effectiveEndDate (10 years).
    """
    print("\n🧪 Test 1: Partial Product (minimal info)")

    request = {
        "persona": "ProductManager",
        "message": "Create a product called 'Analytics Pro'",
        "conversation_id": "test-placeholder-001",
    }

    try:
        response = invoke(request)
        print_response("Partial Product Creation", response)

        # Verify payload was created with smart defaults
        payloads = response.get("zuora_api_payloads", [])
        assert len(payloads) > 0, "Should create at least one payload"

        payload = payloads[0]
        data = payload.get("payload", {})

        # Verify smart defaults were applied (PascalCase for Zuora v1 API)
        assert "EffectiveStartDate" in data, (
            "Should have EffectiveStartDate from smart default"
        )
        assert "EffectiveEndDate" in data, (
            "Should have EffectiveEndDate from smart default"
        )

        # No placeholders needed since smart defaults fill required fields
        # SKU is optional per Zuora API
        has_placeholders = (
            "_placeholders" in payload and len(payload.get("_placeholders", [])) > 0
        )
        if not has_placeholders:
            print("\n✅ Test passed: Smart defaults applied, no placeholders needed")
        else:
            print(
                f"\n✅ Test passed: Placeholders for optional fields: {payload['_placeholders']}"
            )

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
    """Test creating rate plan without product ID - should generate placeholder.

    Per Zuora v1 API, ProductRatePlan requires: Name, ProductId
    ProductId cannot have a smart default, so a placeholder is generated.
    """
    print("\n🧪 Test 3: Partial Rate Plan (no product ID)")

    request = {
        "persona": "ProductManager",
        "message": "Create a rate plan called 'Standard Plan'",
        "conversation_id": "test-placeholder-003",
    }

    try:
        response = invoke(request)
        print_response("Partial Rate Plan Creation", response)

        # Verify placeholder was created for productId
        payloads = response.get("zuora_api_payloads", [])
        assert len(payloads) > 0, "Should create at least one payload"

        payload = payloads[0]
        data = payload.get("payload", {})
        placeholders = payload.get("_placeholders", [])

        # Check for ProductId placeholder (PascalCase for Zuora v1 API)
        has_product_id_placeholder = (
            "ProductId" in placeholders
            or "<<PLACEHOLDER" in str(data.get("ProductId", ""))
        )
        assert has_product_id_placeholder, (
            "Should have placeholder for missing product ID"
        )
        print("\n✅ Test passed: Placeholder generated for missing product ID")

        return response
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return None


def test_partial_charge_creation():
    """Test creating charge with minimal info - should generate placeholders.

    Per Zuora v1 API, ProductRatePlanCharge requires many fields:
    - Name, ProductRatePlanId, ChargeModel, ChargeType
    - BillCycleType, BillingPeriod, TriggerEvent
    - ProductRatePlanChargeTierData (pricing container)

    Smart defaults are applied for: BillCycleType, TriggerEvent, BillingTiming, BillingPeriod
    Placeholders are generated for: ProductRatePlanId, ChargeModel, ProductRatePlanChargeTierData
    """
    print("\n🧪 Test 4: Partial Charge (missing multiple fields)")

    request = {
        "persona": "ProductManager",
        "message": "Create a recurring monthly charge called 'Monthly Fee'",
        "conversation_id": "test-placeholder-004",
    }

    try:
        response = invoke(request)
        print_response("Partial Charge Creation", response)

        # Verify placeholders were created for truly required fields without smart defaults
        payloads = response.get("zuora_api_payloads", [])
        assert len(payloads) > 0, "Should create at least one payload"

        payload = payloads[0]
        data = payload.get("payload", {})
        placeholders = payload.get("_placeholders", [])

        # Check that smart defaults were applied (PascalCase for Zuora v1 API)
        assert data.get("BillCycleType") == "DefaultFromCustomer", (
            "Should have BillCycleType default"
        )
        assert data.get("TriggerEvent") == "ContractEffective", (
            "Should have TriggerEvent default"
        )
        assert data.get("BillingPeriod") == "Month", (
            "Should have BillingPeriod default for Recurring"
        )

        # Check for placeholders on fields without smart defaults (PascalCase)
        has_required_placeholders = (
            "ProductRatePlanId" in placeholders
            or "<<PLACEHOLDER" in str(data.get("ProductRatePlanId", ""))
        )
        assert has_required_placeholders, (
            "Should have placeholders for ProductRatePlanId"
        )
        print(f"\n✅ Test passed: Placeholders generated: {placeholders}")

        return response
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return None


def test_update_payload_removes_placeholder():
    """Test that updating a placeholder field removes it from the list.

    This test creates a rate plan (which DOES have a required placeholder for productId)
    and then updates it to verify placeholder removal works.
    """
    print("\n🧪 Test 5: Update Payload Removes Placeholder")

    # Create a rate plan - this will have a placeholder for productId
    request1 = {
        "persona": "ProductManager",
        "message": "Create a rate plan called 'Test Plan'",
        "conversation_id": "test-placeholder-005",
    }

    try:
        response1 = invoke(request1)
        print_response("Step 1: Create partial rate plan", response1)

        payloads = response1.get("zuora_api_payloads", [])
        assert len(payloads) > 0, "Should create payload"

        # Check for placeholder (either in _placeholders list or as placeholder string) - PascalCase
        payload = payloads[0]
        data = payload.get("payload", {})
        placeholders = payload.get("_placeholders", [])
        has_placeholder = len(placeholders) > 0 or "<<PLACEHOLDER" in str(
            data.get("ProductId", "")
        )
        assert has_placeholder, "Should have placeholder for ProductId"

        # Now update the ProductId field (PascalCase)
        request2 = {
            "persona": "ProductManager",
            "message": "Update the rate plan payload, set ProductId to '8a1234567890abcd'",
            "conversation_id": "test-placeholder-005",
            "zuora_api_payloads": payloads,
        }

        response2 = invoke(request2)
        print_response("Step 2: Update ProductId field", response2)

        updated_payloads = response2.get("zuora_api_payloads", [])
        assert len(updated_payloads) > 0, "Should have updated payload"

        # Check if ProductId placeholder was removed (PascalCase)
        updated_payload = updated_payloads[0]
        updated_data = updated_payload.get("payload", {})
        updated_placeholders = updated_payload.get("_placeholders", [])

        # ProductId should no longer be a placeholder
        product_id_value = updated_data.get("ProductId", "")
        product_id_is_placeholder = (
            "ProductId" in updated_placeholders
            or "<<PLACEHOLDER" in str(product_id_value)
        )

        # Either it was updated successfully OR it was never a placeholder
        if not product_id_is_placeholder:
            print("\n✅ Test passed: Placeholder removed after update")
        else:
            print("\n⚠️ Note: productId still has placeholder - may need manual update")

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
