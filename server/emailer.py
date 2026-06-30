"""Email sender via Resend API — non-blocking with httpx."""

import os
import threading
import httpx

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM = os.environ.get("RESEND_FROM", "noreply@gmapsscraper.pro")
RESEND_API_URL = "https://api.resend.com/emails"


def _send(subject: str, to_email: str, body: str):
    """Send email via Resend API in background thread — non-blocking."""
    def _do():
        try:
            payload = {
                "from": RESEND_FROM,
                "to": [to_email],
                "subject": subject,
                "html": body.replace("\n", "<br>"),
            }
            resp = httpx.post(
                RESEND_API_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            if resp.status_code == 200:
                print(f"   [EMAIL] Sent to {to_email} — {subject}")
            elif resp.status_code == 422:
                print(f"   [EMAIL ERROR] 422 — from='{RESEND_FROM}'. Pastikan domain sudah diverifikasi di resend.com/domains")
                print(f"   [EMAIL ERROR] Response: {resp.text[:300]}")
            else:
                print(f"   [EMAIL ERROR] {resp.status_code}: {resp.text[:300]}")
        except Exception as e:
            print(f"   [EMAIL ERROR] {e}")

    if not RESEND_API_KEY:
        print(f"   [EMAIL SKIP] RESEND_API_KEY not configured — would send: {subject} to {to_email}")
        return
    threading.Thread(target=_do, daemon=True).start()


def send_welcome_email(to_email: str, name: str):
    body = f"""Halo {name},<br><br>
Selamat datang di GMaps Scraper!<br><br>
Kamu sudah bisa langsung mencoba:<br>
• 10x scraping gratis (trial)<br>
• Desktop App untuk Windows<br>
• Export CSV<br><br>
Login ke dashboard: https://gmapsscraper.pro/dashboard<br><br>
Kalau ada pertanyaan, balas email ini aja.<br><br>
—<br>GMaps Scraper"""
    _send("Selamat Datang di GMaps Scraper!", to_email, body)


def send_payment_confirmation(to_email: str, name: str, package_name: str, amount: int, invoice_no: str):
    body = f"""Halo {name},<br><br>
Pembayaran kamu sudah berhasil dikonfirmasi.<br><br>
Detail:<br>
• Paket: {package_name}<br>
• Jumlah: Rp {amount:,}<br>
• Invoice: {invoice_no}<br><br>
Quota sudah aktif dan siap digunakan di Desktop App.<br><br>
Login: https://gmapsscraper.pro/dashboard<br><br>
—<br>GMaps Scraper"""
    _send(f"Pembayaran Berhasil — {package_name}", to_email, body)


def send_verification_email(to_email: str, name: str, verify_url: str):
    body = f"""Halo {name},<br><br>
Terima kasih sudah mendaftar di GMaps Scraper!<br><br>
Klik link di bawah untuk verifikasi email kamu:<br>
<a href="{verify_url}">{verify_url}</a><br><br>
Link ini berlaku 24 jam. Kalau kamu tidak merasa mendaftar, abaikan email ini.<br><br>
—<br>GMaps Scraper"""
    _send("Verifikasi Email — GMaps Scraper", to_email, body)
