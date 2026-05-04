"""First-run setup wizard for the bot.

Flow when a fresh container starts up:

1. *Anyone* may click ``/start``. The first user who does so is locked in
   as the **owner** (single-tenant). All later messages from anyone else
   get a polite refusal.

2. Owner is shown a 3-button menu to pick a brain:

   - ``[OpenRouter]``  → opens API/Model/URL config sub-menu
   - ``[Devin.ai]``    → emits a copy-pasteable prompt for a new Devin session
   - ``[Другое]``      → same sub-menu as OpenRouter (custom OpenAI-compatible
     endpoint such as Together, Groq, vLLM, LM Studio, etc.)

3. In the API/Model/URL sub-menu each button starts an FSM step where the
   bot asks for that single field. Sensitive values (API key) get the
   user's message deleted right after capture.

The wizard handlers live in their own ``Router`` so ``handlers.py`` stays
focused on day-to-day commands. The wizard router is included by
``main.py`` *before* the main router so its callback queries take
priority.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .storage import storage

logger = logging.getLogger(__name__)
wizard_router = Router(name="wizard")


# ---- FSM states ----------------------------------------------------------


class SetupStates(StatesGroup):
    awaiting_api_key = State()
    awaiting_model = State()
    awaiting_url = State()


# ---- Keyboards -----------------------------------------------------------


def _kb_claim() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Запустить и стать владельцем", callback_data="claim_owner")]
        ]
    )


def _kb_brain() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧠 OpenRouter (бесплатно/платно, рекомендую)", callback_data="brain:openrouter")],
            [InlineKeyboardButton(text="🎯 Devin.ai (ручные ответы через шелл)", callback_data="brain:devin")],
            [InlineKeyboardButton(text="⚙️  Другое (свой OpenAI-совместимый endpoint)", callback_data="brain:other")],
        ]
    )


def _kb_llm_config(provider_label: str) -> InlineKeyboardMarkup:
    """Sub-menu shown after OpenRouter / Other.

    All three fields are optional individually but at minimum API + Model
    are needed to make a request. The wizard does not enforce that — the
    first message to the bot will surface a clear error if something's
    missing.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🔑 API ключ ({provider_label})", callback_data="cfg:api")],
            [InlineKeyboardButton(text="🤖 Модель", callback_data="cfg:model")],
            [InlineKeyboardButton(text="🌐 URL (только для Другое)", callback_data="cfg:url")],
            [InlineKeyboardButton(text="✅ Готово, поехали", callback_data="cfg:done")],
            [InlineKeyboardButton(text="↩️  Сменить мозг", callback_data="cfg:back")],
        ]
    )


# ---- Helpers -------------------------------------------------------------


def _is_owner(user_id: int) -> bool:
    owner = storage.get_owner_id()
    return owner is not None and owner == user_id


def _provider_label(brain_choice: str) -> str:
    return "openrouter" if brain_choice == "openrouter" else "custom"


# ---- Handlers ------------------------------------------------------------


@wizard_router.message(Command("start"))
async def cmd_start_wizard(message: Message, state: FSMContext) -> None:
    """Owner-aware /start.

    - Unclaimed: anyone may claim. Show big ``Запустить`` button.
    - Owner: re-enter the brain picker (``/setup`` is an alias).
    - Stranger: deny with their id so the *real* owner can spot a leak.
    """
    user = message.from_user
    if user is None:
        return
    await state.clear()

    owner = storage.get_owner_id()
    if owner is None:
        await message.answer(
            "<b>Привет!</b>\n"
            "Ты только что развернул свой контейнер. Я не знаю кому теперь подчиняться — "
            "первый человек, кто нажмёт кнопку ниже, станет владельцем (только он сможет писать боту дальше).\n\n"
            f"Твой Telegram id: <code>{user.id}</code>",
            reply_markup=_kb_claim(),
        )
        return

    if owner != user.id:
        await message.answer(
            "Этот бот уже привязан к другому владельцу. Если это твой контейнер и ты потерял доступ — "
            "удали в <code>data/state.json</code> поле <code>_settings.owner_id</code> и перезапусти бот.\n\n"
            f"Твой Telegram id: <code>{user.id}</code>"
        )
        return

    await message.answer(
        "Ты владелец. Что хочешь делать?\n"
        "• Перенастроить мозг — кнопки ниже\n"
        "• Посмотреть команды — /help",
        reply_markup=_kb_brain(),
    )


