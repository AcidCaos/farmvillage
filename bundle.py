import sys
import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_BUNDLED_DIR = BASE_DIR

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    print(" [+] Running in bundle/packaged mode")
    TMP_BUNDLED_DIR = sys._MEIPASS
    # PyInstaller broke the __file__ attribute of the entry-point script which
    # used to point to the basename (where the EXE was located). Now it points
    # to the module's full path within the bundle directory. We need to point
    # it to the parent directory of the bundle, not the bundle itself.
    # Source: https://pyinstaller.org/en/stable/runtime-information.html
    # This change is relevant because Flask uses the __file__ attribute to find
    # the root directory of the application, and thus assets returned by functions
    # such as send_from_directory would include the bundle (or _internal) path.
    # We'll set Flask app.root_path to BASE_DIR instead of the default __file__ value
    # as a workaround.
    BASE_DIR = os.path.dirname(BASE_DIR)

# Bundled data (extracted to a temp dir)

PATCHED_ASSETS_DIR = os.path.join(TMP_BUNDLED_DIR, "patched")
TEMPLATES_DIR = os.path.join(TMP_BUNDLED_DIR, "templates")
VILLAGES_DIR = os.path.join(TMP_BUNDLED_DIR, "villages")
XML_DIR = os.path.join(TMP_BUNDLED_DIR, "xml")
EMBEDS_DIR = os.path.join(TMP_BUNDLED_DIR, "embeds")
ASSETHASH_DIR = os.path.join(TMP_BUNDLED_DIR, "assethash")

# Not bundled data (next to server EXE)

SAVES_DIR = os.path.join(BASE_DIR, "saves")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
CACHE_DIR = os.path.join(BASE_DIR, "cache")
TMP_DIR = os.path.join(BASE_DIR, "tmp")
