"use client"

import { useEffect, useRef, useState } from "react"
import { useChat } from "@ai-sdk/react"
import { DefaultChatTransport, type UIMessage } from "ai"
import { Bot, Send, Sparkles, User } from "lucide-react"
import { Button } from "@/components/ui/button"

type ChatMetadata = {
  modelId?: string
  modelLabel?: string
  provider?: "anthropic" | "openrouter-free"
  fallbackCount?: number
}

type ChatPanelProps = {
  onModelChange: (info: { label: string | null; provider: string | null; fallbackCount: number }) => void
}

function getMessageText(message: UIMessage): string {
  if (!message.parts) return ""
  return message.parts
    .filter((p): p is { type: "text"; text: string } => p.type === "text")
    .map((p) => p.text)
    .join("")
}

export function ChatPanel({ onModelChange }: ChatPanelProps) {
  const [input, setInput] = useState("")
  const scrollRef = useRef<HTMLDivElement>(null)

  const { messages, sendMessage, status, error } = useChat<UIMessage>({
    transport: new DefaultChatTransport({ api: "/api/chat" }),
  })

  // Reflect last assistant message metadata to header
  useEffect(() => {
    const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant")
    const meta = lastAssistant?.metadata as ChatMetadata | undefined
    if (meta?.modelLabel) {
      onModelChange({
        label: meta.modelLabel,
        provider: meta.provider ?? null,
        fallbackCount: meta.fallbackCount ?? 0,
      })
    }
  }, [messages, onModelChange])

  // Auto-scroll
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    })
  }, [messages, status])

  const isStreaming = status === "streaming" || status === "submitted"

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = input.trim()
    if (!trimmed || isStreaming) return
    sendMessage({ text: trimmed })
    setInput("")
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex h-9 shrink-0 items-center gap-2 border-b border-border bg-card px-3">
        <Sparkles className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          AI Ассистент
        </span>
        <span className="ml-auto text-[10px] text-muted-foreground">
          Claude → автофоллбэк OpenRouter
        </span>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          <ul className="flex flex-col gap-4">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
            {isStreaming &&
            messages[messages.length - 1]?.role !== "assistant" ? (
              <li className="flex items-start gap-2.5">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
                  <Bot className="h-4 w-4" aria-hidden="true" />
                </div>
                <div className="flex items-center gap-1.5 pt-1.5">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary [animation-delay:150ms]" />
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary [animation-delay:300ms]" />
                </div>
              </li>
            ) : null}
          </ul>
        )}

        {error ? (
          <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            <p className="font-semibold">Ошибка</p>
            <p className="mt-1 font-mono">{error.message}</p>
          </div>
        ) : null}
      </div>

      <form
        className="flex shrink-0 items-end gap-2 border-t border-border bg-card p-3"
        onSubmit={handleSubmit}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault()
              handleSubmit(e)
            }
          }}
          placeholder="Спросите ИИ — например, 'открой github.com и покажи trending'"
          rows={2}
          className="flex-1 resize-none rounded-md border border-border bg-input px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus:border-primary focus:ring-1 focus:ring-primary"
          aria-label="Сообщение для ИИ"
          disabled={isStreaming}
        />
        <Button
          type="submit"
          size="icon"
          disabled={isStreaming || !input.trim()}
          aria-label="Отправить"
        >
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </div>
  )
}

function MessageBubble({ message }: { message: UIMessage }) {
  const isUser = message.role === "user"
  const text = getMessageText(message)
  const meta = message.metadata as ChatMetadata | undefined

  return (
    <li className={`flex items-start gap-2.5 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${
          isUser ? "bg-secondary text-secondary-foreground" : "bg-primary/15 text-primary"
        }`}
      >
        {isUser ? (
          <User className="h-4 w-4" aria-hidden="true" />
        ) : (
          <Bot className="h-4 w-4" aria-hidden="true" />
        )}
      </div>
      <div className={`flex max-w-[85%] flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-lg px-3 py-2 text-sm leading-relaxed ${
            isUser
              ? "bg-primary text-primary-foreground"
              : "bg-card text-card-foreground border border-border"
          }`}
        >
          <p className="whitespace-pre-wrap">{text}</p>
        </div>
        {!isUser && meta?.modelLabel ? (
          <span className="px-1 font-mono text-[10px] text-muted-foreground">
            {meta.modelLabel}
            {meta.fallbackCount && meta.fallbackCount > 0
              ? ` · fallback #${meta.fallbackCount}`
              : ""}
          </span>
        ) : null}
      </div>
    </li>
  )
}

function EmptyState() {
  const examples = [
    "Что такое GitHub Codespaces в двух словах?",
    "Напиши команду для клонирования репозитория",
    "Объясни как работает Playwright",
    "Какие порты обычно открыты для Next.js dev сервера?",
  ]

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary/15 text-primary">
        <Bot className="h-6 w-6" aria-hidden="true" />
      </div>
      <div>
        <p className="text-sm font-semibold">Чат с ИИ-ассистентом</p>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          {"Я работаю как Claude Code. Если основная модель Claude недоступна — "}
          <br />
          {"автоматически переключусь на бесплатную модель через OpenRouter."}
        </p>
      </div>
      <ul className="flex w-full flex-col gap-2">
        {examples.map((ex) => (
          <li key={ex} className="rounded-md border border-border bg-card px-3 py-2 text-left text-xs text-muted-foreground">
            {ex}
          </li>
        ))}
      </ul>
    </div>
  )
}
