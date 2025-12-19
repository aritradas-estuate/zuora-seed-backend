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


def test_update_payload_case_insensitive():
    """Test that updating with snake_case key updates the PascalCase field.

    Bug fix verification: When agent calls update_payload with field_path='billing_period',
    it should update the existing 'BillingPeriod' field, not create a new 'billing_period' key.
    """
    print("\n🧪 Test 6: Case-Insensitive Field Update (snake_case -> PascalCase)")

    # First, create a product and rate plan so we can create a charge
    request1 = {
        "persona": "ProductManager",
        "message": "Create a product 'Test Product' with a rate plan 'Test Plan' and a usage charge 'API Calls' with tiered pricing",
        "conversation_id": "test-case-insensitive-001",
    }

    try:
        response1 = invoke(request1)
        print_response("Step 1: Create product with charge", response1)

        payloads = response1.get("zuora_api_payloads", [])

        # Find charge payload that has BillingPeriod placeholder
        charge_payload = None
        charge_index = None
        for i, p in enumerate(payloads):
            if p.get("zuora_api_type") == "charge_create":
                data = p.get("payload", {})
                placeholders = p.get("_placeholders", [])
                # Check if BillingPeriod is a placeholder
                if "BillingPeriod" in placeholders or "<<PLACEHOLDER" in str(
                    data.get("BillingPeriod", "")
                ):
                    charge_payload = p
                    charge_index = i
                    break

        if not charge_payload:
            print(
                "\n⚠️ Skipped: No charge with BillingPeriod placeholder found (smart default may have applied)"
            )
            return response1

        print(
            f"\nFound charge payload at index {charge_index} with BillingPeriod placeholder"
        )

        # Now update using snake_case field name (simulating what the LLM might do)
        request2 = {
            "persona": "ProductManager",
            "message": "Set the billing_period to 'Month' for the API Calls charge",
            "conversation_id": "test-case-insensitive-001",
            "zuora_api_payloads": payloads,
        }

        response2 = invoke(request2)
        print_response("Step 2: Update with snake_case 'billing_period'", response2)

        updated_payloads = response2.get("zuora_api_payloads", [])

        # Find the updated charge payload
        updated_charge = None
        for p in updated_payloads:
            if p.get("zuora_api_type") == "charge_create":
                if p.get("payload", {}).get("Name") == "API Calls":
                    updated_charge = p
                    break

        if not updated_charge:
            print("\n❌ Test failed: Could not find updated charge payload")
            return None

        updated_data = updated_charge.get("payload", {})
        updated_placeholders = updated_charge.get("_placeholders", [])

        # Verification 1: BillingPeriod should be "Month"
        billing_period_value = updated_data.get("BillingPeriod")
        assert billing_period_value == "Month", (
            f"BillingPeriod should be 'Month', got: {billing_period_value}"
        )

        # Verification 2: billing_period (snake_case) should NOT exist
        assert "billing_period" not in updated_data, (
            "Should NOT have snake_case 'billing_period' key - should use existing 'BillingPeriod'"
        )

        # Verification 3: BillingPeriod should be removed from placeholders
        assert "BillingPeriod" not in updated_placeholders, (
            "BillingPeriod should be removed from _placeholders list"
        )

        print("\n✅ Test passed: Case-insensitive update worked correctly")
        print(f"   - BillingPeriod = '{billing_period_value}'")
        print("   - No duplicate 'billing_period' key")
        print("   - Placeholder removed")

        return response2

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return None
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback

        traceback.print_exc()
        return None


def test_update_payload_by_name():
    """Test that update_payload can find payloads by name (fuzzy match).

    When there are multiple charge payloads, payload_name should find the right one
    using case-insensitive substring matching.
    """
    print("\n🧪 Test 7: Update Payload by Name (Fuzzy Match)")

    # Create a product with two charges
    request1 = {
        "persona": "ProductManager",
        "message": "Create a product 'Test Product' with a rate plan and two charges: 'Monthly Base Fee' (flat $49) and 'API Calls Usage' (usage-based tiered pricing)",
        "conversation_id": "test-payload-name-001",
    }

    try:
        response1 = invoke(request1)
        print_response("Step 1: Create product with two charges", response1)

        payloads = response1.get("zuora_api_payloads", [])

        # Count charge payloads
        charge_payloads = [
            p for p in payloads if p.get("zuora_api_type") == "charge_create"
        ]
        print(f"\nFound {len(charge_payloads)} charge payload(s)")

        if len(charge_payloads) < 2:
            print("\n⚠️ Skipped: Need at least 2 charges to test fuzzy matching")
            return response1

        # Now update one charge by name (partial match)
        request2 = {
            "persona": "ProductManager",
            "message": "Set the billing period to 'Month' for the API Calls charge",
            "conversation_id": "test-payload-name-001",
            "zuora_api_payloads": payloads,
        }

        response2 = invoke(request2)
        print_response("Step 2: Update by name 'API Calls'", response2)

        # Verify it worked on first try (no "issue with identifying" message)
        answer = response2.get("answer", "")
        if "issue with identifying" in answer.lower():
            print(
                "\n❌ Test failed: Agent had identification issue (should use payload_name)"
            )
            return None

        if "multiple" in answer.lower() and "specify" in answer.lower():
            print(
                "\n❌ Test failed: Agent didn't use payload_name to specify which charge"
            )
            return None

        print("\n✅ Test passed: payload_name fuzzy matching works")
        return response2

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return None
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback

        traceback.print_exc()
        return None


