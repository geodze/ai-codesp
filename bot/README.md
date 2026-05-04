# codespace bot

Telegram-бот, который принимает сообщения и:
- запускает любые bash-команды в папке выбранного проекта (`/exec`, `/git`),
- подключает LLM-агента (через OpenRouter, любой OpenAI-совместимый endpoint, или ручную Devin-сессию) к файлам этого проекта — он сам читает, правит, запускает.

**Контейнер deploy-once-anywhere:** один env-var (`BOT_TOKEN`) → выкатить на любой облак → всё остальное настраивается из самого Telegram через кнопки. Подробный гайд по деплою на Render / Railway / Fly.io / Heroku / VPS — в [`bot/DEPLOY.md`](./DEPLOY.md).

## Quickstart за 3 минуты

1. **Создай бота**: `@BotFather` → `/newbot` → скопируй токен.
2. **Деплой контейнера** (выбери одно):
   - `git clone https://github.com/geodze/ai-codesp && cd ai-codesp && docker build -f bot/Dockerfile -t codesp-bot . && docker run -e BOT_TOKEN=... codesp-bot`
   - Или один из cloud-вариантов в [`bot/DEPLOY.md`](./DEPLOY.md).
3. **Открой бота в Telegram** → `/start` → нажми кнопку *«Запустить и стать владельцем»*.
4. Выбери мозг (`OpenRouter` / `Devin.ai` / `Другое`), вводи API/Model/URL по кнопкам.

После этого бот твой — никто кроме тебя писать ему не сможет.

## Локальный запуск

```bash
cd bot
cp .env.example .env
# заполни только BOT_TOKEN
pip install -r requirements.txt
python -m bot.main
```

В `.env` оставь `BOT_MODE=polling`. Бот будет опрашивать Telegram сам, без webhook. Дальше настройка идёт из чата — `/start`.

## Команды

**Старт / настройка**
- `/start` — онбординг (нажми кнопку, чтобы стать владельцем)
- `/setup` — заново выбрать мозг и ввести ключи через кнопки
- `/help` — список команд

**Проекты**
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

- Авторизация — owner-claim: первый, кто после старта контейнера нажмёт `/start` → *«Запустить и стать владельцем»*, становится единственным юзером, кто может писать. Записывается в `data/state.json` поле `_settings.owner_id`. Чтобы перепривязать — удалить это поле и перезапустить.
- Старая схема через env-var `ALLOWED_USER_IDS` тоже работает как fallback (если owner ещё не назначен) — для совместимости с уже работающими установками.
- `exec_bash` запускается с CWD = выбранный проект, **без sudo**, с 30-секундным таймаутом, но в остальном это полноценная shell. Не давай доступ к боту чужим людям.
- Эфемерный disk (Render Free, Heroku и т.п.) → state.json сбрасывается при рестарте, и owner придётся назначить заново. Для сохранения настроек используй платформу с persistent volume (Fly.io, Railway, VPS) или подключи внешний Redis/Postgres.

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