@wizard_router.message(Command("setup"))
async def cmd_setup(message: Message, state: FSMContext) -> None:
    """Re-open the brain picker (owner only)."""
    user = message.from_user
    if user is None or not _is_owner(user.id):
        await message.answer("Только владелец может перенастраивать бот.")
        return
    await state.clear()
    await message.answer(
        "Перенастройка. Выбери мозг:",
        reply_markup=_kb_brain(),
    )


@wizard_router.callback_query(F.data == "claim_owner")
async def cb_claim(query: CallbackQuery, state: FSMContext) -> None:
    user = query.from_user
    existing = storage.get_owner_id()
    if existing is not None:
        await query.answer("Владелец уже зарегистрирован.", show_alert=True)
        return
    storage.set_owner_id(user.id)
    await state.clear()
    if query.message is not None:
        await query.message.edit_text(
            f"<b>Готово.</b> Ты владелец (id <code>{user.id}</code>).\n\n"
            "Теперь выбери, кто будет «мозгами» — кто отвечает на сообщения от тебя:",
            reply_markup=_kb_brain(),
        )
    await query.answer("Ты теперь владелец 🎉")


@wizard_router.callback_query(F.data.startswith("brain:"))
async def cb_brain(query: CallbackQuery, state: FSMContext) -> None:
    user = query.from_user
    if not _is_owner(user.id):
        await query.answer("Только владелец.", show_alert=True)
        return

    choice = (query.data or "").split(":", 1)[1]
    await state.clear()

    if choice == "devin":
        # Switch to brain=devin, show the prompt the owner gives to a fresh Devin session.
        storage.set_brain("devin")
        await query.answer("Brain = devin")
        prompt = _devin_handoff_prompt()
        if query.message is not None:
            await query.message.edit_text(
                "<b>Brain = devin</b>. Бот не отвечает сам — он только пишет входящие в "
                "<code>data/inbox.log</code>, а ты сидишь в <a href='https://app.devin.ai'>app.devin.ai</a>, "
                "читаешь их и отвечаешь через шелл-CLI <code>python -m bot.send</code>.\n\n"
                "Скопируй блок ниже и пришли первым сообщением в новую Devin-сессию — там всё про "
                "архитектуру и команды:",
            )
            # Send the prompt as a separate code block so it copies cleanly on mobile.
            await query.message.answer(f"<pre>{_html_escape(prompt)}</pre>")
            await query.message.answer(
                "Готов? /help покажет все команды бота. /setup — поменять мозг."
            )
        return

    # OpenRouter or custom — both share the same sub-menu, only the label and
    # provider label inside storage differ.
    provider = "openrouter" if choice == "openrouter" else "custom"
    storage.set_brain("auto")
    storage.set_provider(provider)
    if provider == "openrouter":
        # Reset any leftover custom URL from a previous "Другое" run.
        storage.set_base_url("")

    label = "OpenRouter" if provider == "openrouter" else "Кастом (свой endpoint)"
    await query.answer(f"Brain = {label}")
    if query.message is not None:
        await query.message.edit_text(
            f"<b>Brain = auto / {label}</b>\n\n"
            "Заполни конфиг по очереди — что не задано, то возьмётся по умолчанию:",
            reply_markup=_kb_llm_config(_provider_label(choice)),
        )


# --- /cfg:* — sub-menu inside OpenRouter / Other --------------------------


