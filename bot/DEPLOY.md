# Bot deploy guide

The bot is **deploy-once-anywhere**: push the repo to any cloud that runs a
long-lived Python/Docker process, set a single env var (`BOT_TOKEN`), and the
rest of the configuration happens **inside Telegram** via the onboarding
wizard.

```
┌──────────────────────┐         ┌───────────────────────────┐
│  cloud (Render/etc)  │  ←--→   │  Telegram chat with you   │
│  bot container       │         │                           │
│  - reads BOT_TOKEN   │         │  /start  → claim owner    │
│  - persists state    │         │  pick brain → buttons     │
│    in DATA_DIR       │         │  set API/model/URL inline │
└──────────────────────┘         └───────────────────────────┘
```

After a fresh deploy the bot will message-back: *"this container has no
owner — tap the button to claim"*. The first user who taps it is locked in
as the only person who can use the bot. All later config (API key, model,
custom endpoint) goes through inline buttons — **no redeploys needed**.

> This guide is for the Python Telegram bot in `bot/`. For deploying the
> Next.js prototype in `app/` to Railway see `DEPLOY.md` at the repo root.

---

## Which cloud should I pick?

| Cloud | Free tier | Persistent disk | Setup time | Best for |
|---|---|---|---|---|
| **Render** | yes (sleeps after 15 min idle) | no on free | 5 min | quick demos |
| **Railway** | $5 trial credit | yes | 3 min | smooth UX |
| **Fly.io** | yes (3 small machines) | yes (volumes) | 10 min | always-on, EU/Russia regions |
| **Heroku** | paid only ($5/mo eco) | no | 10 min | container-registry workflow |
| **Self-hosted VPS** | depends | yes | 5 min | full control, lowest cost long-term |

