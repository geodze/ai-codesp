#!/usr/bin/env bash
# Auto-setup script for GitHub Codespaces.
# Installs opencode CLI + Node deps + Python deps for the Telegram bot.

set -euo pipefail

echo "==> [post-create] Installing opencode CLI..."
if ! command -v opencode >/dev/null 2>&1; then
  curl -fsSL https://opencode.ai/install | bash
  # Add to PATH for current session
  export PATH="$HOME/.opencode/bin:$PATH"
fi

# Persist for future shells
PROFILE_LINE='export PATH="$HOME/.opencode/bin:$PATH"'
for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
  if [ -f "$rc" ] && ! grep -qF "$PROFILE_LINE" "$rc"; then
    echo "$PROFILE_LINE" >> "$rc"
  fi
done

echo "==> [post-create] opencode.json: $(cat opencode.json 2>/dev/null | head -1 || echo 'missing')"
echo "    Superpowers plugin will auto-install on first 'opencode' run."

echo "==> [post-create] Installing Node.js deps for the Next.js app..."
if [ -f "pnpm-lock.yaml" ]; then
  if ! command -v pnpm >/dev/null 2>&1; then
    npm install -g pnpm
  fi
  pnpm install --frozen-lockfile || pnpm install
elif [ -f "package-lock.json" ]; then
  npm ci
fi

echo "==> [post-create] Installing Python deps for the Telegram bot..."
if [ -f "bot/requirements.txt" ]; then
  python3 -m venv bot/.venv
  bot/.venv/bin/pip install --upgrade pip
  bot/.venv/bin/pip install -r bot/requirements.txt
fi

cat <<'EOF'

================================================================
 Codespace ready.

  Web app:        pnpm dev
  opencode CLI:   opencode               (uses opencode.json + superpowers)
  Telegram bot:   cp bot/.env.example bot/.env  &&  edit  &&
                  bot/.venv/bin/python -m bot.main

  First time using opencode here? Run:
      opencode

  Then ask: "Tell me about your superpowers"
  to verify the skills plugin loaded correctly.
================================================================

EOF
