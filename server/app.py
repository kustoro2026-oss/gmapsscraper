"""GMaps Scraper v2 — License Server (FastAPI + PostgreSQL)."""

import os
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from database import init_db, get_db, engine, Base  # noqa: F401
from models import User, ApiKey, License, Transaction, UsageLog, TransactionStatus, UserRole, PackageType
from auth import (
    create_token, decode_token, hash_password, verify_password,
    get_current_user, get_admin_user, get_license_for_user,
    ADMIN_EMAILS, bearer_scheme,
    get_user_by_api_key, get_license_by_api_key,
)
from duitku import create_invoice, verify_callback_signature, PACKAGES
from emailer import send_welcome_email, send_payment_confirmation

# ── Rate Limiter ──────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address)

# ── Server URL ────────────────────────────────────────────────────

SERVER_URL = os.environ.get("SERVER_URL", "https://gmapsscraper-production-36cd.up.railway.app")
UPGRADE_URL = f"{SERVER_URL}/"


# ── App Setup ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    import traceback as _tb
    try:
        print("   [LIFESPAN] Initializing database...")
        await init_db()
        print("   [LIFESPAN] Database init complete.")
        # Add 'trial' to PackageType ENUM if not exists
        async with engine.connect() as conn:
            try:
                await conn.execute(text("ALTER TYPE packagetype ADD VALUE 'trial'"))
                await conn.commit()
                print("   [LIFESPAN] Added 'trial' to packagetype ENUM")
            except Exception:
                await conn.rollback()
                print("   [LIFESPAN] 'trial' already in packagetype ENUM (or skip)")
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
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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


templates = Jinja2Templates(directory=templates_dir)


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
    try:
        return FileResponse(os.path.join(templates_dir, "landing.html"))
    except Exception as e:
        print(f"[LANDING ERROR] {e}")
        import traceback; traceback.print_exc()
        return HTMLResponse(f"<h1>500 — Server Error</h1><p>{e}</p>", status_code=500)


@app.get("/favicon.ico")
async def favicon():
    favicon_path = os.path.join(static_dir, "logo-gmaps.png")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/png")
    raise HTTPException(404)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    return FileResponse(os.path.join(templates_dir, "dashboard.html"))


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return FileResponse(os.path.join(templates_dir, "login.html"))


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    return FileResponse(os.path.join(templates_dir, "admin.html"))


# ══════════════════════════════════════════════════════════════════
#  AUTH ROUTES
# ══════════════════════════════════════════════════════════════════

@app.post("/api/auth/register")
@limiter.limit("5/minute")
async def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Register user baru dengan email + password."""
    try:
        email = email.strip().lower()
        name = name.strip()
        password = password.strip()

        if len(password) < 6:
            raise HTTPException(status_code=400, detail="Password minimal 6 karakter")
        if len(name) < 1:
            raise HTTPException(status_code=400, detail="Nama tidak boleh kosong")

        # Cek email sudah dipakai
        existing = await db.scalar(select(User).where(User.email == email))
        if existing:
            # Kalau user lama belum punya password (era OTP), upgrade ke password
            if not existing.password_hash:
                existing.password_hash = hash_password(password)
                existing.name = name
                # Pastikan role admin kalau email di ADMIN_EMAILS
                if email in ADMIN_EMAILS and existing.role != UserRole.admin:
                    existing.role = UserRole.admin
                token = create_token(str(existing.id), existing.role.value)
                key_result = await db.execute(
                    select(ApiKey).where(ApiKey.user_id == existing.id)
                )
                api_key_obj = key_result.scalar_one_or_none()
                return JSONResponse({
                    "success": True,
                    "message": "Password berhasil diset! Silakan login.",
                    "token": token,
                    "user": {
                        "id": str(existing.id),
                        "email": existing.email,
                        "name": existing.name,
                        "role": existing.role.value,
                        "is_new": False,
                    },
                    "api_key": api_key_obj.key if api_key_obj else None,
                })
            raise HTTPException(status_code=400, detail="Email sudah terdaftar. Silakan login.")

        # Tentukan role (admin jika email di ADMIN_EMAILS)
        role = UserRole.admin if email in ADMIN_EMAILS else UserRole.user

        # Buat user
        user = User(
            id=uuid.uuid4(),
            email=email,
            name=name,
            password_hash=hash_password(password),
            role=role,
        )
        db.add(user)
        await db.flush()

        # Auto-generate API key
        api_key = ApiKey(id=uuid.uuid4(), user_id=user.id, key=uuid.uuid4().hex)
        db.add(api_key)
        await db.flush()

        # Auto-create trial license
        trial_license = License(
            id=uuid.uuid4(),
            user_id=user.id,
            package=PackageType.trial,
            total_quota=10,
            max_scrolls=1,
        )
        db.add(trial_license)
        await db.flush()

        # Kirim welcome email
        send_welcome_email(email, name)

        token = create_token(str(user.id), user.role.value)
        return JSONResponse({
            "success": True,
            "message": "Registrasi berhasil!",
            "token": token,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
                "role": user.role.value,
                "is_new": True,
            },
            "api_key": api_key.key,
            "trial": {
                "active": True,
                "quota_total": trial_license.total_quota,
                "quota_remaining": trial_license.total_quota - trial_license.used_quota,
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        import traceback as _tb
        print(f"[REGISTER ERROR] {e}")
        _tb.print_exc()
        return JSONResponse({"detail": f"Server error: {str(e)}"}, status_code=500)


@app.post("/api/auth/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Login dengan email + password, return JWT."""
    try:
        email = email.strip().lower()
        password = password.strip()

        # Cari user
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=401, detail="Email atau password salah")

        if user.is_banned:
            raise HTTPException(status_code=403, detail="Akun dibanned")

        # Verifikasi password
        if not user.password_hash:
            raise HTTPException(status_code=401, detail="Akun belum punya password. Silakan register ulang.")
        if not verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="Email atau password salah")

        # Ambil API key
        key_result = await db.execute(
            select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.is_active == True)
        )
        api_key = key_result.scalar_one_or_none()

        token = create_token(str(user.id), user.role.value)
        return JSONResponse({
            "success": True,
            "token": token,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
                "role": user.role.value,
                "is_new": False,
            },
            "api_key": api_key.key if api_key else None,
        })
    except HTTPException:
        raise
    except Exception as e:
        import traceback as _tb
        print(f"[LOGIN ERROR] {e}")
        _tb.print_exc()
        return JSONResponse({"detail": f"Server error: {str(e)}"}, status_code=500)


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
#  USER ROUTES (Dashboard)
# ══════════════════════════════════════════════════════════════════

