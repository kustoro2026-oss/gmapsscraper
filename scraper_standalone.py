"""
PyInstaller entry point — bundles Python + Playwright + Chromium.
Dipanggil oleh Flutter Desktop App sebagai scraper.exe.
"""

import sys
import os


def _setup():
    """Setup environment BEFORE any Playwright import."""
    # CRITICAL: force stdout line-buffering for piped Process.start()
    # Without this, Flutter sees no output until process exits
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(line_buffering=True)
        except Exception:
            pass

    if getattr(sys, 'frozen', False):
        bundle_dir = sys._MEIPASS

        # Tell Playwright to look for browsers in bundled directory
        browsers_dir = os.path.join(bundle_dir, 'browsers')
        if os.path.isdir(browsers_dir):
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers_dir

            # Explicitly find chrome-headless-shell.exe for faster launch
            for root, dirs, files in os.walk(browsers_dir):
                if 'chrome-headless-shell.exe' in files:
                    exe_path = os.path.join(root, 'chrome-headless-shell.exe')
                    os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH'] = exe_path
                    break
                elif 'chrome.exe' in files:
                    exe_path = os.path.join(root, 'chrome.exe')
                    os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH'] = exe_path
                    break

        # On PyInstaller, ensure stdout uses utf-8
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    # Ensure city_coords.py is importable (bundled via --add-data)
    if getattr(sys, 'frozen', False):
        sys.path.insert(0, sys._MEIPASS)


_setup()

# Import scraper AFTER env setup
from scraper import main  # noqa: E402

if __name__ == '__main__':
    main()
