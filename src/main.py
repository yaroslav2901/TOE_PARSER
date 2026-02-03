#!/usr/bin/env python3
import os
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta

# Твої модулі
from telegram_notify import send_error, send_photo
import gener_im_full
import gener_im_1_G
from utils import clean_log, clean_old_files
from toe_api_parser import ToeOutageParser

# Налаштування
json_path = "out/Ternopiloblenerho.json"
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
FULL_LOG_FILE = LOG_DIR / "full_log.log"

def log(message):
    timestamp = datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} [main] {message}"
    print(line)
    with open(FULL_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def sort_full_data(raw_data_map):
    """Сортує спочатку дати (timestamps), а потім групи (GPV)"""
    sorted_timestamps = sorted(raw_data_map.keys(), key=int)
    final_data = {}
    for ts in sorted_timestamps:
        groups = raw_data_map[ts]
        sorted_group_keys = sorted(
            groups.keys(), 
            key=lambda x: [int(s) for s in x.replace('GPV', '').split('.') if s.isdigit()]
        )
        final_data[ts] = {k: groups[k] for k in sorted_group_keys}
    return final_data

def get_api_data_and_save():
    log("🌐 Запит даних з API...")
    now = datetime.now(ZoneInfo("Europe/Kyiv"))
    log("⏳ Формування часових меж...")
    after = ((now - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0).isoformat())
    log(f"⏳ After: {after}")
    before = ((now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat())
    log(f"⏳ Before: {before}")
    
    raw_data_map = ToeOutageParser.fetch_all_groups(before, after)
    
    if not raw_data_map:
        log("❌ Даних не отримано. Оновлення скасовано.")
        return None, False

    data_map = sort_full_data(raw_data_map)

    # --- ПЕРЕВІРКА НА ЗМІНИ ---
    has_changes = True
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                old_json = json.load(f)
                # Порівнюємо суто вміст графіків (data)
                if old_json.get("fact", {}).get("data") == data_map:
                    has_changes = False
        except Exception as e:
            log(f"⚠️ Помилка читання старого файлу: {e}")

    full_json = {
        "regionId": "Ternopil",
        #"lastUpdated": datetime.now(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
        "lastUpdated": datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "fact": {
            "data": data_map,
            "update": now.strftime("%d.%m.%Y %H:%M"),
            "today": int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        },
        "preset": {
            "time_zone": {str(i): [f"{i-1:02}-{i:02}", f"{i-1:02}:00", f"{i:02}:00"] for i in range(1, 25)},
            "time_type": {
                "yes": "Світло є", 
                "no": "Світла немає", 
                "maybe": "Можливе відключення",
                "first": "Світла не буде перші 30 хв.", 
                "second": "Світла не буде другі 30 хв",
                "mfirst": "Можливе відключення перші 30 хв.", 
                "msecond": "Можливе відключення другі 30 хв."
            }
        }
    }

    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(full_json, f, ensure_ascii=False, indent=2)
    
    log(f"✅ JSON оновлено. Зміни виявлено: {has_changes}")
    return full_json, has_changes

def send_tg_updates(json_data):
    try:
        ts_list = sorted(json_data["fact"]["data"].keys())
        today_ts = json_data["fact"]["today"]
        has_tomorrow = any(int(ts) > today_ts for ts in ts_list)
        
        if has_tomorrow:
            photo = "out/images/gpv-all-tomorrow.png"
            caption = "🔄 <b>Тернопільобленерго</b>\nГрафік на завтра\n#Тернопільобленерго"
        else:
            photo = "out/images/gpv-all-today.png"
            caption = "🔄 <b>Тернопільобленерго</b>\nГрафік на сьогодні\n#Тернопільобленерго"

        if os.path.exists(photo):
            send_photo(photo, caption)
            log(f"📱 Фото відправлено в ТГ: {photo}")
    except Exception as e:
        log(f"⚠️ Помилка відправки в ТГ: {e}")

def main():
    log("=== ПОЧАТОК ЦИКЛУ ===")
    clean_old_files("DEBUG_IMAGES", 3, [".png"])
    clean_log(FULL_LOG_FILE, days=2)

    data, has_changes = get_api_data_and_save()
    
    if data and has_changes:
        try:
            log("🎨 Дані змінилися! Генерація зображень...")
            gener_im_full.main()
            gener_im_1_G.main()
            
            log("☁️ Завантаження на GitHub...")
            try:
                import upload_to_github
                upload_to_github.run_upload()
            except ImportError:
                log("⚠️ Скрипт upload_to_github не знайдено")

            send_tg_updates(data)
        except Exception as e:
            log(f"❌ Критична помилка генерації: {e}")
            send_error(f"Помилка в пайплайні: {e}")
    elif data and not has_changes:
        log("😴 Графік не змінився. Генерацію та відправку пропущено.")

    log("=== ЗАВЕРШЕНО ===")

if __name__ == "__main__":
    main()