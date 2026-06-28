"""GMaps Scraper v2 — License Server (FastAPI + PostgreSQL)."""

import os
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from database import init_db, get_db, engine, Base  # noqa: F401
from models import User, ApiKey, License, Transaction, UsageLog, TransactionStatus, UserRole, PackageType
from auth import (
    create_token, decode_token, generate_otp, verify_otp,
    get_current_user, get_admin_user, get_license_for_user,
    ADMIN_EMAILS, bearer_scheme,
    get_user_by_api_key, get_license_by_api_key,
)
from duitku import create_invoice, verify_callback_signature, PACKAGES


# ── App Setup ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    import traceback as _tb
    try:
        print("   [LIFESPAN] Initializing database...")
        await init_db()
        print("   [LIFESPAN] Database init complete.")
        # Auto-create first admin from ADMIN_EMAILS env
        async with engine.begin() as conn:
            for admin_email in ADMIN_EMAILS:
                admin_email = admin_email.strip()
                if not admin_email:
                    continue
                result = await conn.execute(
                    text("SELECT id FROM users WHERE email = :email"), {"email": admin_email}
                )
                row = result.fetchone()
                if not row:
                    new_id = uuid.uuid4()
                    await conn.execute(
                        text("INSERT INTO users (id, email, role, is_banned) VALUES (:id, :email, 'admin', false)"),
                        {"id": new_id, "email": admin_email},
                    )
                    print(f"   [ADMIN CREATED] {admin_email}")
        print("   [LIFESPAN] Startup complete, ready to serve.")
    except Exception:
        print("   [LIFESPAN ERROR]")
        _tb.print_exc()
        raise
    yield


app = FastAPI(title="GMaps Scraper License Server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(BASE_DIR, "templates")
static_dir = os.path.join(BASE_DIR, "static")
if not os.path.isdir(static_dir):
    print(f"   [WARN] Static dir not found: {static_dir}, skipping mount")
else:
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ── Health Check ──────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "server": "GMaps Scraper License Server"}


@app.get("/api/debug/apikey/{api_key}")
async def debug_apikey(api_key: str, db: AsyncSession = Depends(get_db)):
    """Debug endpoint: check if API key exists."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.key == api_key)
    )
    key = result.scalar_one_or_none()
    if not key:
        return {"found": False, "api_key": api_key}
    return {
        "found": True,
        "is_active": key.is_active,
        "user_id": str(key.user_id),
    }


# ── HTML Page Routes ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def landing():
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(templates_dir, "dashboard.html"))


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(templates_dir, "login.html"))


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(templates_dir, "admin.html"))


# ══════════════════════════════════════════════════════════════════
#  AUTH ROUTES
# ══════════════════════════════════════════════════════════════════

@app.post("/api/auth/send-otp")
async def send_otp(email: str = Form(...)):
    """Kirim OTP 6-digit ke email."""
    email = email.strip().lower()
    code = generate_otp(email)
    # TODO: integrasi email provider (SendGrid / Mailgun / SMTP)
    return JSONResponse({"success": True, "message": f"OTP dikirim ke {email} (dev: {code})"})


@app.post("/api/auth/verify")
async def verify(email: str = Form(...), otp: str = Form(...), db: AsyncSession = Depends(get_db)):
    """Verifikasi OTP, return JWT. Auto-create user jika belum ada."""
    email = email.strip().lower()
    if not verify_otp(email, otp):
        raise HTTPException(status_code=400, detail="OTP tidak valid atau expired")

    # Cari atau buat user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    is_new = False
    if not user:
        user = User(id=uuid.uuid4(), email=email, name=email.split("@")[0])
        db.add(user)
        await db.flush()
        is_new = True

    # Auto-generate API key kalau belum ada
    key_result = await db.execute(select(ApiKey).where(ApiKey.user_id == user.id))
    api_key = key_result.scalar_one_or_none()
    if not api_key:
        api_key = ApiKey(id=uuid.uuid4(), user_id=user.id, key=uuid.uuid4().hex)
        db.add(api_key)
        await db.flush()

    token = create_token(str(user.id), user.role.value)
    return JSONResponse({
        "success": True,
        "token": token,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
            "is_new": is_new,
        },
        "api_key": api_key.key,
    })


# ══════════════════════════════════════════════════════════════════
#  LICENSE ROUTES
# ══════════════════════════════════════════════════════════════════

@app.get("/api/license/status")
async def license_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cek status lisensi + sisa quota."""
    result = await db.execute(
        select(License)
        .where(License.user_id == user.id, License.is_active == True)
        .order_by(License.created_at.desc())
        .limit(1)
    )
    lic = result.scalar_one_or_none()

    api_key_result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.is_active == True)
    )
    api_key = api_key_result.scalar_one_or_none()

    return JSONResponse({
        "has_license": lic is not None,
        "license": {
            "package": lic.package.value if lic else None,
            "total_quota": lic.total_quota if lic else 0,
            "used_quota": lic.used_quota if lic else 0,
            "remaining": (lic.total_quota - lic.used_quota) if lic else 0,
            "max_scrolls": lic.max_scrolls if lic else 0,
        } if lic else None,
        "api_key": api_key.key if api_key else None,
        "is_banned": user.is_banned,
    })


