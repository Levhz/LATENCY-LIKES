"""Central config. Sab .env se aata hai."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR") or (BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "fflike.db"


def _ints(raw: str):
    return {int(x) for x in raw.replace(" ", "").split(",") if x.strip().lstrip("-").isdigit()}


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GUILD_ID = int(os.getenv("GUILD_ID") or 0)
ALLOWED_CHANNEL_IDS = _ints(os.getenv("ALLOWED_CHANNEL_IDS", ""))
ADMIN_IDS = _ints(os.getenv("ADMIN_IDS", ""))
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip() or secrets.token_urlsafe(24)
API_KEY = os.getenv("API_KEY", "").strip() or secrets.token_urlsafe(24)

DEFAULT_REGION = os.getenv("DEFAULT_REGION", "IND").upper()
DAY_TZ = os.getenv("DAY_TZ", "Asia/Kolkata")

COST_PER_CMD = int(os.getenv("COST_PER_CMD", "10"))
COST_PER_LIKE = int(os.getenv("COST_PER_LIKE", "0"))
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "100"))
MAX_AMOUNT = int(os.getenv("MAX_AMOUNT", "100"))
WELCOME_CREDITS = int(os.getenv("WELCOME_CREDITS", "0"))

POOL_TARGET = int(os.getenv("POOL_TARGET", "5"))
POOL_MIN = int(os.getenv("POOL_MIN", "2"))
POOL_CREATE_CONCURRENCY = max(1, int(os.getenv("POOL_CREATE_CONCURRENCY", "1")))
REG_GAP = float(os.getenv("REG_GAP", "3"))
ACCOUNT_DAILY_CAP = int(os.getenv("ACCOUNT_DAILY_CAP", "100"))
ACCOUNT_MAX_FAILS = int(os.getenv("ACCOUNT_MAX_FAILS", "3"))
LIKE_GAP = float(os.getenv("LIKE_GAP", "0.35"))
CMD_COOLDOWN = float(os.getenv("CMD_COOLDOWN", "5"))

NAJMI_NAME_PREFIX = os.getenv("NAJMI_NAME_PREFIX", "LatencyZ")
NAJMI_USE_TOR = os.getenv("NAJMI_USE_TOR", "1") != "0"
NAJMI_PROXY = os.getenv("NAJMI_PROXY", "").strip()
NAJMI_TOR_TIMEOUT = float(os.getenv("NAJMI_TOR_TIMEOUT", "90"))
NAJMI_READY_TIMEOUT = float(os.getenv("NAJMI_READY_TIMEOUT", "120"))
