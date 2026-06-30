@echo off
chcp 65001 >nul
echo ==============================================
echo   Build & Deploy Desktop App + Scraper
echo ==============================================
echo.
echo [1/3] Building scraper.exe (PyInstaller)...
cd /d "%~dp0"
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
pyinstaller --onedir --name scraper --console --clean --noconfirm --collect-all playwright --add-data "scraper.py;." --add-data "city_coords.py;." --add-data "browsers;browsers" --hidden-import greenlet --hidden-import playwright.async_api --hidden-import playwright._impl --hidden-import playwright._impl._api_structures scraper_standalone.py
if %errorlevel% neq 0 (
    echo ERROR: PyInstaller build failed
    pause
    exit /b 1
)

echo.
echo [2/3] Building Flutter desktop app...
cd /d "%~dp0desktop_app"
call flutter build windows --release
if %errorlevel% neq 0 (
    echo ERROR: Flutter build failed
    pause
    exit /b 1
)

echo.
echo [3/3] Copying full scraper to Release...
rmdir /s /q "%~dp0desktop_app\build\windows\x64\runner\Release\scraper" 2>nul
xcopy /e /i /q "%~dp0dist\scraper" "%~dp0desktop_app\build\windows\x64\runner\Release\scraper"
if %errorlevel% neq 0 (
    echo ERROR: Copy failed
    pause
    exit /b 1
)

echo.
echo ==============================================
echo   DONE! App siap di:
echo   desktop_app\build\windows\x64\runner\Release\gmaps_scraper_desktop.exe
echo ==============================================
