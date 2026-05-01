"use client"

import { useEffect, useRef, useState } from "react"
import { TerminalSquare, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"

type Line = { type: "input" | "output" | "system"; text: string }

const INITIAL_LINES: Line[] = [
  { type: "system", text: "AI Codespace terminal — этап 1 (заглушка)" },
  { type: "system", text: "Реальный bash появится на этапе 3. Здесь имитация." },
  { type: "output", text: "" },
  { type: "output", text: "Ubuntu 22.04.3 LTS · Node 20 · Python 3.12 · git 2.43" },
  { type: "output", text: 'Введите "help" чтобы посмотреть доступные команды.' },
  { type: "output", text: "" },
]

const MOCK_HANDLERS: Record<string, () => string[]> = {
  help: () => [
    "Доступные команды (mock):",
    "  help          — эта справка",
    "  whoami        — текущий пользователь",
    "  pwd           — рабочая директория",
    "  ls            — список файлов",
    "  date          — текущее время",
    "  clear         — очистить терминал",
  ],
  whoami: () => ["codespace"],
  pwd: () => ["/workspaces/ai-codespace"],
  ls: () => ["app  components  lib  package.json  tsconfig.json  README.md"],
  date: () => [new Date().toString()],
}

export function TerminalPanel() {
  const [lines, setLines] = useState<Line[]>(INITIAL_LINES)
  const [input, setInput] = useState("")
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [lines])

  const runCommand = (cmd: string) => {
    const trimmed = cmd.trim()
    if (!trimmed) return

    if (trimmed === "clear") {
      setLines([])
      return
    }

    const next: Line[] = [...lines, { type: "input", text: trimmed }]
    const handler = MOCK_HANDLERS[trimmed.split(" ")[0]]

    if (handler) {
      for (const out of handler()) {
        next.push({ type: "output", text: out })
      }
    } else {
      next.push({
        type: "output",
        text: `bash: ${trimmed.split(" ")[0]}: command not found (mock — реальный shell на этапе 3)`,
      })
    }
    setLines(next)
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex h-9 shrink-0 items-center gap-2 border-b border-border bg-card px-3">
        <TerminalSquare className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Терминал
        </span>
        <span className="ml-2 text-[10px] text-muted-foreground">bash · Linux</span>
        <Button
          variant="ghost"
          size="icon"
          className="ml-auto h-6 w-6"
          aria-label="Очистить"
          onClick={() => setLines([])}
        >
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-3 font-mono text-xs leading-relaxed"
        onClick={() => inputRef.current?.focus()}
      >
        {lines.map((line, i) => (
          <div
            key={i}
            className={
              line.type === "input"
                ? "text-foreground"
                : line.type === "system"
                  ? "text-muted-foreground italic"
                  : "text-foreground/80"
            }
          >
            {line.type === "input" ? (
              <>
                <span className="text-primary">codespace</span>
                <span className="text-muted-foreground">@ai-codespace:~$ </span>
                <span>{line.text}</span>
              </>
            ) : (
              <span className="whitespace-pre-wrap">{line.text || "\u00A0"}</span>
            )}
          </div>
        ))}

        <form
          className="flex items-center"
          onSubmit={(e) => {
            e.preventDefault()
            runCommand(input)
            setInput("")
          }}
        >
          <span className="text-primary">codespace</span>
          <span className="text-muted-foreground">@ai-codespace:~$&nbsp;</span>
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            className="flex-1 bg-transparent font-mono text-xs text-foreground outline-none"
            autoComplete="off"
            spellCheck={false}
            aria-label="Команда терминала"
          />
        </form>
      </div>
    </div>
  )
}
