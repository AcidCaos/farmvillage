import sys
import os

# Bundled data (extracted to a temp dir)

TMP_BUNDLED_DIR = sys._MEIPASS if getattr(sys, 'frozen', None) else "."

ASSETS_DIR = os.path.join(TMP_BUNDLED_DIR, "assets")
EMBEDS_DIR = os.path.join(TMP_BUNDLED_DIR, "embeds")
ASSETHASH_DIR = os.path.join(TMP_BUNDLED_DIR, "assethash")
STUB_ASSETS_DIR = os.path.join(TMP_BUNDLED_DIR, "stub")
PATCHED_ASSETS_DIR = os.path.join(TMP_BUNDLED_DIR, "patched")
TEMPLATES_DIR = os.path.join(TMP_BUNDLED_DIR, "templates")
XML_DIR = os.path.join(TMP_BUNDLED_DIR, "xml")
VILLAGES_DIR = os.path.join(TMP_BUNDLED_DIR, "villages")

# Not bundled data (next to server EXE)

BASE_DIR = "."

SAVES_DIR = os.path.join(BASE_DIR, "saves")
