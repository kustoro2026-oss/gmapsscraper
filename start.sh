#!/bin/bash
# ── Start Xvfb (virtual display) + Google Maps Scraper ────────────
set -e

# Kill existing Xvfb kalau ada
pkill Xvfb 2>/dev/null || true
rm -f /tmp/.X*-lock /tmp/.X11-unix/X*

# Start Xvfb di display :99
echo "🖥  Starting Xvfb on :99..."
Xvfb :99 -screen 0 1920x1080x24 -ac +extension RANDR &
XVFB_PID=$!
sleep 1

# Cek Xvfb benar-benar jalan
if ! kill -0 $XVFB_PID 2>/dev/null; then
    echo "❌ Xvfb failed to start!"
    exit 1
fi
echo "✅ Xvfb PID=$XVFB_PID running"

export DISPLAY=:99

# Cleanup on exit
cleanup() {
    echo "🛑 Shutting down Xvfb..."
    kill $XVFB_PID 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Run app
echo "🚀 Starting app on port ${PORT:-8000}..."
exec python app.py
