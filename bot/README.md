# codespace bot

Telegram-бот, который принимает сообщения и:
- запускает любые bash-команды в папке выбранного проекта (`/exec`, `/git`),
- подключает LLM-агента (через OpenRouter) к файлам этого проекта — он сам читает, правит, запускает.

Деплой на Render Free (бесплатно, засыпает через 15 мин неактивности).

## Что нужно один раз

- Telegram bot token — `@BotFather` → `/newbot`
- OpenRouter API key — https://openrouter.ai/keys
- Свой Telegram user ID — `@userinfobot` → `/start`

## Деплой на Render (Docker, free plan)

1. **Зайди** на https://dashboard.render.com → `New` → `Blueprint`.
2. Подключи репо `geodze/ai-codesp` → выбери ветку с этим кодом.
3. Render найдёт `bot/render.yaml` и предложит создать сервис `codesp-bot`. Нажми Apply.
4. В разделе `Environment` сервиса выставь значения:
   - `BOT_TOKEN` — токен от @BotFather
   - `OPENROUTER_API_KEY` — ключ OpenRouter
   - `ALLOWED_USER_IDS` — твой Telegram id (только цифры, можно несколько через запятую)
   - `PUBLIC_URL` — публичный URL сервиса, например `https://codesp-bot.onrender.com` (Render показывает его на странице сервиса).
5. Дождись зелёного `Live`. Открой бот в Telegram → `/start`.

> **Внимание:** Render Free засыпает через 15 минут неактивности. Первое сообщение после паузы займёт 30-60 секунд. Файлы (склонированные проекты) при засыпании теряются — после пробуждения нужно делать `/clone` заново. Для постоянной работы — апгрейд до Starter ($7/мес).

## Локальный запуск

```bash
cd bot
cp .env.example .env
# заполни BOT_TOKEN, OPENROUTER_API_KEY, ALLOWED_USER_IDS
pip install -r requirements.txt
python -m bot.main
```

В `.env` оставь `BOT_MODE=polling`. Бот будет опрашивать Telegram сам, без webhook.

## Команды

**Проекты**
- `/help` — список команд
- `/projects` — что загружено
- `/clone <git-url> [имя]` — склонировать репо
- `/project <имя>` — переключиться
- `/cd <subpath>` — субпапка внутри проекта
- `/pwd` — текущий путь

**Выполнение**
- `/exec <команда>` — bash в проекте (timeout 30s)
- `/git <args>` — короткая запись для `/exec git ...`

**Мозги (ключи и модели)**
- `/keys` — список провайдеров и статус их API-ключей (значения замаскированы)
- `/setkey <provider> <key>` — задать ключ. Provider: `openrouter`, `anthropic`, `openai`. Сообщение с ключом бот удалит автоматически.
- `/delkey <provider>` — удалить сохранённый ключ
- `/models` — список моделей и текущая
- `/setmodel <model>` — переключить модель. Например `anthropic/claude-opus-4.5` или `nvidia/nemotron-3-super-120b-a12b:free`.

**Управление**
- `/disable`, `/enable` — выключить/включить бот (в disabled режиме работает только `/enable`, `/help`, `/keys`)
- `/reset` — сброс контекста разговора

Любое сообщение **без** `/` — запрос агенту. Он сам решит, какие файлы прочитать, что выполнить, и ответит.

## Как это работает

1. Бот хранит для каждого пользователя текущий `cwd` и историю последних N сообщений.
2. На обычное сообщение бот отправляет историю + новый запрос в OpenRouter с tool definitions (`list_dir`, `read_file`, `write_file`, `exec_bash`).
3. Если модель возвращает `tool_calls` — бот выполняет их в `cwd`, передаёт результаты обратно. Цикл, пока модель не вернёт финальный текст или не упрётся в `AGENT_MAX_STEPS`.
4. Если выбранная модель упала (rate limit, недоступна) — бот пробует `FALLBACK_MODELS` по очереди.

## Безопасность

- Все сообщения проходят whitelist по `ALLOWED_USER_IDS`. Без этого бот никого не пускает.
- `exec_bash` запускается с CWD = выбранный проект, **без sudo**, с 30-секундным таймаутом, но в остальном это полноценная shell. Не давай доступ к боту чужим людям.
- Render Free disk эфемерный → секреты в файлах не персистятся; используй ENV vars Render для всего что секретно.

## Стек

- Python 3.12 + aiogram 3 (Telegram)
- aiohttp (webhook server)
- openai (для OpenRouter, через `base_url`)

## Модели

Бот ходит в OpenRouter — один API-ключ покрывает все модели (Anthropic Claude, OpenAI GPT, free-tier и т.д.).

По умолчанию: `nvidia/nemotron-3-super-120b-a12b:free` (free-tier с tool calling).

Рекомендуемые варианты (`/models` в боте покажет их все):
- `anthropic/claude-opus-4.5` — самый сильный, требует OpenRouter credit
- `anthropic/claude-sonnet-4.5` — баланс цена/качество
- `openai/gpt-5`, `openai/gpt-4o` — OpenAI через OpenRouter
- `openai/gpt-oss-120b:free`, `qwen/qwen3-coder:free` — free-tier

Когда активная модель — free, бот автоматически fall-back-ит на другие free-модели при rate-limit. Для paid-моделей (Opus, Sonnet, GPT-4) fallback не срабатывает — чтобы не было скрытого довнгрейда. Если Opus упал — бот покажет ошибку.

## API-ключи

Два варианта как бот берёт ключ OpenRouter:

1. **Через Telegram** (`/setkey openrouter sk-or-...`) — приоритетный источник. Сообщение с ключом бот удалит из чата. Ключ сохраняется в `data/state.json` (chmod 600), переживает рестарты.
2. **Через env** (`OPENROUTER_API_KEY=...`) — fallback. Используется если в Telegram ничего не задано.

`/keys` показать что сейчас активно и откуда. Значения всегда маскируются (`sk-or-***af04`).

Получить ключ: https://openrouter.ai/keys (минимум $5 на счёт для Anthropic/OpenAI моделей, free-модели бесплатно).
