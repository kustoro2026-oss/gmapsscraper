"""JWT Auth + Email OTP — passwordless login via email."""

import os
import uuid
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import User, ApiKey, UserRole

# ── Config ──────────────────────────────────────────────────────────

JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24
ADMIN_EMAILS = os.environ.get("ADMIN_EMAILS", "").split(",")  # e.g. "me@email.com"

bearer_scheme = HTTPBearer(auto_error=False)


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


# ── OTP (in-memory — ganti Redis untuk production) ──────────────────

_otp_store: dict[str, tuple[str, datetime]] = {}  # email → (code, expires_at)

OTP_EXPIRE_MINUTES = 5


def generate_otp(email: str) -> str:
    code = f"{secrets.randbelow(1000000):06d}"
    _otp_store[email.lower()] = (
        code,
        datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRE_MINUTES),
    )
    # TODO: kirim via email API (SendGrid, Mailgun, dll)
    print(f"   [OTP] {email} → {code}")
    return code


def verify_otp(email: str, code: str) -> bool:
    stored = _otp_store.get(email.lower())
    if not stored:
        return False
    stored_code, expires = stored
    if datetime.now(timezone.utc) > expires:
        del _otp_store[email.lower()]
        return False
    if stored_code != code.strip():
        return False
    del _otp_store[email.lower()]
    return True


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
