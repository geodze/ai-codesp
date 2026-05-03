# AI Codespace + Telegram Bot — Quickstart

Этот репо содержит несколько вещей в одном пакете:

1. **AI Codespace** (Next.js 16 / React 19) — корень репо. Веб-IDE из исходного развёртывания.
2. **`bot/`** — Telegram-бот, через который ты управляешь проектами текстом из Telegram.
3. **`.devcontainer/`** — автоматическая настройка GitHub Codespaces: ставит `opencode` CLI и зависимости.
4. **`opencode.json`** — конфиг для `opencode` CLI с подключённым плагином [obra/superpowers](https://github.com/obra/superpowers) (агентская методология "сначала план, потом код").

## Структура

```
.
├── app/, components/, lib/    # Next.js приложение AI Codespace
├── bot/                       # Telegram-бот (Python 3.12)
│   ├── main.py                # Entry-point: aiogram polling/webhook
│   ├── handlers.py            # Slash-команды (/clone, /exec, /git, ...)
│   ├── agent.py               # LLM-агент (любое сообщение без слэша)
│   ├── tools.py               # 4 tool-функции для агента
│   ├── storage.py             # Persistence (state.json)
│   ├── config.py              # Чтение env vars
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── render.yaml            # Render Blueprint
│   ├── .env.example
│   └── README.md
├── .devcontainer/             # Авто-настройка GitHub Codespaces
│   ├── devcontainer.json
│   └── post-create.sh         # Ставит opencode + pnpm install + bot venv
├── opencode.json              # Конфиг opencode + Superpowers plugin
└── QUICKSTART.md              # Этот файл
```

## Открыть в GitHub Codespaces (рекомендуемый путь)

1. Залить этот репо в свой GitHub.
2. Открыть https://github.com/codespaces → New codespace → выбрать репо.
3. Дождаться post-create (первый раз ~2-3 минуты): ставится `opencode` CLI, pnpm install, bot venv.
4. Когда терминал готов, запустить:

```bash
opencode
```

При первом запуске opencode скачает плагин Superpowers (`obra/superpowers`).
Чтобы проверить:

```
> Tell me about your superpowers
```

Должен выдать список из 14 skills (brainstorming, test-driven-development, writing-plans и т.д.). Это означает что плагин загрузился.

## Что такое Superpowers

Подключённый плагин [obra/superpowers](https://github.com/obra/superpowers) (177K звёзд, MIT) — это набор **skills**, которые автоматически срабатывают в нужный момент:

- **brainstorming** — перед любой задачей агент сначала уточняет что ты хочешь, прежде чем писать код.
- **writing-plans** — разбивает работу на маленькие задачи с чёткой целью.
- **test-driven-development** — навязывает RED-GREEN-REFACTOR цикл.
- **systematic-debugging** — методология отладки от симптома к корню.
- **using-git-worktrees** — изоляция рабочего пространства в worktree.
- **subagent-driven-development** — параллельные субагенты для длинных задач.
- ещё 8 skills.

Skills работают **автоматически** — не нужно каждый раз говорить "используй такой-то skill".

⚠️ Skills тестировались на полноценных Claude / GPT / Gemini моделях. На бесплатных моделях OpenRouter (Nemotron, Qwen) они работают, но эффект слабее — модели проще, инструкциям следуют менее строго.

## Запустить бота локально (без Codespace, на любой машине с Python 3.12)

```bash
cd bot
cp .env.example .env
# Заполни в .env:
#   BOT_TOKEN — от @BotFather
#   OPENROUTER_API_KEY — с https://openrouter.ai/keys
#   ALLOWED_USER_IDS — твой Telegram ID (через @userinfobot)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m bot.main
```

Бот запустится в polling-режиме.

## Деплой бота на Render Free (постоянно работающий бот)

1. Залить этот репо в свой GitHub.
2. На https://dashboard.render.com → New → Blueprint → выбрать репо.
3. Render найдёт `bot/render.yaml` и создаст сервис `codesp-bot`.
4. Заполнить env vars: `BOT_TOKEN`, `OPENROUTER_API_KEY`, `ALLOWED_USER_IDS`, `PUBLIC_URL`.
5. Дождаться `Live` (~3-5 минут).

Подробнее в `bot/README.md`.

## Команды Telegram-бота

| Команда | Что делает |
|---|---|
| `/start`, `/help` | Список команд |
| `/clone <git-url>` | Склонировать репо |
| `/projects`, `/project <name>`, `/cd <dir>` | Навигация по проектам |
| `/exec <cmd>`, `/git <args>` | Bash в проекте |
| `/reset` | Сбросить контекст агента |
| _обычный текст_ | LLM-агент сам читает / пишет / выполняет команды |

## Что внутри `bot/agent.py`

Через OpenAI SDK ходит в OpenRouter (`base_url=https://openrouter.ai/api/v1`).
Default model: `nvidia/nemotron-3-super-120b-a12b:free`.
При rate-limit — fallback на `gpt-oss-120b:free`, `qwen3-coder:free`, `minimax-m2.5:free`. Все free.

## Безопасность

- Whitelist через `ALLOWED_USER_IDS` (CSV Telegram user IDs). Без неё бот никого не впускает.
- Tool-функции `read_file/write_file/list_dir` блокируют выход за пределы проекта.
- `exec_bash` без sandbox, но cwd ограничен папкой проекта.
