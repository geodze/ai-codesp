# Деплой на Railway

## Что вам нужно

1. Аккаунт на [GitHub](https://github.com)
2. Аккаунт на [Railway](https://railway.com) (вход через GitHub)
3. **Минимум один** из этих API-ключей:
   - `AI_GATEWAY_API_KEY` — Vercel AI Gateway ([получить](https://vercel.com/dashboard) → AI Gateway → API Keys)
   - `ANTHROPIC_API_KEY` — прямой ключ Anthropic ([получить](https://console.anthropic.com))
4. **Опционально** (но желательно для бесплатного фоллбэка):
   - `OPENROUTER_API_KEY` — [получить бесплатно](https://openrouter.ai/keys)

## Шаги деплоя

### 1. Залить код в GitHub

В v0 справа сверху нажмите **три точки → Push to GitHub** (или скачайте ZIP и сделайте `git push` руками).

### 2. Создать проект в Railway

1. Откройте https://railway.com/new
2. **Deploy from GitHub repo** → выберите ваш репозиторий
3. Railway автоматически найдёт `Dockerfile` и начнёт сборку

### 3. Добавить переменные окружения

В Railway откройте сервис → вкладка **Variables** → добавьте:

```
ANTHROPIC_API_KEY=sk-ant-xxxxx
OPENROUTER_API_KEY=sk-or-v1-xxxxx
```

(или `AI_GATEWAY_API_KEY` вместо `ANTHROPIC_API_KEY`)

### 4. Сгенерировать публичный домен

Сервис → **Settings** → **Networking** → **Generate Domain**.

Через минуту получите URL вида `your-app.up.railway.app`.

## Деплой на другие платформы

### Render

1. https://dashboard.render.com → **New** → **Web Service**
2. Подключите GitHub репо
3. **Runtime** → **Docker**
4. Добавьте те же env vars

### Fly.io

```bash
fly launch              # создаст fly.toml
fly secrets set ANTHROPIC_API_KEY=...
fly secrets set OPENROUTER_API_KEY=...
fly deploy
```

### Vercel (самый простой)

1. https://vercel.com/new → импортируйте GitHub репо
2. `AI_GATEWAY_API_KEY` подключится **автоматически**
3. Добавьте только `OPENROUTER_API_KEY`

> Примечание: Если в будущем добавите Playwright (управление браузером) или persistent shell — Vercel не подойдёт (serverless). Для этого нужны Railway / Render / Fly.io.

## Локальный запуск

```bash
pnpm install
cp .env.example .env.local   # заполните ключи
pnpm dev
```
