from bedrock_agentcore import BedrockAgentCoreApp
from agents.zuora_agent import agent

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    """
    AgentCore entry point for Zuora Seed Agent.

    Expected payload:
    {
        "prompt": str,
        "persona": str (optional),
        "session_id": str (optional, for memory)
    }
    """
    prompt = payload.get("prompt", "")
    persona = payload.get("persona", "")
    session_id = payload.get("session_id")

    # Build full prompt with persona context
    if persona:
        full_prompt = f"User Persona: {persona}.\nUser Request: {prompt}"
    else:
        full_prompt = prompt

    # Invoke agent with session for memory
    response = agent(full_prompt, session_id=session_id)

    return {
        "result": str(response),
        "session_id": session_id
    }


if __name__ == "__main__":
    app.run()
