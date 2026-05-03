import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from .agent import run_agent
from .config import ALLOWED_USER_IDS, MODEL, PROJECTS_DIR
from .storage import storage
from .tools import ToolError, clone_repo, exec_bash, project_root_for

logger = logging.getLogger(__name__)
router = Router()


HELP_TEXT = (
    "<b>codespace bot</b>\n"
    "Подключён к OpenRouter, модель: <code>{model}</code>\n\n"
    "<b>Команды</b>\n"
    "/projects — список загруженных проектов\n"
    "/clone &lt;git-url&gt; [имя] — клонировать репо\n"
    "/project &lt;имя&gt; — переключиться на проект\n"
    "/cd &lt;путь&gt; — сменить субпапку внутри проекта\n"
    "/pwd — текущий путь\n"
    "/exec &lt;команда&gt; — bash в текущем проекте\n"
    "/git &lt;аргументы&gt; — то же что /exec git ...\n"
    "/reset — сбросить контекст разговора\n"
    "/help — это сообщение\n\n"
    "Любое сообщение без / отправляется агенту: он сам читает/правит файлы и запускает команды."
)


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
    await message.answer(HELP_TEXT.format(model=MODEL))


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


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message) -> None:
    if not _is_authorized(message):
        await _deny(message)
        return
    cwd = storage.get_cwd(message.from_user.id)
    await message.bot.send_chat_action(message.chat.id, "typing")
    try:
        answer = await run_agent(message.from_user.id, message.text or "", cwd)
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent failed")
        await message.answer(f"Ошибка агента: {_html_escape(str(exc))}")
        return
    await _send_long(message, answer)
