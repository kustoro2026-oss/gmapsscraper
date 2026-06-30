"""JWT Auth + Password Login — email + password authentication."""

import os
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import User, ApiKey, UserRole

# ── Config ──────────────────────────────────────────────────────────

JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    print("=" * 60)
    print("  [FATAL] JWT_SECRET not set! All tokens invalid on restart!")
    print("  Set JWT_SECRET env var to a strong random value.")
    print("=" * 60)
    import sys
    sys.exit(1)

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24
ADMIN_EMAILS = os.environ.get("ADMIN_EMAILS", "").split(",")  # e.g. "me@email.com"

bearer_scheme = HTTPBearer(auto_error=False)


# ── Password Hashing (pbkdf2_hmac) ──────────────────────────────────

PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    """Hash password with pbkdf2_hmac + random salt. Returns salt$hash."""
    salt = secrets.token_hex(32)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return f"{salt}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify password against stored salt$hash."""
    try:
        salt, expected_hash = stored.split("$", 1)
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
        return secrets.compare_digest(h.hex(), expected_hash)
    except (ValueError, AttributeError):
        return False


# ── JWT ─────────────────────────────────────────────────────────────

def create_token(user_id: str, role: str = "user", expire_hours: int = JWT_EXPIRE_HOURS) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=expire_hours),
        "iat": datetime.now(timezone.utc),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalid atau expired")


# ── Dependencies ─────────────────────────────────────────────────────

async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not creds:
        raise HTTPException(status_code=401, detail="Authorization header diperlukan")
    payload = decode_token(creds.credentials)
    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User tidak ditemukan")
    if user.is_banned:
        raise HTTPException(status_code=403, detail="Akun dibanned")
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Email belum diverifikasi. Cek inbox email kamu.")
    return user


async def get_admin_user(
    user: User = Depends(get_current_user),
) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


async def get_license_for_user(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return active license for current user."""
    from models import License
    result = await db.execute(
        select(License)
        .where(License.user_id == user.id, License.is_active == True)
        .order_by(License.created_at.desc())
        .limit(1)
    )
    lic = result.scalar_one_or_none()
    if not lic:
        raise HTTPException(status_code=402, detail="Tidak ada lisensi aktif. Silakan beli paket.")
    if lic.used_quota >= lic.total_quota:
        raise HTTPException(status_code=402, detail="Quota habis. Silakan beli paket baru.")
    return lic


async def get_api_key_for_user(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.is_active == True)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=401, detail="API key tidak ditemukan")
    return key


# ── Desktop App Auth (API Key instead of JWT) ───────────────────

async def get_user_by_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Auth via API key in Authorization: Bearer <api_key> or X-API-Key header."""
    api_key_raw: str | None = None

    # Try Authorization: Bearer <key>
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        api_key_raw = auth_header[7:].strip()

    # Fallback: X-API-Key header
    if not api_key_raw:
        api_key_raw = request.headers.get("X-API-Key", "").strip()

    if not api_key_raw:
        raise HTTPException(status_code=401, detail="API key dibutuhkan")

    # Look up API key
    result = await db.execute(
        select(ApiKey).where(ApiKey.key == api_key_raw, ApiKey.is_active == True)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=401, detail="API key tidak valid")

    # Get user
    user = await db.scalar(select(User).where(User.id == api_key.user_id))
    if not user:
        raise HTTPException(status_code=401, detail="User tidak ditemukan")
    if user.is_banned:
        raise HTTPException(status_code=403, detail="Akun dibanned")
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Email belum diverifikasi. Cek inbox email kamu.")

    return user


async def get_license_by_api_key(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Return active license for desktop app user (auth via API key)."""
    from models import License
    result = await db.execute(
        select(License)
        .where(License.user_id == user.id, License.is_active == True)
        .order_by(License.created_at.desc())
        .limit(1)
    )
    lic = result.scalar_one_or_none()
    if not lic:
        raise HTTPException(status_code=402, detail="Tidak ada lisensi aktif. Silakan beli paket.")
    if lic.used_quota >= lic.total_quota:
        raise HTTPException(status_code=402, detail="Quota habis. Silakan beli paket baru.")
    return lic
