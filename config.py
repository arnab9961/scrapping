import os
from pathlib import Path
from dotenv import load_dotenv

# Workspace root and .env path
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# Groq Cloud Configuration (Primary AI Validation Engine)
GROQ_CLOUD_API_KEY = (
    os.getenv("GROQ_CLOUD_API_KEY") or
    os.getenv("Groq_cloud_api_key") or
    ""
).strip()

MODEL_NAME = (
    os.getenv("MODEL_NAME") or
    os.getenv("Model_name") or
    "openai/gpt-oss-120b"
).strip()

GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").strip()

# Primary Search API Configuration (Brave Search)
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()

# Scraper & Crawler Settings
DEFAULT_USER_AGENT = os.getenv(
    "DEFAULT_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
).strip()

RATE_LIMIT_DELAY = float(os.getenv("RATE_LIMIT_DELAY_SECONDS", "1.0"))
MAX_AGENT_ITERATIONS = int(os.getenv("MAX_AGENT_ITERATIONS", "10"))
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "10.0"))
PLAYWRIGHT_TIMEOUT_MS = int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "15000"))

# Server Port Configuration
PORT = int(os.getenv("PORT", "8001"))

# Database Configuration
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = Path(os.getenv("DB_PATH", str(DATA_DIR / "sunset_leads.db")))

def has_groq_credentials() -> bool:
    """Returns True if Groq API key is present."""
    return bool(GROQ_CLOUD_API_KEY)

def has_brave_credentials() -> bool:
    """Returns True if Brave Search API key is present."""
    return bool(BRAVE_SEARCH_API_KEY)
