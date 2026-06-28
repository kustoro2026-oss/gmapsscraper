"""Minimal FastAPI + CORS + StaticFiles — isolate 502 to specific component."""
import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="GMaps Scraper — Minimal+CORS+Static")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(BASE_DIR, "static")
print(f"   Static dir: {static_dir}, exists={os.path.isdir(static_dir)}")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/health")
async def health():
    return {"status": "ok", "server": "GMaps Scraper License Server"}

@app.get("/")
async def root():
    return JSONResponse({"status": "ok", "message": "FastAPI + CORS + Static"})
