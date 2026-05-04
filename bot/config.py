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
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ALLOWED_USER_IDS = _split_ids(os.environ.get("ALLOWED_USER_IDS", ""))

# Default to polling so a freshly-deployed container works without any
# webhook URL setup. Switch to ``webhook`` + set ``PUBLIC_URL`` for
# production scale.
MODE = os.environ.get("BOT_MODE", "polling")
PORT = int(os.environ.get("PORT", "8080"))
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")
WEBHOOK_PATH = f"/tg/{BOT_TOKEN.split(':', 1)[0]}"
WEBHOOK_URL = f"{PUBLIC_URL}{WEBHOOK_PATH}" if PUBLIC_URL else ""


def _resolve_keepalive_url() -> str:
    """Best-effort detect the bot's own public URL for self-pinging.

    Render, Railway, Fly.io expose this as platform-specific env vars; if
    none of them are set, fall back to ``KEEP_ALIVE_URL`` or ``PUBLIC_URL``.
    Returns empty string when no URL is known (local dev / VPS) — caller
    should treat that as "self-ping disabled".
    """
    explicit = os.environ.get("KEEP_ALIVE_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    render = os.environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if render:
        return render
    rw_dom = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if rw_dom:
        return f"https://{rw_dom}"
    fly_app = os.environ.get("FLY_APP_NAME", "").strip()
    if fly_app:
        return f"https://{fly_app}.fly.dev"
    return PUBLIC_URL


# Self-ping keeps Render Free awake. Set ``KEEP_ALIVE_INTERVAL=0`` to
# disable the loop even when a URL is detected.
KEEP_ALIVE_URL = _resolve_keepalive_url()
KEEP_ALIVE_INTERVAL = int(os.environ.get("KEEP_ALIVE_INTERVAL", "30"))

DEFAULT_MODEL = os.environ.get("MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
# Backward-compat alias for older imports.
MODEL = DEFAULT_MODEL
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
