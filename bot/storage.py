import json
import os
from pathlib import Path

from .config import DATA_DIR, HISTORY_LIMIT, PROJECTS_DIR

# Settings live under this key inside state.json so they don't collide with
# user-id-keyed entries (Telegram user ids are stringified ints).
_SETTINGS_KEY = "_settings"

# Providers we know about. Each entry maps to a UI label and the env-var that
# acts as a fallback when nothing has been set via Telegram.
KNOWN_PROVIDERS: dict[str, str] = {
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 10:
        return "***"
    return f"{key[:6]}***{key[-4:]}"


class Storage:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir
        self.state_file = data_dir / "state.json"
        self._state = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        self.state_file.write_text(json.dumps(self._state, ensure_ascii=False, indent=2))
        try:
            os.chmod(self.state_file, 0o600)
        except OSError:
            # Best-effort on platforms that don't support chmod.
            pass

    # ---- per-user state -------------------------------------------------

    def _user(self, user_id: int) -> dict:
        key = str(user_id)
        if key not in self._state:
            self._state[key] = {"cwd": None, "history": []}
        return self._state[key]

    def get_cwd(self, user_id: int) -> Path | None:
        cwd = self._user(user_id).get("cwd")
        if cwd is None:
            return None
        path = Path(cwd)
        return path if path.exists() else None

    def set_cwd(self, user_id: int, path: Path) -> None:
        self._user(user_id)["cwd"] = str(path)
        self._save()

    def get_history(self, user_id: int) -> list[dict]:
        return list(self._user(user_id).get("history", []))

    def append_history(self, user_id: int, message: dict) -> None:
        history = self._user(user_id).setdefault("history", [])
        history.append(message)
        if len(history) > HISTORY_LIMIT * 2:
            del history[: len(history) - HISTORY_LIMIT * 2]
        self._save()

    def clear_history(self, user_id: int) -> None:
        self._user(user_id)["history"] = []
        self._save()

    def list_projects(self) -> list[str]:
        if not PROJECTS_DIR.exists():
            return []
        return sorted(p.name for p in PROJECTS_DIR.iterdir() if p.is_dir())

    # ---- bot-wide settings (keys, model, enabled flag) ------------------

    def _settings(self) -> dict:
        return self._state.setdefault(_SETTINGS_KEY, {})

    def set_provider_key(self, provider: str, key: str) -> None:
        provider = provider.lower()
        if provider not in KNOWN_PROVIDERS:
            raise ValueError(
                f"unknown provider '{provider}'. known: {', '.join(KNOWN_PROVIDERS)}"
            )
        keys = self._settings().setdefault("keys", {})
        keys[provider] = key
        self._save()

    def delete_provider_key(self, provider: str) -> bool:
        provider = provider.lower()
        keys = self._settings().get("keys", {})
        if provider in keys:
            del keys[provider]
            self._save()
            return True
        return False

    def get_provider_key(self, provider: str) -> str:
        """Return the key for ``provider`` from state, falling back to env."""
        provider = provider.lower()
        stored = self._settings().get("keys", {}).get(provider)
        if stored:
            return stored
        env_var = KNOWN_PROVIDERS.get(provider)
        if env_var:
            return os.environ.get(env_var, "")
        return ""

    def list_provider_keys(self) -> dict[str, dict]:
        """List known providers with the source and a masked preview."""
        out: dict[str, dict] = {}
        keys = self._settings().get("keys", {})
        for provider, env_var in KNOWN_PROVIDERS.items():
            stored = keys.get(provider, "")
            env_value = os.environ.get(env_var, "")
            active = stored or env_value
            out[provider] = {
                "source": "telegram" if stored else ("env" if env_value else "none"),
                "masked": _mask_key(active),
                "env_var": env_var,
            }
        return out

    def set_model(self, model: str) -> None:
        self._settings()["model"] = model
        self._save()

    def get_model(self) -> str:
        from .config import DEFAULT_MODEL  # local import to avoid cycles

        return self._settings().get("model") or DEFAULT_MODEL

    def is_enabled(self) -> bool:
        return bool(self._settings().get("enabled", True))

    # ---- brain mode (auto vs devin) -------------------------------------

    def get_brain(self) -> str:
        """Return current brain mode: ``auto`` (LLM via OpenRouter) or ``devin``.

        ``devin`` mode means the bot does NOT auto-reply; incoming messages
        are logged to ``data/inbox.log`` and a real Devin session (with shell
        access to the same VM) responds via ``python -m bot.send``.
        """
        return str(self._settings().get("brain", "auto"))

    def set_brain(self, mode: str) -> None:
        if mode not in ("auto", "devin"):
            raise ValueError(f"unknown brain mode '{mode}', expected 'auto' or 'devin'")
        self._settings()["brain"] = mode
        self._save()

    def set_enabled(self, enabled: bool) -> None:
        self._settings()["enabled"] = bool(enabled)
        self._save()

    # ---- owner (single-owner claim) -------------------------------------

    def get_owner_id(self) -> int | None:
        """Telegram user-id that owns this container, or ``None`` if unclaimed."""
        raw = self._settings().get("owner_id")
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    def set_owner_id(self, user_id: int) -> None:
        """Lock the container to a single Telegram user. Idempotent."""
        self._settings()["owner_id"] = int(user_id)
        self._save()

    # ---- LLM provider selection (auto-mode backend) ---------------------

    def get_provider(self) -> str:
        """Which LLM provider auto-mode talks to.

        Defaults to ``openrouter`` for backwards compatibility. Other valid
        values are ``custom`` (a self-hosted OpenAI-compatible endpoint) or
        ``devin`` (handled separately by brain=devin and ignored here).
        """
        return str(self._settings().get("provider", "openrouter"))

    def set_provider(self, provider: str) -> None:
        if provider not in ("openrouter", "custom"):
            raise ValueError(
                f"unknown provider '{provider}', expected 'openrouter' or 'custom'"
            )
        self._settings()["provider"] = provider
        self._save()

    def get_base_url(self) -> str:
        """Base URL for the active provider. Empty = use provider's default."""
        return str(self._settings().get("base_url", ""))

    def set_base_url(self, url: str) -> None:
        self._settings()["base_url"] = url.rstrip("/")
        self._save()


storage = Storage()
