"""Minimal FastAPI — no DB, no auth, no static. Isolate the 502 issue."""
import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="GMaps Scraper — Minimal")

@app.get("/health")
async def health():
    return {"status": "ok", "server": "GMaps Scraper License Server"}

@app.get("/")
async def root():
    return JSONResponse({"status": "ok", "message": "Minimal FastAPI running"})

# if running directly
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