@wizard_router.callback_query(F.data == "cfg:back")
async def cb_cfg_back(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(query.from_user.id):
        await query.answer("Только владелец.", show_alert=True)
        return
    await state.clear()
    if query.message is not None:
        await query.message.edit_text(
            "Выбери мозг:",
            reply_markup=_kb_brain(),
        )
    await query.answer()


@wizard_router.callback_query(F.data == "cfg:done")
async def cb_cfg_done(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(query.from_user.id):
        await query.answer("Только владелец.", show_alert=True)
        return
    await state.clear()
    summary = _config_summary()
    if query.message is not None:
        await query.message.edit_text(
            "<b>Готово.</b>\n\n"
            f"{summary}\n\n"
            "Теперь любое сообщение без <code>/</code> уйдёт в LLM. /help — все команды."
        )
    await query.answer()


@wizard_router.callback_query(F.data == "cfg:api")
async def cb_cfg_api(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(query.from_user.id):
        await query.answer("Только владелец.", show_alert=True)
        return
    await state.set_state(SetupStates.awaiting_api_key)
    if query.message is not None:
        provider = storage.get_provider()
        hint = (
            "Получить: <a href='https://openrouter.ai/keys'>openrouter.ai/keys</a>"
            if provider == "openrouter"
            else "Это твой ключ от того endpoint-а, который ты указал в URL"
        )
        await query.message.answer(
            "Пришли API-ключ <b>одним сообщением</b>. Я удалю его из чата как только сохраню.\n\n"
            + hint
        )
    await query.answer()


@wizard_router.callback_query(F.data == "cfg:model")
async def cb_cfg_model(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(query.from_user.id):
        await query.answer("Только владелец.", show_alert=True)
        return
    await state.set_state(SetupStates.awaiting_model)
    if query.message is not None:
        provider = storage.get_provider()
        if provider == "openrouter":
            hint = (
                "Примеры:\n"
                "• <code>nvidia/nemotron-3-super-120b-a12b:free</code> (бесплатно)\n"
                "• <code>anthropic/claude-opus-4.7</code> (платно, лучшее качество)\n"
                "• <code>openai/gpt-5</code>\n"
                "Полный список: <a href='https://openrouter.ai/models'>openrouter.ai/models</a>"
            )
        else:
            hint = (
                "Имя модели для твоего endpoint-а. Например <code>llama3.1:70b</code>, "
                "<code>mistral-large</code>, <code>gpt-4o</code>."
            )
        await query.message.answer(
            "Пришли имя модели одним сообщением.\n\n" + hint
        )
    await query.answer()


@wizard_router.callback_query(F.data == "cfg:url")
async def cb_cfg_url(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(query.from_user.id):
        await query.answer("Только владелец.", show_alert=True)
        return
    if storage.get_provider() == "openrouter":
        # URL для OpenRouter не настраивается, чтобы юзер случайно не сломал коннект.
        await query.answer(
            "Для OpenRouter URL не нужен. Выбери «Другое» если хочешь свой endpoint.",
            show_alert=True,
        )
        return
    await state.set_state(SetupStates.awaiting_url)
    if query.message is not None:
        await query.message.answer(
            "Пришли URL endpoint-а одним сообщением. Должен быть OpenAI-совместимым "
            "(заканчивается на <code>/v1</code>).\n\n"
            "Примеры:\n"
            "• <code>https://api.together.xyz/v1</code>\n"
            "• <code>https://api.groq.com/openai/v1</code>\n"
            "• <code>http://localhost:11434/v1</code> (Ollama)\n"
            "• <code>http://10.0.0.5:8000/v1</code> (свой vLLM)"
        )
    await query.answer()


# --- text capture for FSM --------------------------------------------------
# Filter out commands so users can /cancel, /setup, /help mid-wizard without
# their command being treated as the requested input.
_NOT_A_COMMAND = F.text & ~F.text.startswith("/")


@wizard_router.message(StateFilter(SetupStates.awaiting_api_key), _NOT_A_COMMAND)
async def capture_api_key(message: Message, state: FSMContext) -> None:
    if not _is_owner(message.from_user.id if message.from_user else 0):
        return
    key = (message.text or "").strip()
    if not key:
        await message.answer("Пустое сообщение, попробуй ещё раз или нажми «Сменить мозг».")
        return
    # Delete the message with the secret first, then save.
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass
    storage.set_provider_key(_provider_label_from_storage(), key)
    await state.clear()
    summary = _config_summary()
    await message.answer(
        "Ключ сохранён, твоё сообщение удалено.\n\n"
        f"{summary}",
        reply_markup=_kb_llm_config(_provider_label_from_storage()),
    )


@wizard_router.message(StateFilter(SetupStates.awaiting_model), _NOT_A_COMMAND)
async def capture_model(message: Message, state: FSMContext) -> None:
    if not _is_owner(message.from_user.id if message.from_user else 0):
        return
    model = (message.text or "").strip()
    if not model:
        await message.answer("Пустое сообщение, попробуй ещё раз.")
        return
    storage.set_model(model)
    await state.clear()
    summary = _config_summary()
    await message.answer(
        f"Модель сохранена: <code>{_html_escape(model)}</code>\n\n{summary}",
        reply_markup=_kb_llm_config(_provider_label_from_storage()),
    )


@wizard_router.message(StateFilter(SetupStates.awaiting_url), _NOT_A_COMMAND)
async def capture_url(message: Message, state: FSMContext) -> None:
    if not _is_owner(message.from_user.id if message.from_user else 0):
        return
    url = (message.text or "").strip()
    if not url:
        await message.answer("Пустое сообщение, попробуй ещё раз.")
        return
    if not url.startswith(("http://", "https://")):
        await message.answer(
            "URL должен начинаться с <code>http://</code> или <code>https://</code>. Попробуй ещё раз."
        )
        return
    storage.set_base_url(url)
    await state.clear()
    summary = _config_summary()
    await message.answer(
        f"URL сохранён: <code>{_html_escape(url)}</code>\n\n{summary}",
        reply_markup=_kb_llm_config(_provider_label_from_storage()),
    )


# ---- Misc helpers --------------------------------------------------------


def _provider_label_from_storage() -> str:
    return storage.get_provider()


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _config_summary() -> str:
    """Pretty summary of the current LLM config, safe for HTML."""
    provider = storage.get_provider()
    keys = storage.list_provider_keys()
    label = "OpenRouter" if provider == "openrouter" else "Кастомный endpoint"
    key_state = keys.get("openrouter", {}).get("masked") or "не задан"
    if provider != "openrouter":
        key_state = keys.get("openrouter", {}).get("masked") or "не задан (нужен)"
    model = storage.get_model() or "—"
    base_url = storage.get_base_url()
    lines = [
        f"<b>{label}</b>",
        f"  Ключ: <code>{key_state}</code>",
        f"  Модель: <code>{_html_escape(model)}</code>",
    ]
    if provider != "openrouter":
        lines.append(f"  URL: <code>{_html_escape(base_url) if base_url else 'не задан'}</code>")
    return "\n".join(lines)


def _devin_handoff_prompt() -> str:
    """The text the owner pastes into a fresh Devin session.

    Devin will read this once and then live as the bot's brain — picking up
    inbox.log, replying via bot.send, etc.
    """
    return """Ты — мой удалённый ассистент с шелл-доступом к серверу, на котором живёт Telegram-бот.

ЧТО НА СЕРВЕРЕ
- Репо: https://github.com/geodze/ai-codesp (ветка с актуальным ботом — devin/1777827133-bot-key-mgmt)
- Рантайм бота на VM: /home/ubuntu/bot-runtime/  (на твоём боксе путь может быть другим — пользуйся `ls`)
- Лог входящих сообщений: data/inbox.log  (бот пишет туда каждое моё сообщение)
- Состояние (ключи, brain, owner): data/state.json
- BOT_TOKEN — в .env рядом с ботом

ТВОЯ РАБОТА
Бот сейчас в режиме brain=devin: он НЕ отвечает мне сам. Когда я что-то пишу в TG, ты:
1. Читаешь свежие строки в data/inbox.log
2. Понимаешь что я хочу
3. Делаешь работу (правишь код, гонишь тесты, исследуешь, что угодно)
4. Отправляешь мне ответ обратно через CLI:
     set -a && source .env && set +a
     python -m bot.send <chat_id> "ответ"
   chat_id ты находишь в той же inbox.log строке.

ЕСЛИ ТЕБЕ НУЖЕН CONTEXT
Команды бота которые я могу запускать в TG (=ты их видишь в inbox.log как kind=cmd):
  /help, /start, /setup     — справка и перенастройка
  /brain, /setbrain auto|devin
  /clone <url>, /projects, /project <name>, /cd, /pwd
  /exec <bash>, /git <args>
  /keys, /setkey, /delkey, /models, /setmodel
  /enable, /disable, /reset

ВАЖНО
- Я (владелец) пингую тебя в нашем чате когда хочу чтобы ты отреагировал. Между пингами ты простаиваешь.
- Если просьба сложная — сначала разбери, потом ОДНИМ сообщением мне в TG пришли план; я скажу «ок» и ты делай.
- Если меняешь код — делай в ветке, делай PR, ссылку шли в TG.

Когда прочитал — ответь мне в этом чате (тут, у Devin) что готов, и я начну писать в TG."""
