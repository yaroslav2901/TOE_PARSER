# src/config.py
from zoneinfo import ZoneInfo
import os
from pathlib import Path
# ----------------- НАЛАШТУВАННЯ ЧАСУ -----------------
TIMEZONE = ZoneInfo("Europe/Kyiv")
REGION = "Ternopiloblenerho"   # <<<<<<<<<<<<<<<<<< ОБЛЕНЕРГО
#BASE_DIR = "/home/yaroslav/bots/LOE_PARSER"
BASE_DIR = Path(__file__).parent.parent.absolute()
SOURCE_JSON = os.path.join(BASE_DIR, "out", f"{REGION}.json")
SOURCE_IMAGES = os.path.join(BASE_DIR, "out/images")

REPO_DIR = "/home/yaroslav/bots/OE_OUTAGE_DATA"
DATA_DIR = os.path.join(REPO_DIR, "data")
IMAGES_DIR = os.path.join(REPO_DIR, f"images/{REGION}")
LOG_FILE = os.path.join(BASE_DIR, "logs", "full_log.log")