@app.post("/api/license/use")
async def use_quota(
    license: License = Depends(get_license_for_user),
    db: AsyncSession = Depends(get_db),
    keyword: str = Form(""),
    results_count: int = Form(0),
):
    """Kurangi 1 quota + log usage setelah scrape sukses."""
    license.used_quota += 1

    log = UsageLog(
        id=uuid.uuid4(),
        user_id=license.user_id,
        license_id=license.id,
        keyword=keyword[:255] if keyword else None,
        results_count=results_count,
    )
    db.add(log)
    await db.flush()

    remaining = license.total_quota - license.used_quota
    return JSONResponse({
        "success": True,
        "remaining": remaining,
        "package": license.package.value,
    })


# ══════════════════════════════════════════════════════════════════
#  DESKTOP APP ROUTES (API Key auth)
# ══════════════════════════════════════════════════════════════════

@app.get("/api/desktop/status")
async def desktop_status(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Cek status lisensi via API key (untuk Desktop App)."""
    result = await db.execute(
        select(License)
        .where(License.user_id == user.id, License.is_active == True)
        .order_by(License.created_at.desc())
        .limit(1)
    )
    lic = result.scalar_one_or_none()

    if lic and lic.used_quota < lic.total_quota:
        return JSONResponse({
            "active": True,
            "quota_remaining": lic.total_quota - lic.used_quota,
            "package": lic.package.value,
            "max_scrolls": lic.max_scrolls,
            "user_email": user.email,
        })
    elif lic and lic.used_quota >= lic.total_quota:
        return JSONResponse({
            "active": False,
            "quota_remaining": 0,
            "package": lic.package.value,
            "error": "Quota habis",
        })
    else:
        return JSONResponse({
            "active": False,
            "quota_remaining": 0,
            "package": None,
            "error": "Tidak ada lisensi aktif",
        })


@app.post("/api/desktop/use")
async def desktop_use_quota(
    lic: License = Depends(get_license_by_api_key),
    db: AsyncSession = Depends(get_db),
    keyword: str = Form(""),
    results_count: int = Form(0),
):
    """Kurangi 1 quota via API key (untuk Desktop App)."""
    lic.used_quota += 1

    log = UsageLog(
        id=uuid.uuid4(),
        user_id=lic.user_id,
        license_id=lic.id,
        keyword=keyword[:255] if keyword else None,
        results_count=results_count,
    )
    db.add(log)
    await db.flush()

    remaining = lic.total_quota - lic.used_quota
    return JSONResponse({
        "success": True,
        "remaining": remaining,
        "package": lic.package.value,
    })


# ══════════════════════════════════════════════════════════════════
#  PAYMENT ROUTES
# ══════════════════════════════════════════════════════════════════

@app.post("/api/payment/create")
async def payment_create(
    package_key: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Buat invoice Duitku."""
    if package_key not in PACKAGES:
        raise HTTPException(status_code=400, detail=f"Paket tidak valid: {package_key}")

    merchant_order_id = f"GMAPS-{uuid.uuid4().hex[:12].upper()}"
    pkg = PACKAGES[package_key]

    # Buat transaction record (pending)
    txn = Transaction(
        id=uuid.uuid4(),
        user_id=user.id,
        amount=pkg["price"],
        duitku_order_id=merchant_order_id,
        product=PackageType(package_key),
        status=TransactionStatus.pending,
    )
    db.add(txn)
    await db.flush()

    try:
        invoice = await create_invoice(package_key, user.email, merchant_order_id)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Gagal membuat invoice: {e}")

    txn.reference = invoice.get("reference")
    await db.flush()

    return JSONResponse({
        "success": True,
        "payment_url": invoice["paymentUrl"],
        "order_id": merchant_order_id,
        "reference": invoice.get("reference"),
    })


@app.post("/api/payment/callback")
async def payment_callback(request: Request, db: AsyncSession = Depends(get_db)):
    """Duitku callback webhook — verify & activate license."""
    body = await request.form()
    params = dict(body)

    merchant_code = params.get("merchantCode", "")
    merchant_order_id = params.get("merchantOrderId", "")
    amount = params.get("amount", "0")
    signature = params.get("signature", "")
    result_code = params.get("resultCode", "")
    reference = params.get("reference", "")
    payment_method = params.get("paymentCode", "")

    # Verify signature
    if not verify_callback_signature(merchant_code, amount, merchant_order_id, signature):
        raise HTTPException(status_code=400, detail="Invalid callback signature")

    # Cari transaksi
    result = await db.execute(
        select(Transaction).where(Transaction.duitku_order_id == merchant_order_id)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    txn.callback_raw = params
    txn.reference = reference
    txn.payment_method = payment_method

    if result_code == "00":  # Success
        txn.status = TransactionStatus.success
        pkg = PACKAGES.get(txn.product.value, {})
        # Create license
        lic = License(
            id=uuid.uuid4(),
            user_id=txn.user_id,
            package=txn.product,
            total_quota=pkg.get("quota", 25),
            max_scrolls=pkg.get("max_scrolls", 10),
            is_active=True,
        )
        db.add(lic)
        txn.license_id = lic.id
    elif result_code in ("01", "02", "03"):
        txn.status = TransactionStatus.failed

    await db.flush()
    return JSONResponse({"success": True})


@app.get("/api/payment/return")
async def payment_return():
    """Redirect setelah user selesai bayar."""
    return RedirectResponse(url="/")


# ══════════════════════════════════════════════════════════════════
#  ADMIN ROUTES
# ══════════════════════════════════════════════════════════════════

@app.get("/api/admin/stats")
async def admin_stats(admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    """Dashboard stats."""
    total_users = await db.scalar(select(func.count(User.id)))
    active_licenses = await db.scalar(
        select(func.count(License.id)).where(License.is_active == True)
    )
    total_revenue = await db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.status == TransactionStatus.success)
    )
    today_usage = await db.scalar(
        select(func.count(UsageLog.id))
        .where(func.date(UsageLog.created_at) == func.current_date())
    )

    return JSONResponse({
        "total_users": total_users,
        "active_licenses": active_licenses,
        "total_revenue": float(total_revenue or 0),
        "today_usage": today_usage,
    })


@app.get("/api/admin/users")
async def admin_users(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    search: str = "",
):
    """List users with pagination."""
    per_page = 20
    offset = (page - 1) * per_page

    query = select(User).order_by(User.created_at.desc())
    count_query = select(func.count(User.id))

    if search:
        query = query.where(User.email.ilike(f"%{search}%"))
        count_query = count_query.where(User.email.ilike(f"%{search}%"))

    query = query.offset(offset).limit(per_page)
    result = await db.execute(query)
    users = result.scalars().all()
    total = await db.scalar(count_query)

    user_data = []
    for u in users:
        lic_result = await db.execute(
            select(License).where(License.user_id == u.id).order_by(License.created_at.desc()).limit(1)
        )
        latest_lic = lic_result.scalar_one_or_none()
        user_data.append({
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
            "role": u.role.value,
            "is_banned": u.is_banned,
            "latest_license": latest_lic.package.value if latest_lic else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        })

    return JSONResponse({
        "users": user_data,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if total else 0,
    })


@app.get("/api/admin/users/{user_id}")
async def admin_user_detail(
    user_id: str,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Detail user + licenses + transactions."""
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    api_key_result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id)
    )
    api_key = api_key_result.scalar_one_or_none()

    licenses_result = await db.execute(
        select(License).where(License.user_id == user.id).order_by(License.created_at.desc())
    )
    licenses = licenses_result.scalars().all()

    txns_result = await db.execute(
        select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.created_at.desc()).limit(50)
    )
    transactions = txns_result.scalars().all()

    return JSONResponse({
        "user": {
            "id": str(user.id), "email": user.email, "name": user.name,
            "role": user.role.value, "is_banned": user.is_banned,
            "banned_reason": user.banned_reason, "created_at": user.created_at.isoformat() if user.created_at else None,
            "api_key": api_key.key if api_key else None,
        },
        "licenses": [{
            "id": str(l.id), "package": l.package.value,
            "total_quota": l.total_quota, "used_quota": l.used_quota,
            "remaining": l.total_quota - l.used_quota,
            "max_scrolls": l.max_scrolls, "is_active": l.is_active,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        } for l in licenses],
        "transactions": [{
            "id": str(t.id), "amount": float(t.amount),
            "product": t.product.value, "status": t.status.value,
            "payment_method": t.payment_method,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        } for t in transactions],
    })


@app.post("/api/admin/users/{user_id}/ban")
async def admin_ban_user(user_id: str, reason: str = Form(""), admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_banned = True
    user.banned_reason = reason or None
    # Deactivate all licenses
    await db.execute(text("UPDATE licenses SET is_active = false WHERE user_id = :uid"), {"uid": user.id})
    # Deactivate API key
    await db.execute(text("UPDATE api_keys SET is_active = false WHERE user_id = :uid"), {"uid": user.id})
    await db.flush()
    return JSONResponse({"success": True, "message": f"User {user.email} dibanned"})


@app.post("/api/admin/users/{user_id}/unban")
async def admin_unban_user(user_id: str, admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_banned = False
    user.banned_reason = None
    await db.flush()
    return JSONResponse({"success": True, "message": f"User {user.email} di-unban"})


@app.post("/api/admin/users/{user_id}/add-quota")
async def admin_add_quota(
    user_id: str, amount: int = Form(...),
    admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db),
):
    lic = await db.scalar(
        select(License).where(License.user_id == user_id, License.is_active == True).order_by(License.created_at.desc()).limit(1)
    )
    if not lic:
        raise HTTPException(status_code=404, detail="No active license")
    lic.total_quota += amount
    await db.flush()
    return JSONResponse({"success": True, "new_total": lic.total_quota})


@app.post("/api/admin/users/{user_id}/edit-quota")
async def admin_edit_quota(
    user_id: str, new_total: int = Form(...),
    admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db),
):
    lic = await db.scalar(
        select(License).where(License.user_id == user_id, License.is_active == True).order_by(License.created_at.desc()).limit(1)
    )
    if not lic:
        raise HTTPException(status_code=404, detail="No active license")
    lic.total_quota = new_total
    await db.flush()
    return JSONResponse({"success": True, "new_total": lic.total_quota})


@app.post("/api/admin/users/{user_id}/reset-key")
async def admin_reset_key(user_id: str, admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    # Deactivate old keys
    await db.execute(text("UPDATE api_keys SET is_active = false WHERE user_id = :uid"), {"uid": user_id})
    # Create new key
    new_key = ApiKey(id=uuid.uuid4(), user_id=user_id, key=uuid.uuid4().hex)
    db.add(new_key)
    await db.flush()
    return JSONResponse({"success": True, "new_api_key": new_key.key})


@app.get("/api/admin/transactions")
async def admin_transactions(
    admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db),
    page: int = 1, status: str = "",
):
    per_page = 30
    offset = (page - 1) * per_page
    query = select(Transaction).order_by(Transaction.created_at.desc())
    count_query = select(func.count(Transaction.id))

    if status:
        query = query.where(Transaction.status == TransactionStatus(status))
        count_query = count_query.where(Transaction.status == TransactionStatus(status))

    query = query.offset(offset).limit(per_page)
    result = await db.execute(query)
    txns = result.scalars().all()
    total = await db.scalar(count_query)

    txn_data = []
    for t in txns:
        user = await db.scalar(select(User).where(User.id == t.user_id))
        txn_data.append({
            "id": str(t.id), "user_email": user.email if user else "?",
            "user_name": user.name if user else "?",
            "amount": float(t.amount), "product": t.product.value,
            "status": t.status.value, "payment_method": t.payment_method,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })

    return JSONResponse({
        "transactions": txn_data, "total": total, "page": page,
    })


# ── Run ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port_raw = os.environ.get("PORT", "8080")
    port = int(port_raw)
    print("=" * 55)
    print(f"  GMaps Scraper License Server — http://0.0.0.0:{port}")
    print(f"  PORT env = {port_raw!r}")
    print("=" * 55)
    uvicorn.run(app, host="0.0.0.0", port=port)