@app.get("/api/user/history")
async def user_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
):
    """Riwayat scraping user."""
    per_page = 20
    offset = (page - 1) * per_page
    count = await db.scalar(select(func.count(UsageLog.id)).where(UsageLog.user_id == user.id))
    result = await db.execute(
        select(UsageLog)
        .where(UsageLog.user_id == user.id)
        .order_by(UsageLog.created_at.desc())
        .offset(offset).limit(per_page)
    )
    logs = result.scalars().all()
    return JSONResponse({
        "logs": [{
            "id": str(l.id), "keyword": l.keyword, "results_count": l.results_count,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        } for l in logs],
        "total": count, "page": page, "total_pages": max(1, (count + per_page - 1) // per_page),
    })


@app.get("/api/user/invoices")
async def user_invoices(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
):
    """Riwayat transaksi user."""
    per_page = 20
    offset = (page - 1) * per_page
    count = await db.scalar(
        select(func.count(Transaction.id)).where(Transaction.user_id == user.id)
    )
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.desc())
        .offset(offset).limit(per_page)
    )
    txns = result.scalars().all()
    return JSONResponse({
        "invoices": [{
            "id": str(t.id), "amount": float(t.amount), "product": t.product.value,
            "status": t.status.value, "invoice_number": getattr(t, "invoice_number", None),
            "payment_method": t.payment_method,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        } for t in txns],
        "total": count, "page": page, "total_pages": max(1, (count + per_page - 1) // per_page),
    })


@app.get("/api/user/invoice/{txn_id}/download", response_class=HTMLResponse)
async def download_invoice(
    txn_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download invoice as HTML receipt."""
    result = await db.execute(
        select(Transaction).where(Transaction.id == txn_id, Transaction.user_id == user.id)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Invoice tidak ditemukan")
    inv_no = getattr(txn, "invoice_number", txn.duitku_order_id)
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="id"><head><meta charset="UTF-8"><title>Invoice {inv_no}</title>
<style>body{{font-family:Arial,sans-serif;max-width:600px;margin:40px auto;padding:20px;}}h1{{color:#3b82f6;}}table{{width:100%;border-collapse:collapse;margin:20px 0;}}td,th{{padding:8px;border-bottom:1px solid #ddd;text-align:left;}}.total{{font-size:20px;font-weight:bold;}}
@media print{{body{{margin:0;padding:0;}}}}</style></head><body>
<h1>GMaps Scraper — Invoice</h1>
<p><strong>Invoice:</strong> {inv_no}<br><strong>Tanggal:</strong> {txn.created_at.strftime('%d %B %Y') if txn.created_at else '-'}</p>
<table>
<tr><td>Paket</td><td><strong>{txn.product.value.upper()}</strong></td></tr>
<tr><td>Total</td><td class="total">Rp {int(txn.amount):,}</td></tr>
<tr><td>Status</td><td>{txn.status.value.upper()}</td></tr>
<tr><td>Metode</td><td>{txn.payment_method or '-'}</td></tr>
</table>
<p style="color:#888;font-size:12px;">Terima kasih telah menggunakan GMaps Scraper.</p>
<script>window.print();</script>
</body></html>""")


@app.post("/api/user/profile")
async def update_profile(
    name: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update nama profil."""
    user.name = name[:255]
    await db.flush()
    return JSONResponse({"success": True, "name": user.name})


@app.post("/api/user/reset-key")
async def reset_my_key(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reset API key sendiri."""
    await db.execute(text("UPDATE api_keys SET is_active = false WHERE user_id = :uid"), {"uid": user.id})
    new_key = ApiKey(id=uuid.uuid4(), user_id=user.id, key=uuid.uuid4().hex)
    db.add(new_key)
    await db.flush()
    return JSONResponse({"success": True, "new_api_key": new_key.key})


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
            "quota_total": lic.total_quota,
            "package": lic.package.value,
            "max_scrolls": lic.max_scrolls,
            "is_trial": lic.package == PackageType.trial,
            "user_email": user.email,
            "upgrade_url": UPGRADE_URL if lic.package == PackageType.trial else None,
        })
    elif lic and lic.used_quota >= lic.total_quota:
        return JSONResponse({
            "active": False,
            "quota_remaining": 0,
            "quota_total": lic.total_quota,
            "package": lic.package.value,
            "is_trial": lic.package == PackageType.trial,
            "error": "Quota habis. Silakan upgrade ke paket berbayar." if lic.package == PackageType.trial else "Quota habis. Silakan beli paket baru.",
            "upgrade_url": UPGRADE_URL,
        })
    else:
        return JSONResponse({
            "active": False,
            "quota_remaining": 0,
            "quota_total": 0,
            "package": None,
            "is_trial": False,
            "error": "Tidak ada lisensi aktif. Silakan beli paket di dashboard.",
            "upgrade_url": UPGRADE_URL,
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
@limiter.limit("10/minute")
async def payment_create(
    request: Request,
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
        # Generate invoice number
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        txn.invoice_number = f"INV-{date_str}-{uuid.uuid4().hex[:4].upper()}"
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
        # Send payment confirmation email
        user_result = await db.execute(select(User).where(User.id == txn.user_id))
        pay_user = user_result.scalar_one_or_none()
        if pay_user:
            send_payment_confirmation(
                pay_user.email,
                pay_user.name or pay_user.email.split("@")[0],
                txn.product.value.upper(),
                int(txn.amount),
                txn.invoice_number,
            )
    elif result_code in ("01", "02", "03"):
        txn.status = TransactionStatus.failed

    await db.flush()
    return JSONResponse({"success": True})


@app.get("/api/payment/return")
async def payment_return():
    """Redirect setelah user selesai bayar."""
    return RedirectResponse(url="/dashboard")


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
    page: int = 1, status: str = "", date_from: str = "", date_to: str = "",
):
    per_page = 30
    offset = (page - 1) * per_page
    query = select(Transaction).order_by(Transaction.created_at.desc())
    count_query = select(func.count(Transaction.id))

    if status:
        query = query.where(Transaction.status == TransactionStatus(status))
        count_query = count_query.where(Transaction.status == TransactionStatus(status))
    if date_from:
        from_dt = datetime.strptime(date_from, "%Y-%m-%d")
        query = query.where(Transaction.created_at >= from_dt)
        count_query = count_query.where(Transaction.created_at >= from_dt)
    if date_to:
        to_dt = datetime.strptime(date_to, "%Y-%m-%d")
        query = query.where(Transaction.created_at < to_dt)
        count_query = count_query.where(Transaction.created_at < to_dt)

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
            "invoice_number": getattr(t, "invoice_number", None),
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })

    return JSONResponse({
        "transactions": txn_data, "total": total, "page": page,
    })


# ══════════════════════════════════════════════════════════════════
#  ERROR HANDLERS
# ══════════════════════════════════════════════════════════════════

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    return HTMLResponse(
        templates.get_template("error.html").render({
            "code": "404", "title": "Halaman Tidak Ditemukan",
            "message": "Halaman yang kamu cari tidak ada atau sudah dipindahkan.",
            "request": request,
        }),
        status_code=404,
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    import traceback as _tb
    print(f"[500 ERROR] {request.url} — {exc}")
    _tb.print_exc()
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Internal server error"}, status_code=500)
    return HTMLResponse(
        templates.get_template("error.html").render({
            "code": "500", "title": "Server Error",
            "message": "Terjadi kesalahan di server. Coba lagi nanti.",
            "request": request,
        }),
        status_code=500,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return HTMLResponse(
        templates.get_template("error.html").render({
            "code": str(exc.status_code), "title": "Error",
            "message": str(exc.detail),
            "request": request,
        }),
        status_code=exc.status_code,
    )


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
