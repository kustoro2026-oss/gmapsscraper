@echo off
chcp 65001 >nul
echo ==============================================
echo   Build scraper.exe (PyInstaller + Chromium)
echo ==============================================
echo.

REM ── Step 1: install deps ────────────────────────
echo [1/4] Installing Python dependencies...
pip install pyinstaller playwright --quiet
if %errorlevel% neq 0 (
    echo ERROR: pip install failed
    pause
    exit /b 1
)

REM ── Step 2: download Chromium ───────────────────
echo [2/4] Downloading Chromium browser...
playwright install chromium
if %errorlevel% neq 0 (
    echo ERROR: playwright install chromium failed
    pause
    exit /b 1
)

REM ── Step 3: prepare browsers folder ──────────────
echo [3/4] Preparing bundled browsers folder...
if exist browsers rmdir /s /q browsers
mkdir browsers

REM Find Chromium in ms-playwright
for /d %%d in ("%USERPROFILE%\AppData\Local\ms-playwright\chromium-*") do (
    echo    Copying %%~nxd...
    xcopy /e /i /q "%%d" "browsers\%%~nxd" >nul
)

REM Find ffmpeg in ms-playwright
for /d %%d in ("%USERPROFILE%\AppData\Local\ms-playwright\ffmpeg-*") do (
    echo    Copying %%~nxd...
    xcopy /e /i /q "%%d" "browsers\%%~nxd" >nul
)

REM Find winldd in ms-playwright (if exists)
for /d %%d in ("%USERPROFILE%\AppData\Local\ms-playwright\winldd-*") do (
    echo    Copying %%~nxd...
    xcopy /e /i /q "%%d" "browsers\%%~nxd" >nul
)

REM ── Step 4: PyInstaller build ────────────────────
echo [4/4] Building scraper.exe with PyInstaller...

REM Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

pyinstaller ^
    --onedir ^
    --name scraper ^
    --console ^
    --clean ^
    --noconfirm ^
    --collect-all playwright ^
    --add-data "scraper.py;." ^
    --add-data "city_coords.py;." ^
    --add-data "browsers;browsers" ^
    --hidden-import greenlet ^
    --hidden-import playwright.async_api ^
    --hidden-import playwright._impl ^
    --hidden-import playwright._impl._api_structures ^
    scraper_standalone.py

if %errorlevel% neq 0 (
    echo ERROR: PyInstaller build failed
    pause
    exit /b 1
)

echo.
echo ==============================================
echo   SUCCESS!
echo   Output: dist\scraper\scraper.exe
echo.
echo   Copy ke folder Release bersama .exe Flutter:
echo   xcopy /e /i /q dist\scraper build\windows\x64\runner\Release\scraper
echo ==============================================
pause
