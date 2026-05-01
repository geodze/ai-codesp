"use client"

import { Cloud, Cpu, HardDrive, PanelLeftClose, PanelLeftOpen, Zap } from "lucide-react"

type HeaderProps = {
  modelLabel: string | null
  modelProvider: string | null
  fallbackCount: number
  browserVisible: boolean
  onToggleBrowser: () => void
}

export function Header({
  modelLabel,
  modelProvider,
  fallbackCount,
  browserVisible,
  onToggleBrowser,
}: HeaderProps) {
  const isFallback = fallbackCount > 0
  const isFree = modelProvider === "openrouter-free"

  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-border bg-card px-4">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onToggleBrowser}
          aria-label={browserVisible ? "Скрыть панель браузера" : "Показать панель браузера"}
          aria-pressed={browserVisible}
          title={browserVisible ? "Скрыть браузер" : "Показать браузер"}
          className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
        >
          {browserVisible ? (
            <PanelLeftClose className="h-4 w-4" aria-hidden="true" />
          ) : (
            <PanelLeftOpen className="h-4 w-4" aria-hidden="true" />
          )}
        </button>
        <Cloud className="h-5 w-5 text-primary" aria-hidden="true" />
        <h1 className="text-sm font-semibold tracking-tight">AI Codespace</h1>
        <span className="ml-2 hidden text-xs text-muted-foreground md:inline">
          Cloud Dev Environment with AI
        </span>
      </div>

      <div className="flex items-center gap-3 text-xs">
        <div className="hidden items-center gap-1.5 text-muted-foreground md:flex">
          <Cpu className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Ubuntu</span>
        </div>
        <div className="hidden items-center gap-1.5 text-muted-foreground md:flex">
          <HardDrive className="h-3.5 w-3.5" aria-hidden="true" />
          <span>15 GB</span>
        </div>
        <div
          className="flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1"
          aria-live="polite"
        >
          <Zap
            className={`h-3.5 w-3.5 ${isFallback ? "text-destructive" : "text-primary"}`}
            aria-hidden="true"
          />
          <span className="font-mono">{modelLabel ?? "ожидание..."}</span>
          {isFree ? (
            <span className="rounded bg-primary/15 px-1.5 py-0.5 text-[10px] font-medium uppercase text-primary">
              Free
            </span>
          ) : null}
          {isFallback ? (
            <span className="rounded bg-destructive/15 px-1.5 py-0.5 text-[10px] font-medium uppercase text-destructive">
              Fallback
            </span>
          ) : null}
        </div>
      </div>
    </header>
  )
}
