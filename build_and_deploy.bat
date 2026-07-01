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
echo [2/3] Building Flutter desktop app (obfuscated)...
cd /d "%~dp0desktop_app"
call flutter build windows --release --obfuscate --split-debug-info=build\debug-info
if %errorlevel% neq 0 (
    echo ERROR: Flutter build failed
    pause
    exit /b 1
)

echo.
echo [3/3] Updating scraper hash & copying to Release...
cd /d "%~dp0"
echo    Computing hashes...
python -c "import hashlib, re; eh=hashlib.sha256(open(r'%CD%\dist\scraper\scraper.exe','rb').read()).hexdigest(); ph=hashlib.sha256(open(r'%CD%\scraper.py','rb').read()).hexdigest(); print(f'SCRAPER_EXE_HASH={eh}'); d=open(r'%CD%\desktop_app\lib\screens\home_screen.dart','r',encoding='utf-8').read(); d=re.sub(r\"_expectedScraperExeHash = '[a-f0-9]+'\", f\"_expectedScraperExeHash = '{eh}'\", d); d=re.sub(r\"_expectedScraperPyHash = '[a-f0-9]+'\", f\"_expectedScraperPyHash = '{ph}'\", d); open(r'%CD%\desktop_app\lib\screens\home_screen.dart','w',encoding='utf-8').write(d); print(f'SCRAPER_PY_HASH={ph}'); print('home_screen.dart updated!')"
rmdir /s /q "%~dp0desktop_app\build\windows\x64\runner\Release\scraper" 2>nul
xcopy /e /i /q "%~dp0dist\scraper" "%~dp0desktop_app\build\windows\x64\runner\Release\scraper"
if %errorlevel% neq 0 (
    echo ERROR: Copy failed
    pause
    exit /b 1
)

echo.
echo ==============================================
echo   DONE! Hashes auto-updated in home_screen.dart.
echo   App: desktop_app\build\windows\x64\runner\Release\gmaps_scraper_desktop.exe
echo ==============================================