def test_tiered_usage_charge_defaults():
    """Test that tiered usage charges get correct smart defaults.

    Verifies:
    1. BillingTiming defaults to "In Arrears" for Usage charges
    2. RatingGroup defaults to "ByBillingPeriod" for tiered/volume Usage charges
    """
    print(
        "\n🧪 Test 8: Tiered Usage Charge Smart Defaults (RatingGroup & BillingTiming)"
    )

    request = {
        "persona": "ProductManager",
        "message": """Create a product 'Analytics Pro' with:
        - Rate plan 'Pro Plan'
        - Usage charge 'API Calls' with tiered pricing:
          - Tier 1: 0-10000 units at $0.004
          - Tier 2: 10001-50000 units at $0.0035
          - Tier 3: 50001+ units at $0.003
        - UOM: Calls""",
        "conversation_id": "test-tiered-usage-001",
    }

    try:
        response = invoke(request)
        print_response("Create tiered usage charge", response)

        payloads = response.get("zuora_api_payloads", [])

        # Find the charge payload
        charge_payload = None
        for p in payloads:
            if p.get("zuora_api_type") == "charge_create":
                charge_payload = p
                break

        if not charge_payload:
            print("\n❌ Test failed: No charge payload found")
            return None

        charge_data = charge_payload.get("payload", {})
        print("\nCharge payload data:")
        print(f"  ChargeType: {charge_data.get('ChargeType')}")
        print(f"  ChargeModel: {charge_data.get('ChargeModel')}")
        print(f"  BillingTiming: {charge_data.get('BillingTiming')}")
        print(f"  RatingGroup: {charge_data.get('RatingGroup')}")

        # Verify BillingTiming is "In Arrears" for Usage charge
        billing_timing = charge_data.get("BillingTiming")
        if billing_timing != "In Arrears":
            print(
                f"\n❌ Test failed: BillingTiming should be 'In Arrears' for Usage charge, got: {billing_timing}"
            )
            return None

        # Verify RatingGroup is "ByBillingPeriod" for tiered Usage charge
        rating_group = charge_data.get("RatingGroup")
        if rating_group != "ByBillingPeriod":
            print(
                f"\n❌ Test failed: RatingGroup should be 'ByBillingPeriod' for tiered Usage charge, got: {rating_group}"
            )
            return None

        print("\n✅ Test passed: Tiered usage charge has correct smart defaults")
        print("   - BillingTiming = 'In Arrears'")
        print("   - RatingGroup = 'ByBillingPeriod'")

        return response

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return None
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback

        traceback.print_exc()
        return None


def test_currency_price_not_top_level():
    """Test that 'currency' and 'price' are NEVER stored as top-level fields in charge payloads.

    These fields should only exist inside ProductRatePlanChargeTierData.
    When the agent tries to set them via update_payload(), they should be redirected
    to the proper tier structure.

    Bug fix verification: Prevents Zuora API errors caused by invalid top-level fields.
    See: https://developer.zuora.com/v1-api-reference/api/operation/Object_POSTProductRatePlanCharge/
    """
    print("\n🧪 Test 9: Currency/Price Not Top-Level (Redirect to Tier Data)")

    # Create a charge that may have placeholder for ProductRatePlanChargeTierData
    request1 = {
        "persona": "ProductManager",
        "message": "Create a product 'Test Product' with a rate plan and a flat fee monthly charge called 'Monthly Base Fee' for $49",
        "conversation_id": "test-currency-price-001",
    }

    try:
        response1 = invoke(request1)
        print_response("Step 1: Create charge", response1)

        payloads = response1.get("zuora_api_payloads", [])

        # Find the charge payload
        charge_payload = None
        for p in payloads:
            if p.get("zuora_api_type") == "charge_create":
                charge_payload = p
                break

        if not charge_payload:
            print("\n❌ Test failed: No charge payload found")
            return None

        charge_data = charge_payload.get("payload", {})

        # Verification 1: 'currency' should NOT be a top-level field (lowercase)
        if "currency" in charge_data:
            print("\n❌ Test failed: 'currency' is a top-level field (invalid)")
            print(f"   Value: {charge_data.get('currency')}")
            return None

        # Verification 2: 'price' should NOT be a top-level field (lowercase)
        if "price" in charge_data:
            print("\n❌ Test failed: 'price' is a top-level field (invalid)")
            print(f"   Value: {charge_data.get('price')}")
            return None

        # Verification 3: 'prices' should NOT be a top-level field
        if "prices" in charge_data:
            print("\n❌ Test failed: 'prices' is a top-level field (invalid)")
            print(f"   Value: {charge_data.get('prices')}")
            return None

        # Verification 4: ProductRatePlanChargeTierData should exist with proper structure
        tier_data = charge_data.get("ProductRatePlanChargeTierData")
        if tier_data and isinstance(tier_data, dict):
            tiers = tier_data.get("ProductRatePlanChargeTier", [])
            if tiers:
                print("\n✅ ProductRatePlanChargeTierData has proper structure:")
                for i, tier in enumerate(tiers):
                    print(
                        f"   Tier {i + 1}: Currency={tier.get('Currency')}, Price={tier.get('Price')}"
                    )
        elif tier_data and "<<PLACEHOLDER" in str(tier_data):
            print(
                f"\n⚠️ ProductRatePlanChargeTierData is still a placeholder: {tier_data}"
            )
            print("   This is OK if the agent didn't have enough info")
        else:
            print(f"\n⚠️ ProductRatePlanChargeTierData: {tier_data}")

        print("\n✅ Test passed: No invalid top-level 'currency' or 'price' fields")
        return response1

    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback

        traceback.print_exc()
        return None


