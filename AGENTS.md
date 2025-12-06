# AGENTS.md

## Commands
```bash
source .venv/bin/activate            # Activate virtual environment first
uv sync                              # Install dependencies
agentcore run local                  # Run agent locally
agentcore deploy \                   # Deploy to AWS
  --env ZUORA_CLIENT_ID=<id> \
  --env ZUORA_CLIENT_SECRET=<secret> \
  --env ZUORA_ENV=apisandbox \
  --env MAX_CONVERSATION_TURNS=3 \
  --env GEN_MODEL_ID=qwen.qwen3-next-80b-a3b \
  --auto-update-on-conflict
python test_agent.py                 # Interactive test menu
python test_agent.py ba1             # Run single test by key
ruff check . && ruff format .        # Lint and format
```

## Code Style
- **Imports:** stdlib -> third-party -> relative (`from .module import`)
- **Types:** Always use type hints (`Optional`, `List`, `Dict`, `Any`, `Literal`)
- **Naming:** `snake_case` functions/variables, `PascalCase` classes
- **Docstrings:** Google-style with Args/Returns sections
- **Pydantic:** Use `Field(...)` with descriptions for model fields
- **Errors:** Log with `logging.getLogger(__name__)`
- **Config:** Environment variables via `agents/config.py`