**Picking advice:**
- *"Just want to try"* → **Render** or **Railway**
- *"Always-on, low ping from Russia"* → **Fly.io** (use `fra` region)
- *"Already pay for a VPS (Selectel, Timeweb, Hetzner)"* → run the Docker image directly, see [VPS](#vps-selectel--timeweb--hetzner-etc) at the bottom
- *"Don't trust clouds"* → run the container on a Raspberry Pi behind your home router; works the same

> ⚠️ **Don't use Vercel / Netlify / Cloudflare Pages** — they only run
> serverless functions ≤10s, which can't hold a Telegram polling
> connection. Same goes for GitHub Actions / CircleCI: those are CI
> systems, not runtime hosts.

---

## Render

The repo contains a Render-ready service definition at `bot/render.yaml`.
Because the repo also has a Next.js prototype at the root, you have to
point Render at the bot's config explicitly.

1. Sign in to <https://dashboard.render.com/> with GitHub.
2. **New +** → **Web Service** → connect this repo (or a fork).
3. Configure manually:
   - **Runtime**: `Docker`
   - **Dockerfile path**: `bot/Dockerfile`
   - **Docker Build Context**: `.` (the repo root — Dockerfile does
     `COPY bot/requirements.txt`)
   - **Health Check Path**: `/healthz`
4. **Environment** tab → add `BOT_TOKEN` (from `@BotFather`). Optionally
   add `BOT_MODE=polling` and `DATA_DIR=/tmp/bot-data` to be explicit.
5. **Create Web Service**.

Wait ~3 min for the build to finish. Then open Telegram, find your bot, and
send `/start`. You'll see the *"Запустить и стать владельцем"* button.

**Going to webhook mode (optional, faster on Render Pro):**
- Once the service is live, copy its URL (e.g. `https://codesp-bot.onrender.com`)
- In the Render dashboard set `PUBLIC_URL` to that URL and `BOT_MODE` to
  `webhook`. Restart. The bot will register a webhook automatically.

> Render's free plan spins down after 15 min of inactivity. The bot's
> built-in `/healthz` endpoint plus polling means the service stays alive
> while Render hits it, but cold-start *after* a manual spin-down is ~30s.
> For 24/7 reliability upgrade to a paid plan or use Fly.io.

---

## Railway

> The root `railway.json` belongs to the Next.js prototype. The bot has
> its own at `bot/railway.json` — point Railway at the bot's directory
> when creating the service.

1. <https://railway.app/new> → **Deploy from GitHub repo** → pick your fork.
2. **Settings** → **Source** → set **Root Directory** to `bot/`. Railway
   will now read `bot/railway.json` and build via `bot/Dockerfile` with
   build context = `bot/`. The Dockerfile is written to handle either
   context, so this works as-is.
3. Open the service → **Variables** → add `BOT_TOKEN`.
4. (Optional) **Settings** → **Generate Domain** to get a public URL, then
   add `PUBLIC_URL=https://<that-url>` and `BOT_MODE=webhook` for slightly
   faster delivery.

Railway's `$5/month` trial credit covers the bot for ~2 weeks at idle load.
After that, ~$3-7/mo for an always-on service.

---

## Fly.io

```bash
# 1. install flyctl
curl -L https://fly.io/install.sh | sh

# 2. log in
fly auth login

# 3. from the repo root:
fly launch --no-deploy --copy-config --name <your-unique-app-name>
#    edit the generated fly.toml so `app = "<your-name>"`

# 4. create the persistent volume (state.json + cloned repos go here)
fly volumes create bot_data --region fra --size 1

# 5. set the only required secret
fly secrets set BOT_TOKEN=123456789:AAEx...

# 6. deploy
fly deploy
```

Fly's free tier covers 3 small machines + 3 GB persistent storage —
enough for the bot indefinitely. Frankfurt (`fra`) gives ~30 ms ping from
Moscow / SPb.

---

## Heroku

The bot ships only the `bot/Dockerfile` (no `heroku.yml` or `Procfile` at
the repo root, to avoid clashing with the Next.js prototype). Use the
container registry workflow instead:

```bash
# 1. log in
heroku login
heroku container:login

# 2. create the app
heroku create <app-name>
heroku stack:set container -a <app-name>

# 3. set the only required secret
heroku config:set BOT_TOKEN=123456789:AAEx... -a <app-name>

# 4. push the bot's container image
docker build -f bot/Dockerfile -t registry.heroku.com/<app-name>/web .
docker push registry.heroku.com/<app-name>/web

# 5. release
heroku container:release web -a <app-name>
```

The Eco plan (`$5/mo`, 1000 dyno hours) keeps the bot up 24/7.

---

## VPS (Selectel / Timeweb / Hetzner / etc.)

If you already have a VPS, you don't need any of the cloud configs above —
just run the Docker image:

```bash
git clone https://github.com/geodze/ai-codesp.git
cd ai-codesp

# build
docker build -f bot/Dockerfile -t codesp-bot .

# run (./data is bind-mounted so state survives container restarts)
mkdir -p ./data
docker run -d \
  --name codesp-bot \
  -p 8080:8080 \
  -e BOT_TOKEN="123456789:AAEx..." \
  -e DATA_DIR=/data \
  -v "$PWD/data:/data" \
  --restart unless-stopped \
  codesp-bot
```

For systemd-managed long-running deployment without Docker, see the
*Локальный запуск* section in `bot/README.md`.

---

## After deploy: claim the bot

1. Open Telegram, find your bot by the username you gave `@BotFather`.
2. Send `/start`. You'll see one button — **🚀 Запустить и стать владельцем**.
3. Tap it. From now on only your Telegram account talks to this bot.
4. Pick a brain:
   - **OpenRouter** (recommended) — paste an API key from
     <https://openrouter.ai/keys>, optionally pick a model.
   - **Devin.ai** — switches the bot to log-only mode; you give a Devin
     session SSH access to the machine and Devin replies via the
     `python -m bot.send` CLI. The bot prints the exact handoff prompt to
     paste into a fresh Devin chat.
   - **Другое** — any OpenAI-compatible endpoint (Together, Groq, vLLM,
     local Ollama). Three buttons let you set API key, model, and URL one
     by one.

To re-run the wizard at any time: `/setup`.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `BOT_TOKEN` env var is missing | The container crash-loops on startup with `KeyError: 'BOT_TOKEN'`. Set `BOT_TOKEN` in the cloud's env config. |
| `TelegramUnauthorizedError: Unauthorized` | The token is invalid (typo, revoked, or wrong bot). Get a fresh one with `/revoke` + `/token` in `@BotFather` and update the env. |
| Bot says "уже привязан к другому владельцу" | Someone else clicked the claim button first (or you have residual `data/state.json`). To reset: delete the `_settings.owner_id` field from `state.json` and restart. |
| Wizard buttons don't respond | Check that the bot's privacy mode is **disabled** in `@BotFather` (`/setprivacy` → Disable) so it can read its own callback queries inside groups; in 1:1 chat it always works. |
| `/exec git ...` fails with "no project selected" | First `/clone <repo-url>` to clone something, or `/project <name>` to switch to an already-cloned one. |
