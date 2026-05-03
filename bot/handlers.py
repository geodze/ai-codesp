import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from .agent import NoApiKeyError, run_agent
from .config import ALLOWED_USER_IDS, DEFAULT_MODEL, PROJECTS_DIR
from .storage import KNOWN_PROVIDERS, storage
from .tools import ToolError, clone_repo, exec_bash, project_root_for

logger = logging.getLogger(__name__)
router = Router()


HELP_TEXT = (
    "<b>codespace bot</b>\n"
    "Активная модель: <code>{model}</code> {state}\n\n"
    "<b>Проекты</b>\n"
    "/projects — список загруженных проектов\n"
    "/clone &lt;git-url&gt; [имя] — клонировать репо\n"
    "/project &lt;имя&gt; — переключиться на проект\n"
    "/cd &lt;путь&gt; — сменить субпапку внутри проекта\n"
    "/pwd — текущий путь\n\n"
    "<b>Выполнение</b>\n"
    "/exec &lt;команда&gt; — bash в текущем проекте\n"
    "/git &lt;аргументы&gt; — то же что /exec git ...\n\n"
    "<b>Мозги (ключи и модели)</b>\n"
    "/keys — какие API-ключи установлены\n"
    "/setkey &lt;provider&gt; &lt;key&gt; — задать ключ (openrouter, anthropic, openai)\n"
    "/delkey &lt;provider&gt; — удалить ключ\n"
    "/models — список моделей и текущая\n"
    "/setmodel &lt;model&gt; — переключить модель\n\n"
    "<b>Управление</b>\n"
    "/disable, /enable — выключить/включить бот\n"
    "/reset — сбросить контекст разговора\n"
    "/help — это сообщение\n\n"
    "Любое сообщение без / отправляется агенту: он сам читает/правит файлы и запускает команды."
)

# Curated catalogue of models worth pinning. /setmodel accepts any string
# OpenRouter understands; this list is purely for /models output.
MODEL_CATALOGUE: list[tuple[str, str]] = [
    # Free tier (no credit required, rate-limited).
    ("nvidia/nemotron-3-super-120b-a12b:free", "Nemotron 120b — default free"),
    ("openai/gpt-oss-120b:free", "GPT-OSS 120b — free"),
    ("qwen/qwen3-coder:free", "Qwen3 Coder — free"),
    ("minimax/minimax-m2.5:free", "MiniMax 2.5 — free"),
    # Anthropic Claude via OpenRouter (needs OpenRouter credit, ~5% markup).
    ("anthropic/claude-opus-4.5", "Claude Opus 4.5 — strongest, expensive"),
    ("anthropic/claude-sonnet-4.5", "Claude Sonnet 4.5 — balanced"),
    ("anthropic/claude-haiku-4.5", "Claude Haiku 4.5 — fast, cheap"),
    # OpenAI via OpenRouter.
    ("openai/gpt-5", "GPT-5 — strongest OpenAI"),
    ("openai/gpt-4o", "GPT-4o — fast, capable"),
]


def _is_authorized(message: Message) -> bool:
    user = message.from_user
    if user is None:
        return False
    return user.id in ALLOWED_USER_IDS if ALLOWED_USER_IDS else False


async def _deny(message: Message) -> None:
    user = message.from_user
    uid = user.id if user else "unknown"
    await message.answer(
        f"Доступ запрещён.\nТвой telegram id: <code>{uid}</code>\n"
        "Чтобы получить доступ, добавь этот id в <code>ALLOWED_USER_IDS</code> на сервере."
    )


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# Telegram hard limit is 4096 characters per message. We reserve room for the
# `<pre></pre>` wrapper (13 chars) and a small margin for safety.
_TG_LIMIT = 4096
_PRE_OVERHEAD = len("<pre></pre>")
_CHUNK_LIMIT = _TG_LIMIT - _PRE_OVERHEAD - 16


def _safe_cut(escaped: str, limit: int) -> int:
    """Pick a cut position <= ``limit`` that does not split an HTML entity."""
    cut = escaped.rfind("\n", 0, limit)
    if cut < limit // 2:
        cut = escaped.rfind(" ", 0, limit)
    if cut < limit // 2:
        cut = limit
    # HTML entities introduced by `_html_escape` are at most 5 chars (`&amp;`)
    amp = escaped.rfind("&", max(0, cut - 6), cut)
    if amp != -1 and ";" not in escaped[amp:cut]:
        cut = amp
    return max(cut, 1)


