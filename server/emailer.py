"""Email sender via Gmail SMTP — OTP, transaction confirmations, welcome emails."""

import os
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_FROM = os.environ.get("SMTP_FROM", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")


def _send(email: MIMEMultipart):
    """Send email in background thread — non-blocking."""
    def _do():
        try:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as s:
                s.login(SMTP_FROM, SMTP_PASSWORD)
                s.send_message(email)
            print(f"   [EMAIL] Sent to {email['To']} — {email['Subject']}")
        except Exception as e:
            print(f"   [EMAIL ERROR] {e}")

    if not SMTP_FROM or not SMTP_PASSWORD:
        print(f"   [EMAIL SKIP] SMTP not configured — would send: {email['Subject']} to {email['To']}")
        return
    threading.Thread(target=_do, daemon=True).start()


def send_welcome_email(to_email: str, name: str):
    """Send welcome email after first login."""
    msg = MIMEMultipart()
    msg["Subject"] = "Selamat Datang di GMaps Scraper!"
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    body = f"""Halo {name},

Selamat datang di GMaps Scraper!

Kamu sudah bisa langsung mencoba:
• 10x scraping gratis (trial)
• Desktop App untuk Windows
• Export CSV

Login ke dashboard: https://gmapsscraper.pro/dashboard

Kalau ada pertanyaan, balas email ini aja.

—
GMaps Scraper"""
    msg.attach(MIMEText(body, "plain"))
    _send(msg)


def send_payment_confirmation(to_email: str, name: str, package_name: str, amount: int, invoice_no: str):
    """Send payment confirmation after successful transaction."""
    msg = MIMEMultipart()
    msg["Subject"] = f"Pembayaran Berhasil — {package_name}"
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    body = f"""Halo {name},

Pembayaran kamu sudah berhasil dikonfirmasi.

Detail:
• Paket: {package_name}
• Jumlah: Rp {amount:,}
• Invoice: {invoice_no}

Quota sudah aktif dan siap digunakan di Desktop App.

Login: https://gmapsscraper.pro/dashboard

—
GMaps Scraper"""
    msg.attach(MIMEText(body, "plain"))
    _send(msg)


def send_verification_email(to_email: str, name: str, verify_url: str):
    """Send email verification link after registration."""
    msg = MIMEMultipart()
    msg["Subject"] = "Verifikasi Email — GMaps Scraper"
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    body = f"""Halo {name},

Terima kasih sudah mendaftar di GMaps Scraper!

Klik link di bawah untuk verifikasi email kamu:
{verify_url}

Link ini berlaku 24 jam. Kalau kamu tidak merasa mendaftar, abaikan email ini.

—
GMaps Scraper"""
    msg.attach(MIMEText(body, "plain"))
    _send(msg)
