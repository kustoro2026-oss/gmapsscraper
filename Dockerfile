# ── Google Maps Scraper — Dockerfile with xvfb ─────────────────────
# Railway auto-detects Dockerfile → uses Docker builder instead of Nixpacks
# xvfb = virtual display agar Chromium bisa jalan di mode visible (headless=False)
# Ini BUKAN "headless browser" — Chromium render ke virtual screen xvfb
# Google Maps tidak bisa mendeteksi xvfb sebagai headless → lebih aman

FROM python:3.11-slim

# ── Install system dependencies ────────────────────────────────────
# xvfb: virtual framebuffer (X11 virtual display)
# Chromium deps: library yang dibutuhkan Playwright untuk jalankan Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    xauth \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libxcb1 \
    libxext6 \
    libx11-6 \
    libxrender1 \
    libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

# ── Python setup ──────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Playwright + Chromium ─────────────────────────────────────────
RUN playwright install chromium
RUN playwright install-deps chromium

# ── App code ──────────────────────────────────────────────────────
COPY . .

# Make start script executable
RUN chmod +x start.sh

# Railway uses PORT env var
EXPOSE 8000

# ── Launch: start.sh → Xvfb :99 → Python app ────────────────────
CMD ["./start.sh"]
