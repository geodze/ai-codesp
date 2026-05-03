import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _split_ids(raw: str) -> set[int]:
    out: set[int] = set()
    for chunk in (raw or "").replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            out.add(int(chunk))
    return out


BOT_TOKEN = os.environ["BOT_TOKEN"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
ALLOWED_USER_IDS = _split_ids(os.environ.get("ALLOWED_USER_IDS", ""))

MODE = os.environ.get("BOT_MODE", "webhook")
PORT = int(os.environ.get("PORT", "8080"))
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")
WEBHOOK_PATH = f"/tg/{BOT_TOKEN.split(':', 1)[0]}"
WEBHOOK_URL = f"{PUBLIC_URL}{WEBHOOK_PATH}" if PUBLIC_URL else ""

MODEL = os.environ.get("MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
FALLBACK_MODELS = [
    m.strip()
    for m in os.environ.get(
        "FALLBACK_MODELS",
        "openai/gpt-oss-120b:free,qwen/qwen3-coder:free,minimax/minimax-m2.5:free",
    ).split(",")
    if m.strip()
]

DATA_DIR = Path(os.environ.get("DATA_DIR", "/tmp/bot-data"))
PROJECTS_DIR = DATA_DIR / "projects"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

EXEC_TIMEOUT = int(os.environ.get("EXEC_TIMEOUT", "30"))
MAX_FILE_BYTES = int(os.environ.get("MAX_FILE_BYTES", "200000"))
HISTORY_LIMIT = int(os.environ.get("HISTORY_LIMIT", "20"))
AGENT_MAX_STEPS = int(os.environ.get("AGENT_MAX_STEPS", "8"))

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
HTTP_REFERER = os.environ.get("HTTP_REFERER", "https://github.com/geodze/ai-codesp")
APP_TITLE = os.environ.get("APP_TITLE", "ai-codesp telegram bot")