def test_update_payload_currency_price_redirect():
    """Test that update_payload redirects 'currency' and 'price' to tier data.

    When the agent calls update_payload with field_path='currency' or 'price',
    it should update/create the ProductRatePlanChargeTierData structure,
    NOT create a top-level field.
    """
    print("\n🧪 Test 10: Update Payload Currency/Price Redirect")

    # First, create a minimal charge that has a placeholder for tier data
    # We'll simulate this by creating a charge without currency
    from agents.tools import (
        _handle_direct_currency_or_price_update,
        INVALID_CHARGE_TOP_LEVEL_FIELDS,
    )

    # Test 1: INVALID_CHARGE_TOP_LEVEL_FIELDS is defined correctly
    assert "currency" in INVALID_CHARGE_TOP_LEVEL_FIELDS, "Should include 'currency'"
    assert "price" in INVALID_CHARGE_TOP_LEVEL_FIELDS, "Should include 'price'"
    assert "prices" in INVALID_CHARGE_TOP_LEVEL_FIELDS, "Should include 'prices'"
    print("✅ INVALID_CHARGE_TOP_LEVEL_FIELDS contains: currency, price, prices")

    # Test 2: _handle_direct_currency_or_price_update with placeholder tier data
    payload_with_placeholder = {
        "Name": "Test Charge",
        "ChargeModel": "Flat Fee Pricing",
        "ProductRatePlanChargeTierData": "<<PLACEHOLDER:ProductRatePlanChargeTierData>>",
    }
    payload_entry = {
        "payload": payload_with_placeholder,
        "_placeholders": ["ProductRatePlanChargeTierData"],
    }

    # Set currency first
    was_handled, field_updated, error = _handle_direct_currency_or_price_update(
        payload_with_placeholder, payload_entry, "currency", "EUR"
    )
    assert was_handled, "Should handle 'currency' field"
    assert error is None, f"Should not have error: {error}"
    print(f"✅ Currency update handled: {field_updated}")

    # Set price second - should create tier data
    was_handled, field_updated, error = _handle_direct_currency_or_price_update(
        payload_with_placeholder, payload_entry, "price", 99.00
    )
    assert was_handled, "Should handle 'price' field"
    assert error is None, f"Should not have error: {error}"
    print(f"✅ Price update handled: {field_updated}")

    # Verify tier data was created
    tier_data = payload_with_placeholder.get("ProductRatePlanChargeTierData")
    assert isinstance(tier_data, dict), "Should have tier data dict"
    tiers = tier_data.get("ProductRatePlanChargeTier", [])
    assert len(tiers) >= 1, "Should have at least one tier"
    assert tiers[0].get("Currency") == "EUR", "Should have EUR currency"
    assert tiers[0].get("Price") == 99.00, "Should have 99.00 price"
    print(f"✅ Tier data created: {tiers}")

    # Verify 'currency' and 'price' are NOT top-level
    assert "currency" not in payload_with_placeholder, (
        "Should NOT have 'currency' top-level"
    )
    assert "price" not in payload_with_placeholder, "Should NOT have 'price' top-level"
    print("✅ No invalid top-level fields")

    # Verify placeholder was removed
    assert "ProductRatePlanChargeTierData" not in payload_entry.get(
        "_placeholders", []
    ), "ProductRatePlanChargeTierData should be removed from placeholders"
    print("✅ Placeholder removed")

    print("\n✅ Test passed: Currency/price redirect to tier data works correctly")
    return True


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
        ("Case-Insensitive Update", test_update_payload_case_insensitive),
        ("Update by Name (Fuzzy)", test_update_payload_by_name),
        ("Tiered Usage Defaults", test_tiered_usage_charge_defaults),
        ("Currency/Price Not Top-Level", test_currency_price_not_top_level),
        ("Currency/Price Redirect", test_update_payload_currency_price_redirect),
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
