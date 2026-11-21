import os
from pathlib import Path
from dotenv import load_dotenv

# Workspace root and .env path
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# YAML Configuration Loader
YAML_CONFIG = {}
CONFIG_YAML_PATH = BASE_DIR / "scraper_config.yaml"
if CONFIG_YAML_PATH.exists():
    try:
        import yaml
        with open(CONFIG_YAML_PATH, "r", encoding="utf-8") as f:
            YAML_CONFIG = yaml.safe_load(f) or {}
    except Exception:
        YAML_CONFIG = {}

# General & Client Settings
CLIENT_NAME = os.getenv("CLIENT_NAME", YAML_CONFIG.get("general", {}).get("client_name", "Sunset Group"))
CLIENT_ENTITY = os.getenv("CLIENT_ENTITY", YAML_CONFIG.get("general", {}).get("client_entity", "Sunset Kuakata Hotel & Resort"))
DEFAULT_COUNTRY = os.getenv("DEFAULT_COUNTRY", YAML_CONFIG.get("general", {}).get("default_country", "Bangladesh"))
DEFAULT_CITY = os.getenv("DEFAULT_CITY", YAML_CONFIG.get("general", {}).get("default_city", "Dhaka"))
TARGET_INDUSTRY = os.getenv("TARGET_INDUSTRY", YAML_CONFIG.get("general", {}).get("target_industry", "Corporate & Hospitality"))

# Groq Cloud Configuration (Primary AI Validation Engine)
GROQ_CLOUD_API_KEY = (
    os.getenv("GROQ_CLOUD_API_KEY") or
    os.getenv("Groq_cloud_api_key") or
    ""
).strip()

MODEL_NAME = (
    os.getenv("MODEL_NAME") or
    os.getenv("Model_name") or
    YAML_CONFIG.get("ai_qualification", {}).get("model", "openai/gpt-oss-120b")
).strip()

GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").strip()

# Primary Search API Configuration (Brave Search)
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()

# Scraper & Crawler Settings
DEFAULT_USER_AGENT = os.getenv(
    "DEFAULT_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
).strip()

RATE_LIMIT_DELAY = float(os.getenv("RATE_LIMIT_DELAY_SECONDS", str(YAML_CONFIG.get("concurrency", {}).get("per_domain_delay_seconds", 1.0))))
MAX_AGENT_ITERATIONS = int(os.getenv("MAX_AGENT_ITERATIONS", "10"))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", str(YAML_CONFIG.get("concurrency", {}).get("max_workers", 6))))
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", str(YAML_CONFIG.get("concurrency", {}).get("http_timeout_seconds", 10.0))))
PLAYWRIGHT_TIMEOUT_MS = int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", str(YAML_CONFIG.get("concurrency", {}).get("playwright_timeout_ms", 15000))))

# Proxy Configuration
PROXY_URL = os.getenv("PROXY_URL") or os.getenv("HTTP_PROXY") or YAML_CONFIG.get("proxies", {}).get("http_proxy", "")

# Server Port Configuration
PORT = int(os.getenv("PORT", "8001"))

# Database Configuration
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = Path(os.getenv("DB_PATH", str(DATA_DIR / "sunset_leads.db")))

# Quality & Scoring Config
MIN_COMPLETENESS_SCORE = int(os.getenv("MIN_COMPLETENESS_SCORE", str(YAML_CONFIG.get("validation", {}).get("min_completeness_score", 50))))
ALLOW_LANDLINE_PHONES = os.getenv("ALLOW_LANDLINE_PHONES", "true").lower() in ("true", "1", "yes")
FUZZY_DEDUP_THRESHOLD = float(os.getenv("FUZZY_DEDUP_THRESHOLD", str(YAML_CONFIG.get("validation", {}).get("fuzzy_dedup_threshold", 0.88))))

def has_groq_credentials() -> bool:
    """Returns True if Groq API key is present."""
    return bool(GROQ_CLOUD_API_KEY)

def has_brave_credentials() -> bool:
    """Returns True if Brave Search API key is present."""
    return bool(BRAVE_SEARCH_API_KEY)
