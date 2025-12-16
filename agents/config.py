import os
from dotenv import load_dotenv

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "zuora-seed-agent")
GEN_MODEL_ID = os.getenv("GEN_MODEL_ID", "qwen.qwen3-next-80b-a3b")
ZUORA_CLIENT_ID = os.getenv("ZUORA_CLIENT_ID")
ZUORA_CLIENT_SECRET = os.getenv("ZUORA_CLIENT_SECRET")
ZUORA_ENV = os.getenv("ZUORA_ENV", "sandbox")

# Observability Configuration
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "zuora-seed-agent")
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"

# Performance Configuration
ZUORA_API_CACHE_ENABLED = os.getenv("ZUORA_API_CACHE_ENABLED", "true").lower() == "true"
ZUORA_API_CACHE_TTL_SECONDS = int(os.getenv("ZUORA_API_CACHE_TTL_SECONDS", "300"))
ZUORA_API_RETRY_ATTEMPTS = int(os.getenv("ZUORA_API_RETRY_ATTEMPTS", "1"))
ZUORA_API_RETRY_BACKOFF_FACTOR = float(
    os.getenv("ZUORA_API_RETRY_BACKOFF_FACTOR", "0.5")
)
ZUORA_API_CONNECTION_POOL_SIZE = int(os.getenv("ZUORA_API_CONNECTION_POOL_SIZE", "10"))
ZUORA_API_REQUEST_TIMEOUT = int(os.getenv("ZUORA_API_REQUEST_TIMEOUT", "15"))
ZUORA_OAUTH_TIMEOUT = int(os.getenv("ZUORA_OAUTH_TIMEOUT", "10"))

# Conversation History Management
MAX_CONVERSATION_TURNS = int(os.getenv("MAX_CONVERSATION_TURNS", "3"))
