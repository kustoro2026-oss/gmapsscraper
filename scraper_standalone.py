"""
PyInstaller entry point — bundles Python + Playwright + Chromium.
Dipanggil oleh Flutter Desktop App sebagai scraper.exe.
"""

import sys
import os


def _setup():
    """Setup environment BEFORE any Playwright import."""
    if getattr(sys, 'frozen', False):
        bundle_dir = sys._MEIPASS

        # Tell Playwright to look for browsers in bundled directory
        browsers_dir = os.path.join(bundle_dir, 'browsers')
        if os.path.isdir(browsers_dir):
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers_dir

        # On PyInstaller, we need to explicitly tell stdout to use utf-8
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
