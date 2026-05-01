import { convertToModelMessages, streamText, type UIMessage, type ModelMessage } from "ai"
import { getAvailableCandidates, type ModelCandidate } from "@/lib/ai-providers"

export const maxDuration = 60

const SYSTEM_PROMPT = `Вы — AI Codespace, ИИ-ассистент в облачной среде разработки в стиле GitHub Codespaces. Вы работаете как Claude Code: помогаете пользователю писать код, объясняете команды, управляете терминалом и встроенным браузером.

Принципы работы:
- Отвечайте на языке пользователя (по умолчанию — русский).
- Будьте кратки и техничны: минимум воды, максимум практической пользы.
- Когда предлагаете команду для терминала — оформляйте её в блок \`\`\`bash.
- Когда предлагаете URL — оформляйте кликабельной ссылкой в markdown.
- Если задачу можно разбить на шаги — давайте нумерованный список.
- Если запрос рискованный (rm -rf, удаление БД, секреты в логах) — предупредите пользователя.

Текущее окружение: Linux (Ubuntu) + Node.js + Python + headless браузер (Playwright). Терминал и панель браузера работают рядом — вы можете предложить пользователю команду или URL, и они сразу выполнят их в соответствующей панели.`

/**
 * Пробует модели по очереди. Для каждой модели:
 *   1. Создаём streamText
 *   2. «Прогреваем» поток — читаем первый chunk через fullStream
 *      Если первый chunk = error → пробуем следующую модель
 *      Если первый chunk = текст/начало → повторяем streamText (новый поток)
 *      и сразу возвращаем его клиенту
 *
 * Стоимость: 1 лишний токен на успешной модели (1-й chunk),
 * но это намного безопаснее, чем терять отвечающие модели.
 *
 * НА САМОМ ДЕЛЕ — ещё проще: пробуем каждую модель сразу, без двойного streamText.
 * Если streamText бросает синхронную ошибку при создании — идём дальше.
 * Если ошибка в середине стрима — она уйдёт клиенту через onError.
 */
async function streamWithFallback(
  candidates: ModelCandidate[],
  modelMessages: ModelMessage[],
) {
  const failures: { id: string; label: string; reason: string }[] = []

  for (let i = 0; i < candidates.length; i++) {
    const candidate = candidates[i]
    const isLast = i === candidates.length - 1

    try {
      console.log(`[v0] trying model: ${candidate.label}`)
      const model = candidate.build()

      const result = streamText({
        model,
        system: SYSTEM_PROMPT,
        messages: modelMessages,
        onError: ({ error }) => {
          console.error(`[v0] streamText error on ${candidate.label}:`, error)
        },
      })

      // Ждём первого чанка, чтобы поймать ранние ошибки (404, 401, 429 на создание соединения).
      // Если первый чанк — error и есть ещё кандидаты, переходим к следующему.
      const reader = result.fullStream.getReader()
      const first = await reader.read()

      if (first.value?.type === "error") {
        reader.releaseLock()
        const err = (first.value as { error: unknown }).error
        const reason = err instanceof Error ? err.message : String(err)
        failures.push({ id: candidate.id, label: candidate.label, reason })
        console.log(`[v0] ${candidate.label} returned error chunk: ${reason}`)
        if (!isLast) continue
      }

      reader.releaseLock()

      // Поток живой — отдаём клиенту. Это создаст НОВЫЙ streamText,
      // потому что первый поток уже частично прочитан.
      // Это означает один лишний запрос, но он гарантирует целостность UI-стрима.
      const finalResult = streamText({
        model,
        system: SYSTEM_PROMPT,
        messages: modelMessages,
        onError: ({ error }) => {
          console.error(`[v0] streamText final error on ${candidate.label}:`, error)
        },
      })

      return finalResult.toUIMessageStreamResponse({
        messageMetadata: () => ({
          modelId: candidate.id,
          modelLabel: candidate.label,
          provider: candidate.provider,
          fallbackCount: failures.length,
          failures,
        }),
      })
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error)
      console.error(`[v0] ${candidate.label} threw:`, reason)
      failures.push({ id: candidate.id, label: candidate.label, reason })
      if (isLast) throw error
    }
  }

  throw new Error("Все модели в цепочке недоступны")
}

export async function POST(req: Request) {
  const { messages }: { messages: UIMessage[] } = await req.json()

  const candidates = getAvailableCandidates()

  if (candidates.length === 0) {
    return new Response(
      JSON.stringify({
        error:
          "Не настроено ни одного провайдера. Установите хотя бы один из ключей: AI_GATEWAY_API_KEY, ANTHROPIC_API_KEY или OPENROUTER_API_KEY.",
      }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    )
  }

  console.log(`[v0] available models: ${candidates.map((c) => c.label).join(" -> ")}`)

  const modelMessages = await convertToModelMessages(messages)

  try {
    return await streamWithFallback(candidates, modelMessages)
  } catch (error) {
    console.error("[v0] all models failed:", error)
    return new Response(
      JSON.stringify({
        error: error instanceof Error ? error.message : "Все модели недоступны",
      }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    )
  }
}
