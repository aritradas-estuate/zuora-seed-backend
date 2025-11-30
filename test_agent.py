from agents.zuora_agent import agent

def test_agent():
    # Test 1: Simple greeting / capability check
    print("\n--- Test 1: Capability Check ---")
    try:
        response = agent("Hi, what can you do?", stream=False)
        print(f"Agent Response: {response}")
    except Exception as e:
        print(f"Error: {e}")

    # Test 2: Structured Product Creation (Preview)
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

if __name__ == "__main__":
    test_agent()
