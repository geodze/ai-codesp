# Multi-stage Dockerfile for Next.js на Railway
# Использует standalone output для минимального финального образа

# ---------- 1. Установка зависимостей ----------
FROM node:20-alpine AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

# Копируем lock-файлы и package.json
COPY package.json pnpm-lock.yaml* ./
RUN corepack enable pnpm && pnpm install --frozen-lockfile

# ---------- 2. Сборка приложения ----------
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
RUN corepack enable pnpm && pnpm run build

# ---------- 3. Финальный production образ ----------
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Создаём пользователя без root-прав
RUN addgroup --system --gid 1001 nodejs \
  && adduser --system --uid 1001 nextjs

# Копируем только нужные артефакты сборки
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

# Railway передаёт PORT через env, слушаем его
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
EXPOSE 3000

CMD ["node", "server.js"]
