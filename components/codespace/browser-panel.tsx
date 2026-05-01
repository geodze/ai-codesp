"use client"

import { useState } from "react"
import { ArrowLeft, ArrowRight, Globe, Lock, RotateCw } from "lucide-react"
import { Button } from "@/components/ui/button"

export function BrowserPanel() {
  const [url, setUrl] = useState("https://example.com")
  const [inputUrl, setInputUrl] = useState("https://example.com")
  const [iframeKey, setIframeKey] = useState(0)

  const navigate = (target: string) => {
    let normalized = target.trim()
    if (!normalized) return
    if (!/^https?:\/\//i.test(normalized)) {
      normalized = `https://${normalized}`
    }
    setUrl(normalized)
    setInputUrl(normalized)
  }

  return (
    <div className="flex h-full flex-col bg-background">
      {/* Title bar */}
      <div className="flex h-9 shrink-0 items-center gap-2 border-b border-border bg-card px-3">
        <Globe className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Браузер
        </span>
        <span className="ml-auto text-[10px] text-muted-foreground">
          Headless Chromium (Playwright)
        </span>
      </div>

      {/* URL bar */}
      <form
        className="flex h-10 shrink-0 items-center gap-1.5 border-b border-border bg-card px-2"
        onSubmit={(e) => {
          e.preventDefault()
          navigate(inputUrl)
        }}
      >
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          aria-label="Назад"
          disabled
        >
          <ArrowLeft className="h-3.5 w-3.5" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          aria-label="Вперёд"
          disabled
        >
          <ArrowRight className="h-3.5 w-3.5" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          aria-label="Обновить"
          onClick={() => setIframeKey((k) => k + 1)}
        >
          <RotateCw className="h-3.5 w-3.5" />
        </Button>
        <div className="flex flex-1 items-center gap-1.5 rounded-md border border-border bg-input px-2 py-1">
          <Lock className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
          <input
            type="url"
            value={inputUrl}
            onChange={(e) => setInputUrl(e.target.value)}
            placeholder="https://..."
            className="flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
            aria-label="URL"
          />
        </div>
        <Button type="submit" size="sm" className="h-7 px-3 text-xs">
          Перейти
        </Button>
      </form>

      {/* Viewport */}
      <div className="flex-1 overflow-hidden bg-background">
        <iframe
          key={iframeKey}
          src={url}
          title="Browser preview"
          className="h-full w-full border-0 bg-white"
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
          referrerPolicy="no-referrer"
        />
      </div>

      {/* Status bar */}
      <div className="flex h-6 shrink-0 items-center justify-between border-t border-border bg-card px-3 text-[10px] text-muted-foreground">
        <span className="font-mono">{url}</span>
        <span>Этап 1: iframe-режим. Playwright-управление подключим на этапе 2.</span>
      </div>
    </div>
  )
}
