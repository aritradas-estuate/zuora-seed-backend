import os
from dotenv import load_dotenv

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "zuora-seed-agent")
GEN_MODEL_ID = os.getenv("GEN_MODEL_ID", "us.meta.llama3-3-70b-instruct-v1:0")
ZUORA_CLIENT_ID = os.getenv("ZUORA_CLIENT_ID")
ZUORA_CLIENT_SECRET = os.getenv("ZUORA_CLIENT_SECRET")
ZUORA_ENV = os.getenv("ZUORA_ENV", "sandbox")