async def _send_long(message: Message, text: str) -> None:
    if not text:
        text = "(пусто)"
    escaped = _html_escape(text)
    chunks: list[str] = []
    while len(escaped) > _CHUNK_LIMIT:
        cut = _safe_cut(escaped, _CHUNK_LIMIT)
        chunks.append(escaped[:cut])
        escaped = escaped[cut:]
    chunks.append(escaped)
    for chunk in chunks:
        if not chunk.strip():
            continue
        await message.answer(f"<pre>{chunk}</pre>")


@router.message(Command("start", "help"))
async def cmd_start(message: Message) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    state_label = "" if storage.is_enabled() else "<i>(выключен — /enable чтобы поднять)</i>"
    await message.answer(
        HELP_TEXT.format(model=storage.get_model() or DEFAULT_MODEL, state=state_label)
    )


@router.message(Command("projects"))
async def cmd_projects(message: Message) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    projects = storage.list_projects()
    if not projects:
        await message.answer(
            "Проектов пока нет. Склонируй репо:\n<code>/clone https://github.com/owner/repo</code>"
        )
        return
    cwd = storage.get_cwd(message.from_user.id)
    cwd_name = cwd.relative_to(PROJECTS_DIR).parts[0] if cwd else None
    lines = []
    for name in projects:
        marker = "→ " if name == cwd_name else "  "
        lines.append(f"{marker}{name}")
    await message.answer("<b>Проекты</b>\n<code>" + "\n".join(lines) + "</code>")


@router.message(Command("clone"))
async def cmd_clone(message: Message, command: CommandObject) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    args = (command.args or "").split()
    if not args:
        await message.answer("Использование: <code>/clone &lt;git-url&gt; [имя]</code>")
        return
    url = args[0]
    name = args[1] if len(args) > 1 else None
    await message.answer(f"Клонирую <code>{_html_escape(url)}</code>...")
    try:
        dest = await clone_repo(url, name)
    except ToolError as exc:
        await message.answer(f"Ошибка: {_html_escape(str(exc))}")
        return
    storage.set_cwd(message.from_user.id, dest)
    await message.answer(f"Готово. Проект: <b>{dest.name}</b>\nТекущий cwd: <code>{dest}</code>")


@router.message(Command("project"))
async def cmd_project(message: Message, command: CommandObject) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    name = (command.args or "").strip()
    if not name:
        await message.answer("Использование: <code>/project &lt;имя&gt;</code>")
        return
    target = PROJECTS_DIR / name
    if not target.exists():
        await message.answer(
            f"Проект <code>{_html_escape(name)}</code> не найден. /projects — список."
        )
        return
    storage.set_cwd(message.from_user.id, target)
    await message.answer(f"Переключился на <b>{name}</b>\ncwd: <code>{target}</code>")


@router.message(Command("cd"))
async def cmd_cd(message: Message, command: CommandObject) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    cwd = storage.get_cwd(message.from_user.id)
    if cwd is None:
        await message.answer("Сначала выбери проект: /projects или /clone")
        return
    rel = (command.args or "").strip() or "."
    target = (cwd / rel).resolve()
    project_root = project_root_for(cwd).resolve()
    if project_root not in target.parents and target != project_root:
        await message.answer("Нельзя выйти за пределы проекта")
        return
    if not target.exists() or not target.is_dir():
        await message.answer(f"Не найдена директория: <code>{_html_escape(str(target))}</code>")
        return
    storage.set_cwd(message.from_user.id, target)
    await message.answer(f"cwd: <code>{target}</code>")


@router.message(Command("pwd"))
async def cmd_pwd(message: Message) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    cwd = storage.get_cwd(message.from_user.id)
    if cwd is None:
        await message.answer("Проект не выбран")
        return
    await message.answer(f"<code>{cwd}</code>")


@router.message(Command("exec"))
async def cmd_exec(message: Message, command: CommandObject) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    cmd = (command.args or "").strip()
    if not cmd:
        await message.answer("Использование: <code>/exec &lt;команда&gt;</code>")
        return
    cwd = storage.get_cwd(message.from_user.id)
    if cwd is None:
        await message.answer("Сначала выбери проект: /projects или /clone")
        return
    try:
        result = await exec_bash(cwd, cmd)
    except ToolError as exc:
        await message.answer(f"Ошибка: {_html_escape(str(exc))}")
        return
    await _send_long(message, result)


@router.message(Command("git"))
async def cmd_git(message: Message, command: CommandObject) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    args = (command.args or "").strip()
    if not args:
        await message.answer("Использование: <code>/git &lt;args&gt;</code>")
        return
    cwd = storage.get_cwd(message.from_user.id)
    if cwd is None:
        await message.answer("Сначала выбери проект: /projects или /clone")
        return
    try:
        result = await exec_bash(cwd, f"git {args}")
    except ToolError as exc:
        await message.answer(f"Ошибка: {_html_escape(str(exc))}")
        return
    await _send_long(message, result)


