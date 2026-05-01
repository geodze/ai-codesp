"use client"

import { useState } from "react"
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels"
import { Header } from "@/components/codespace/header"
import { BrowserPanel } from "@/components/codespace/browser-panel"
import { TerminalPanel } from "@/components/codespace/terminal-panel"
import { ChatPanel } from "@/components/codespace/chat-panel"

type ModelInfo = {
  label: string | null
  provider: string | null
  fallbackCount: number
}

export default function HomePage() {
  const [modelInfo, setModelInfo] = useState<ModelInfo>({
    label: null,
    provider: null,
    fallbackCount: 0,
  })
  const [browserVisible, setBrowserVisible] = useState(true)

  return (
    <main className="flex h-dvh flex-col bg-background text-foreground">
      <Header
        modelLabel={modelInfo.label}
        modelProvider={modelInfo.provider}
        fallbackCount={modelInfo.fallbackCount}
        browserVisible={browserVisible}
        onToggleBrowser={() => setBrowserVisible((v) => !v)}
      />

      <div className="min-h-0 flex-1">
        <PanelGroup
          key={browserVisible ? "with-browser" : "no-browser"}
          direction="horizontal"
          autoSaveId={browserVisible ? "codespace-h" : "codespace-h-nobrowser"}
        >
          {browserVisible ? (
            <>
              {/* Левая колонка: Браузер */}
              <Panel defaultSize={55} minSize={30}>
                <BrowserPanel />
              </Panel>

              <PanelResizeHandle className="w-1 bg-border transition-colors hover:bg-primary/50 data-[resize-handle-state=drag]:bg-primary" />
            </>
          ) : null}

          {/* Правая колонка: Чат сверху + Терминал снизу */}
          <Panel defaultSize={browserVisible ? 45 : 100} minSize={25}>
            <PanelGroup direction="vertical" autoSaveId="codespace-v">
              <Panel defaultSize={60} minSize={20}>
                <ChatPanel onModelChange={setModelInfo} />
              </Panel>

              <PanelResizeHandle className="h-1 bg-border transition-colors hover:bg-primary/50 data-[resize-handle-state=drag]:bg-primary" />

              <Panel defaultSize={40} minSize={15}>
                <TerminalPanel />
              </Panel>
            </PanelGroup>
          </Panel>
        </PanelGroup>
      </div>
    </main>
  )
}
