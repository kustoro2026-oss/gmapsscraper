"""Step 4: Full imports, minimal routes — isolate 502."""
import os
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from database import init_db, engine
from models import User
from auth import (
    create_token, decode_token, generate_otp, verify_otp,
    get_current_user, get_admin_user, get_license_for_user,
    ADMIN_EMAILS, bearer_scheme,
)
from duitku import create_invoice, verify_callback_signature, PACKAGES


@asynccontextmanager
async def lifespan(app: FastAPI):
    import traceback as _tb
    try:
        print("   [LIFESPAN] Init DB...")
        await init_db()
        print("   [LIFESPAN] DB ok, creating admin...")
        async with engine.begin() as conn:
            for admin_email in ADMIN_EMAILS:
                admin_email = admin_email.strip()
                if not admin_email:
                    continue
                result = await conn.execute(
                    text("SELECT id FROM users WHERE email = :email"), {"email": admin_email}
                )
                if not result.fetchone():
                    await conn.execute(
                        text("INSERT INTO users (id, email, role, is_banned) VALUES (:id, :email, 'admin', false)"),
                        {"id": uuid.uuid4(), "email": admin_email},
                    )
                    print(f"   [ADMIN] {admin_email}")
        print("   [LIFESPAN] Ready.")
    except Exception:
        print("   [LIFESPAN ERROR]")
        _tb.print_exc()
        raise
    yield


app = FastAPI(title="GMaps Scraper — Full Imports", lifespan=lifespan)

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
    return JSONResponse({"status": "ok", "message": "All imports OK"})
