import logging
from pathlib import Path

from openai import AsyncOpenAI
from openai._exceptions import APIError

from .config import (
    AGENT_MAX_STEPS,
    APP_TITLE,
    DEFAULT_MODEL,
    FALLBACK_MODELS,
    HTTP_REFERER,
    OPENROUTER_BASE_URL,
)
from .storage import storage
from .tools import TOOL_DEFINITIONS, ToolError, dispatch_tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an autonomous coding agent that operates inside a Telegram bot.

Rules:
- Always answer in the user's language (Russian by default for this user).
- You have access to tools: list_dir, read_file, write_file, exec_bash. Use them whenever the user asks you to look at, change, or run something. Do not invent file contents — read them.
- Be concise: in chat replies aim for short paragraphs. Long file content goes via tools, not into the reply.
- After making changes, suggest a git commit message; do not commit unless the user confirms or explicitly asks.
- If the user asks for git operations, use exec_bash with git commands.
- If no project is selected, tell the user to run /clone <url> or /project <name> first.
"""


class NoApiKeyError(RuntimeError):
    """Raised when no usable provider key is configured anywhere."""


def _build_client() -> AsyncOpenAI:
    """Create a fresh OpenAI client per request so /setkey takes effect immediately.

    Picks the endpoint based on ``storage.get_provider()``:
      - ``openrouter`` (default): hits https://openrouter.ai/api/v1
      - ``custom``: hits ``storage.get_base_url()`` — set via /setup wizard
        for self-hosted endpoints (vLLM, Ollama, Together, Groq, etc.).
    """
    api_key = storage.get_provider_key("openrouter")
    provider = storage.get_provider()
    if provider == "custom":
        base_url = storage.get_base_url() or OPENROUTER_BASE_URL
    else:
        base_url = OPENROUTER_BASE_URL

    if not api_key:
        if provider == "custom":
            raise NoApiKeyError(
                "Не задан API-ключ для кастомного endpoint-а. Открой /setup → 🔑 API ключ."
            )
        raise NoApiKeyError(
            "Не задан ключ OpenRouter. Поставь его командой:\n"
            "<code>/setkey openrouter sk-or-...</code>\n"
            "Получить ключ: https://openrouter.ai/keys"
        )

    headers = {"HTTP-Referer": HTTP_REFERER, "X-Title": APP_TITLE}
    return AsyncOpenAI(api_key=api_key, base_url=base_url, default_headers=headers)


def _candidate_models() -> list[str]:
    """Active model first, then free fallbacks only if active itself is free.

    Premium models (e.g. ``anthropic/claude-opus-4.5``) intentionally do NOT
    fall back to free models — silent downgrade would be confusing.
    """
    active = storage.get_model() or DEFAULT_MODEL
    candidates = [active]
    is_free = ":free" in active or active in FALLBACK_MODELS
    if is_free:
        for m in FALLBACK_MODELS:
            if m != active and m not in candidates:
                candidates.append(m)
    return candidates


def _build_messages(user_id: int, user_text: str) -> list[dict]:
    history = storage.get_history(user_id)
    return (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + history
        + [{"role": "user", "content": user_text}]
    )


async def _call_model(client: AsyncOpenAI, messages: list[dict]) -> tuple[object, str]:
    last_error: Exception | None = None
    for model in _candidate_models():
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                temperature=0.2,
            )
            return resp.choices[0].message, model
        except APIError as exc:
            logger.warning("model %s failed: %s", model, exc)
            last_error = exc
    raise RuntimeError(f"all models failed: {last_error}")


async def run_agent(user_id: int, user_text: str, cwd: Path | None) -> str:
    client = _build_client()
    messages = _build_messages(user_id, user_text)
    final_text = ""
    requested_model = storage.get_model() or DEFAULT_MODEL
    used_model = requested_model

    for step in range(AGENT_MAX_STEPS):
        msg, used_model = await _call_model(client, messages)
        tool_calls = getattr(msg, "tool_calls", None) or []

        assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
        if tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
        messages.append(assistant_entry)

        if not tool_calls:
            final_text = msg.content or ""
            break

        for tc in tool_calls:
            try:
                result = await dispatch_tool(tc.function.name, tc.function.arguments, cwd)
            except ToolError as exc:
                result = f"ERROR: {exc}"
            except Exception as exc:  # noqa: BLE001
                logger.exception("tool %s crashed", tc.function.name)
                result = f"ERROR: {exc}"
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "content": result[:8000],
                }
            )
    else:
        final_text = (
            "(превышен лимит шагов агента — попробуй упростить запрос или /reset)"
        )

    storage.append_history(user_id, {"role": "user", "content": user_text})
    if final_text:
        storage.append_history(user_id, {"role": "assistant", "content": final_text})

    if used_model != requested_model:
        final_text = f"[fallback model: {used_model}]\n{final_text}"
    return final_text or "(пустой ответ)"
