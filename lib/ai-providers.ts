import { createOpenAICompatible } from "@ai-sdk/openai-compatible"
import { createAnthropic } from "@ai-sdk/anthropic"
import type { LanguageModel } from "ai"

/**
 * OpenRouter — для бесплатных моделей-фоллбэков.
 * Документация: https://openrouter.ai/docs
 *
 * baseURL: https://openrouter.ai/api/v1 (без /chat/completions — AI SDK добавит сам)
 */
const openrouter = createOpenAICompatible({
  name: "openrouter",
  apiKey: process.env.OPENROUTER_API_KEY ?? "",
  baseURL: "https://openrouter.ai/api/v1",
  headers: {
    // OpenRouter рекомендует указывать эти заголовки для рейтинга/аналитики
    "HTTP-Referer": process.env.PUBLIC_APP_URL ?? "https://ai-codespace.local",
    "X-Title": "AI Codespace",
  },
})

/**
 * Anthropic напрямую (если у пользователя есть ANTHROPIC_API_KEY).
 * Если ключа нет — будет использоваться AI Gateway (model id строкой).
 */
const anthropicDirect = process.env.ANTHROPIC_API_KEY
  ? createAnthropic({ apiKey: process.env.ANTHROPIC_API_KEY })
  : null

export type ModelCandidate = {
  id: string
  label: string
  provider: "claude-gateway" | "claude-direct" | "openrouter-free"
  build: () => LanguageModel | string
}

/**
 * Цепочка моделей. Порядок:
 *  1. Claude (через Anthropic API напрямую, если есть ключ)
 *  2. Claude (через Vercel AI Gateway — AI_GATEWAY_API_KEY)
 *  3. Бесплатные модели OpenRouter (по очереди)
 *
 * При сбое одной — автоматически пробуется следующая.
 */
export const MODEL_CHAIN: ModelCandidate[] = [
  // --- Основные: Claude ---
  ...(anthropicDirect
    ? [
        {
          id: "anthropic-direct/claude-sonnet-4-5",
          label: "Claude Sonnet 4.5 (Anthropic API)",
          provider: "claude-direct" as const,
          build: () => anthropicDirect("claude-sonnet-4-5"),
        },
      ]
    : []),
  {
    id: "gateway/anthropic/claude-opus-4.6",
    label: "Claude Opus 4.6 (AI Gateway)",
    provider: "claude-gateway",
    build: () => "anthropic/claude-opus-4.6",
  },
  {
    id: "gateway/anthropic/claude-sonnet-4.5",
    label: "Claude Sonnet 4.5 (AI Gateway)",
    provider: "claude-gateway",
    build: () => "anthropic/claude-sonnet-4.5",
  },

  // --- Бесплатные фоллбэки через OpenRouter ---
  {
    id: "openrouter:nvidia/nemotron-3-super-120b-a12b:free",
    label: "Nemotron 3 Super 120B (OpenRouter Free)",
    provider: "openrouter-free",
    build: () => openrouter("nvidia/nemotron-3-super-120b-a12b:free"),
  },
  {
    id: "openrouter:meta-llama/llama-3.3-70b-instruct:free",
    label: "Llama 3.3 70B (OpenRouter Free)",
    provider: "openrouter-free",
    build: () => openrouter("meta-llama/llama-3.3-70b-instruct:free"),
  },
  {
    id: "openrouter:google/gemini-2.0-flash-exp:free",
    label: "Gemini 2.0 Flash (OpenRouter Free)",
    provider: "openrouter-free",
    build: () => openrouter("google/gemini-2.0-flash-exp:free"),
  },
  {
    id: "openrouter:deepseek/deepseek-chat-v3.1:free",
    label: "DeepSeek V3.1 (OpenRouter Free)",
    provider: "openrouter-free",
    build: () => openrouter("deepseek/deepseek-chat-v3.1:free"),
  },
]

/**
 * Возвращает доступных кандидатов с учётом установленных env-ключей.
 * Кандидат недоступен заранее, если у него нет соответствующего ключа.
 */
export function getAvailableCandidates(): ModelCandidate[] {
  const hasGateway = !!process.env.AI_GATEWAY_API_KEY || !!process.env.VERCEL
  const hasOpenRouter = !!process.env.OPENROUTER_API_KEY
  const hasAnthropic = !!process.env.ANTHROPIC_API_KEY

  return MODEL_CHAIN.filter((c) => {
    if (c.provider === "claude-direct") return hasAnthropic
    if (c.provider === "claude-gateway") return hasGateway
    if (c.provider === "openrouter-free") return hasOpenRouter
    return false
  })
}

/**
 * Утилита для классификации ошибок: какие можно «фоллбэкать», а какие — нет.
 * Rate limit / network / 5xx / no_credits → пробуем следующую модель.
 * Auth/permission → лучше сразу остановиться на этом провайдере, но всё равно идём дальше.
 */
export function isRetryableError(error: unknown): boolean {
  const msg = error instanceof Error ? error.message.toLowerCase() : String(error).toLowerCase()
  return (
    msg.includes("rate") ||
    msg.includes("limit") ||
    msg.includes("quota") ||
    msg.includes("credit") ||
    msg.includes("overload") ||
    msg.includes("timeout") ||
    msg.includes("network") ||
    msg.includes("5") || // 5xx-ошибки
    msg.includes("unauthorized") ||
    msg.includes("forbidden") ||
    msg.includes("404") ||
    msg.includes("not found")
  )
}