@router.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    storage.clear_history(message.from_user.id)
    await message.answer("Контекст разговора очищен")


# ---- /keys, /setkey, /delkey ---------------------------------------------


@router.message(Command("keys"))
async def cmd_keys(message: Message) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    info = storage.list_provider_keys()
    lines = ["<b>API-ключи</b>"]
    for provider, data in info.items():
        if data["source"] == "none":
            badge = "не задан"
        else:
            badge = f"{data['masked']}  ({data['source']})"
        lines.append(f"  <code>{provider:10}</code> {badge}")
    lines.append("")
    lines.append("<i>source=telegram — поставлен через /setkey, source=env — из переменной окружения</i>")
    await message.answer("\n".join(lines))


@router.message(Command("setkey"))
async def cmd_setkey(message: Message, command: CommandObject) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    args = (command.args or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "Использование: <code>/setkey &lt;provider&gt; &lt;key&gt;</code>\n"
            f"Provider: {', '.join(KNOWN_PROVIDERS)}"
        )
        return
    provider, key = args[0].lower(), args[1].strip()
    # Try to delete the user's message right away — the key was sent in plaintext.
    try:
        await message.delete()
    except Exception:
        # Older bots without delete permissions; fall back to warning.
        pass
    try:
        storage.set_provider_key(provider, key)
    except ValueError as exc:
        await message.answer(f"Ошибка: {_html_escape(str(exc))}")
        return
    masked = storage.list_provider_keys()[provider]["masked"]
    await message.answer(
        f"Ключ <code>{provider}</code> сохранён ({masked}).\n"
        "Сообщение с ключом удалено из чата."
    )


@router.message(Command("delkey"))
async def cmd_delkey(message: Message, command: CommandObject) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    provider = (command.args or "").strip().lower()
    if not provider:
        await message.answer(
            f"Использование: <code>/delkey &lt;provider&gt;</code> ({', '.join(KNOWN_PROVIDERS)})"
        )
        return
    if storage.delete_provider_key(provider):
        await message.answer(f"Ключ <code>{provider}</code> удалён.")
    else:
        await message.answer(
            f"Ключ <code>{provider}</code> не был задан через /setkey "
            "(возможно ещё стоит env-переменная)."
        )


# ---- /models, /setmodel --------------------------------------------------


@router.message(Command("models"))
async def cmd_models(message: Message) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    active = storage.get_model() or DEFAULT_MODEL
    lines = ["<b>Модели</b> (текущая помечена ▶)"]
    for model_id, label in MODEL_CATALOGUE:
        marker = "▶" if model_id == active else "  "
        lines.append(f"{marker} <code>{model_id}</code> — {label}")
    lines.append("")
    lines.append(
        "Переключить: <code>/setmodel &lt;model&gt;</code>\n"
        "Можно указать любую модель OpenRouter — список выше это просто рекомендации."
    )
    await message.answer("\n".join(lines))


@router.message(Command("setmodel"))
async def cmd_setmodel(message: Message, command: CommandObject) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    model = (command.args or "").strip()
    if not model:
        await message.answer(
            "Использование: <code>/setmodel &lt;model&gt;</code>\n"
            "Список вариантов: /models"
        )
        return
    storage.set_model(model)
    await message.answer(
        f"Активная модель: <code>{_html_escape(model)}</code>\n"
        "Применится со следующего сообщения агенту."
    )


# ---- /enable, /disable ----------------------------------------------------


@router.message(Command("enable"))
async def cmd_enable(message: Message) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    storage.set_enabled(True)
    await message.answer("Бот включён. Жду сообщений.")


@router.message(Command("disable"))
async def cmd_disable(message: Message) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    storage.set_enabled(False)
    await message.answer(
        "Бот выключен. Текстовые сообщения и команды кроме /enable, /help, /keys будут игнорироваться."
    )


# ---- text handler ---------------------------------------------------------


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    if not storage.is_enabled():
        await message.answer(
            "Бот выключен. Включи через <code>/enable</code>."
        )
        return
    cwd = storage.get_cwd(message.from_user.id)
    await message.bot.send_chat_action(message.chat.id, "typing")
    try:
        answer = await run_agent(message.from_user.id, message.text or "", cwd)
    except NoApiKeyError as exc:
        await message.answer(str(exc))
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent failed")
        await message.answer(f"Ошибка агента: {_html_escape(str(exc))}")
        return
    await _send_long(message, answer)
