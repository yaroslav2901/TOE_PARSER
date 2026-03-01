import urllib.request
import ssl
from datetime import datetime, timedelta
import json
import os
import time
import base64
from zoneinfo import ZoneInfo
from pathlib import Path
import random
from telegram_notify import send_message

class ToeOutageParser:
    #BASE_URL = "https://api-toe-poweron.inneti.net/api"
    BASE_URL = "https://api-poweron.toe.com.ua/api"
    LOG_DIR = Path("logs")
    LOG_DIR.mkdir(exist_ok=True)
    FULL_LOG_FILE = LOG_DIR / "full_log.log"

    @staticmethod
    def log(message):
        timestamp = datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%Y-%m-%d %H:%M:%S")
        line = f"{timestamp} [toe_api_parser] {message}"
        print(line)
        try:
            with open(ToeOutageParser.FULL_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            print(f"Не вдалося записати лог: {e}")

    # Співвідношення (cityId, streetId) до груп
    GROUP_KEYS = {
        (22212,   41980):  ['1.1'], #Андрушівка (Шумська ОТГ), Грибелька
        (1032,  47732):    ['1.2', '4.1'], # Тернопіль (Тернопільська ОТГ), Андрея Шептицького
        #(21743,   38099):  ['2.1'], # Андруга (Кременецька ОТГ), Гайова
        (21185,   33899):  ['2.1'], # Базниківка (Саранчуківська ОТГ), вул. Тиха
        (1032,  44479):    ['2.2', '5.2'], # Тернопіль (Тернопільська ОТГ), 15 Квітня
        (21935, 39514):    ['3.1'], # Голотки (Скориківська ОТГ), Зарваниця
        (1032,  10188):    ['3.2'], # Тернопіль (Тернопільська ОТГ), Безкоровайного
        (1032,  50611):    ['4.2'], # Тернопіль (Тернопільська ОТГ), Бродівська-Гріга
        (21427,   40845):  ['5.1'], #  Августівка (Зборівська ОТГ), Бічна 
        (21707, 37937):    ['6.1'], # Башуки (Лопушненська ОТГ), Бригадна
        (21534,  36593):   ['6.2'], # Горби (Козівська ОТГ), Горби    
    }

    @staticmethod
    def build_debug_key(city_id: int, street_id: int) -> str:
        return base64.b64encode(f"{city_id}/{street_id}".encode()).decode()

    @staticmethod
    def process_times(times: dict):
        """Перетворює 48 точок API у 24 години для JSON"""
        hours_map = {}
        for h in range(1, 25):
            t1 = f"{h-1:02d}:00"
            t2 = f"{h-1:02d}:30"
            
            v1 = str(times.get(t1, "0"))
            v2 = str(times.get(t2, "0"))

            # Логіка визначення статусу
            if v1 == "1" and v2 == "1":
                status = "no"
            elif v1 == "0" and v2 == "0":
                status = "yes"
            elif v1 == "10" and v2 == "10":
                status = "maybe" 
            elif v1 == "10":
                status = "mfirst"
            elif v2 == "10":
                status = "msecond"
            elif v1 == "1" and v2 == "0":
                status = "first"
            elif v1 == "0" and v2 == "1":
                status = "second"
            else:
                status = "yes"
            
            hours_map[str(h)] = status
        return hours_map

    @staticmethod
    def fetch_all_groups(before: str, after: str):
        ToeOutageParser.log(f"🚀 Початок завантаження графіків (Before: {before}, After: {after})")
        data_structure = {}
        now_ts = int(time.time() * 1000)
        processed_count = 0

        for i, ((city_id, street_id), expected_groups) in enumerate(ToeOutageParser.GROUP_KEYS.items()):
            key = ToeOutageParser.build_debug_key(city_id, street_id)
            #tp = f"{now_ts + i}%D0%B0"
            #tp = f"{now_ts + i}"
            tp = f"{now_ts + random.randint(0,500)}"
            query = f"before={before.replace('+', '%2B')}&after={after.replace('+', '%2B')}&group[]={expected_groups[0]}&time={tp}"
            url = f"{ToeOutageParser.BASE_URL}/a_gpv_g?{query}"
            ToeOutageParser.log(f"url: {url}")

            headers = {
                'Accept': 'application/json, text/plain, */*',
                #'Origin': 'https://toe-poweron.inneti.net',
                'Origin': 'https://poweron.toe.com.ua',
                'X-debug-key': key,
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }

            try:
                #ToeOutageParser.log(f"🛰 Запит для {city_id}/{street_id} (Групи: {expected_groups})")
                
                req = urllib.request.Request(url, headers=headers)
                ctx = ssl.create_default_context()
                
                with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                    raw_data = json.loads(resp.read().decode("utf-8"))

                members = raw_data.get("hydra:member", [])
                if not members:
                    ToeOutageParser.log(f"⚠️ Порожня відповідь для {city_id}/{street_id}")
                    continue

                for member in members:
                    raw_date = member.get("dateGraph", "").split("T")[0]
                    if not raw_date:
                        continue
                    
                    dt = datetime.strptime(raw_date, "%Y-%m-%d").replace(tzinfo=ZoneInfo("Europe/Kyiv"))
                    ts_key = str(int(dt.timestamp()))

                    if ts_key not in data_structure:
                        data_structure[ts_key] = {}

                    data_json = member.get("dataJson", {})
                    for raw_group_name, group_info in data_json.items():
                        clean_name = raw_group_name.split("#")[0]
                        full_name = f"GPV{clean_name}"
                        
                        times_dict = group_info.get("times", {})
                        processed_times = ToeOutageParser.process_times(times_dict)
                        
                        data_structure[ts_key][full_name] = processed_times
                        processed_count += 1
                
                #ToeOutageParser.log(f"✅ Дані для {city_id}/{street_id} успішно оброблені")

            except Exception as e:
                ToeOutageParser.log(f"❌ Помилка API ({city_id}/{street_id}): {str(e)}")
                send_message(f"❌ Помилка API ({city_id}/{street_id}): {str(e)}", silent=True)

        
        ToeOutageParser.log(f"🏁 Завершено. Оброблено груп: {processed_count}. Дати: {list(data_structure.keys())}")
        
        # ============ ПЕРЕВІРКА ВСІХ 12 ГРУП ============
        all_expected_groups = set()
        for groups_list in ToeOutageParser.GROUP_KEYS.values():
            all_expected_groups.update(groups_list)

        # Збираємо які групи фактично отримали
        found_groups = set()
        for date_data in data_structure.values():
            for group_name in date_data.keys():
                # Видаляємо префікс "GPV" щоб порівняти
                clean_name = group_name.replace("GPV", "")
                found_groups.add(clean_name)

        missing_groups = all_expected_groups - found_groups

        if missing_groups:
            missing_list = ', '.join(sorted(missing_groups))
            warning_msg = f"⚠️ Не знайдено дані для груп: {missing_list} (знайдено {len(found_groups)}/12)"
            ToeOutageParser.log(warning_msg)
            try:
                #send_message(warning_msg, silent=True)
                ToeOutageParser.log(f"⚠️ Вимкнено відправку Telegram повідомлень про відсутні групи ")
            except Exception as e:
                ToeOutageParser.log(f"❌ Не вдалося відправити Telegram повідомлення: {e}")
        else:
            ToeOutageParser.log(f"✅ Всі 12 груп успішно знайдені")

        # --- ВИВІД УСІХ ДАНИХ У ЛОГ ---
        # Форматуємо весь словник у гарний JSON-рядок
        #full_data_json = json.dumps(data_structure, ensure_ascii=False, indent=4)
        #ToeOutageParser.log(f"📊 ПОВНИЙ ДАМП ОТРИМАНИХ ДАНИХ:\n{full_data_json}")
        # ------------------------------
        return data_structure