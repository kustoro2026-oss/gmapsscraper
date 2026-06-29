@echo off
chcp 65001 >nul
title GMaps Scraper

:: ── Cek Visual C++ Redistributable ──────────────────────────────
:: Flutter Windows app membutuhkan vcruntime140.dll.
:: Kalau DLL ada di folder app (distribusi bundle), langsung bisa jalan.
:: Kalau gak ada di folder app, cek di system.

set "DLL_FOUND=0"

:: Cek di folder app dulu
if exist "%~dp0vcruntime140.dll" set "DLL_FOUND=1"

:: Kalau gak ada, cek system32
if %DLL_FOUND%==0 (
    reg query "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" /v Installed 2>nul | findstr "0x1" >nul
    if %errorlevel%==0 set "DLL_FOUND=1"
)

if %DLL_FOUND%==1 (
    start "" "%~dp0gmaps_scraper_desktop.exe"
    exit /b 0
)

:: ── VC++ gak ketemu — tampilkan pesan ──────────────────────────
echo.
echo ═══════════════════════════════════════════════════════════════
echo   Visual C++ Redistributable tidak ditemukan!
echo.
echo   Aplikasi ini membutuhkan Microsoft Visual C++ Redistributable.
echo   Silakan download dan install versi terbaru:
echo.
echo   https://aka.ms/vs/17/release/vc_redist.x64.exe
echo.
echo   Setelah install, jalankan ulang aplikasi ini.
echo ═══════════════════════════════════════════════════════════════
echo.

:: Buka link download
start "" "https://aka.ms/vs/17/release/vc_redist.x64.exe"

pause
exit /b 1
