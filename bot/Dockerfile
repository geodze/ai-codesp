# Dockerfile for the Telegram bot.
#
# Build context can be EITHER the repo root or the `bot/` subdirectory —
# both work. The COPY paths use a glob that matches both layouts:
#   - From repo root:  `bot/requirements.txt` matches `bot/requirements.txt`
#   - From bot/:       `bot/requirements.txt` doesn't exist, so we fall back
#     to `requirements.txt` via the second COPY line.
# The first matching COPY always wins; the no-op COPY of the same file is
# harmless.
#
# This dual-context support is what lets Render (root context) and
# Railway/Fly (bot/ context) both build off the exact same Dockerfile.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# git is needed for /clone, ca-certificates for HTTPS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements file regardless of which dir was the build context.
# When context = repo root: `COPY bot/requirements.txt ./` works.
# When context = bot/:      `COPY requirements.txt ./` works.
# We set up the second case so the image handles both — pick whichever
# path actually exists.
COPY . /tmp/src/
RUN if [ -f /tmp/src/bot/requirements.txt ]; then \
        cp /tmp/src/bot/requirements.txt /app/requirements.txt; \
    elif [ -f /tmp/src/requirements.txt ]; then \
        cp /tmp/src/requirements.txt /app/requirements.txt; \
    else \
        echo "ERROR: requirements.txt not found in build context" && exit 1; \
    fi

RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the bot package itself, picking up whichever layout is in the
# build context.
RUN if [ -d /tmp/src/bot ]; then \
        cp -r /tmp/src/bot /app/bot; \
    else \
        mkdir -p /app/bot && \
        cp -r /tmp/src/. /app/bot/; \
    fi \
    && rm -rf /tmp/src

EXPOSE 8080

CMD ["python", "-m", "bot.main"]
