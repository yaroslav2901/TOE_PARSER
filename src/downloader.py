#!/usr/bin/env python3
"""
TOE Downloader - просто завантажує 2 картинки (today + tomorrow)
"""
import requests
import hashlib
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from time import sleep

TZ = ZoneInfo("Europe/Kyiv")

API_TODAY = "https://api-toe-poweron.inneti.net/api/options?option_key=pw_gpv_image_today"
API_TMR = "https://api-toe-poweron.inneti.net/api/options?option_key=pw_gpv_image_tomorrow"

OUT_DIR = Path("in")
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "full_log.log"

# Налаштування ретеншену
IMAGE_RETENTION_DAYS = 2
LOG_RETENTION_DAYS = 14

OUT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)


def log(msg: str):
    """Функція логування"""
    timestamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} [downloader] {msg}"

    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def cleanup_old_files():
    """Видалення старих файлів"""
    now = datetime.now()
    
    # Видалення старих логів
    for log_file in LOG_DIR.glob("*.log"):
        if (now - datetime.fromtimestamp(log_file.stat().st_mtime)).days > LOG_RETENTION_DAYS:
            log_file.unlink()
            log(f"Видалено старий лог: {log_file}")
    
    # Видалення старих зображень
    for img_file in OUT_DIR.glob("*"):
        if (now - datetime.fromtimestamp(img_file.stat().st_mtime)).days > IMAGE_RETENTION_DAYS:
            img_file.unlink()
            log(f"Видалено старе зображення: {img_file}")


def get_img_url(api_url, retries=3):
    """Отримує URL картинки з API з можливістю повтору"""
    for attempt in range(retries):
        try:
            log(f"Запит до API: {api_url} (спроба {attempt + 1}/{retries})")
            resp = requests.get(
                api_url, 
                headers={"Accept": "application/json"},
                timeout=10
            )
            resp.raise_for_status()

            try:
                data = resp.json()
            except Exception as e:
                log(f"❌ JSON decode error: {e}")
                log(f"RAW: {resp.text}")
                raise

            log(f"Отримано JSON: {data}")

            val = None

            # Якщо API повертає список
            if isinstance(data, list) and len(data) > 0:
                if "value" in data[0]:
                    val = data[0]["value"]

            # Якщо API повертає словник
            elif isinstance(data, dict):
                if "value" in data:
                    val = data["value"]

            # Якщо не знайшли або порожня строка
            if not val or val == "":
                log(f"⚠️ Зображення відсутнє - 'value' порожнє або не знайдено в JSON")
                return None

            full_url = "https://api-toe-poweron.inneti.net" + val
            log(f"URL картинки: {full_url}")

            return full_url

        except requests.exceptions.RequestException as e:
            log(f"❌ Помилка API запиту (спроба {attempt + 1}): {e}")
            if attempt < retries - 1:
                sleep(2)
            else:
                raise
        except Exception as e:
            log(f"❌ Помилка обробки відповіді (спроба {attempt + 1}): {e}")
            if attempt < retries - 1:
                sleep(2)
            else:
                raise


def download(url, label, retries=3):
    """
    Завантажує файл з можливістю повтору та MD5 хешуванням
    
    Args:
        url: URL для завантаження
        label: мітка (today/tomorrow) для логування
        retries: кількість спроб
    
    Returns:
        str: шлях до збереженого файлу або None якщо помилка
    """
    # Перевірка, що URL починається з правильного домену
    if not url.startswith("https://api-toe-poweron.inneti.net"):
        log(f"⚠️ УВАГА: Підозрілий URL: {url}")
        return None

    for attempt in range(retries):
        try:
            log(f"⬇️ Завантажую картинку ({label}): {url} (спроба {attempt + 1}/{retries})")
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()

            content = resp.content
            
            # Обчислюємо MD5
            md5_hash = hashlib.md5(content).hexdigest()
            ext = Path(url).suffix.lower() or ".png"
            output_file = OUT_DIR / f"{md5_hash}{ext}"
            
            # Перевірка чи файл вже існує
            if output_file.exists():
                log(f"    Файл {output_file.name} вже існує — пропускаємо завантаження")
                return #str(output_file)


            
            # Зберігаємо
            output_file.write_bytes(content)
            
            file_size = len(content) / 1024  # KB
            log(f"✔ Збережено як {output_file} ({file_size:.2f} KB)")
            
            return str(output_file)

        except requests.exceptions.RequestException as e:
            log(f"❌ Помилка завантаження (спроба {attempt + 1}): {e}")
            if attempt < retries - 1:
                sleep(2)
            else:
                log(f"❌ Не вдалося завантажити {label} після {retries} спроб")
                return None
        except Exception as e:
            log(f"❌ Несподівана помилка (спроба {attempt + 1}): {e}")
            if attempt < retries - 1:
                sleep(2)
            else:
                return None


def main():
    """
    Головна функція - завантажує today + tomorrow
    
    Returns:
        dict: {"today": "path/to/file.png", "tomorrow": "path/to/file.png"}
              або None для файлів які не вдалося завантажити
    """
    log("🚀 Старт TOE downloader")
    
    # Очищення старих файлів
    cleanup_old_files()
    
    result = {"today": None, "tomorrow": None}

    try:
        # ---- ЗАВАНТАЖЕННЯ СЬОГОДНІШНЬОЇ КАРТИНКИ ----
        log("=" * 60)
        log("📥 Завантаження картинки на СЬОГОДНІ (TODAY)")
        log("=" * 60)
        try:
            today_url = get_img_url(API_TODAY)
            if today_url:
                today_file = download(today_url, "today")
                result["today"] = today_file
                if today_file:
                    log(f"✅ TODAY завантажено: {today_file}")
                else:
                    log(f"❌ TODAY не вдалося завантажити")
            else:
                log(f"⚠️ TODAY зображення відсутнє на сервері")
        except Exception as e:
            log(f"❌ Помилка при завантаженні TODAY: {e}")

        # ---- ЗАВАНТАЖЕННЯ ЗАВТРАШНЬОЇ КАРТИНКИ ----
        log("=" * 60)
        log("📥 Завантаження картинки на ЗАВТРА (TOMORROW)")
        log("=" * 60)
        try:
            tomorrow_url = get_img_url(API_TMR)
            if tomorrow_url:
                tomorrow_file = download(tomorrow_url, "tomorrow")
                result["tomorrow"] = tomorrow_file
                if tomorrow_file:
                    log(f"✅ TOMORROW завантажено: {tomorrow_file}")
                else:
                    log(f"❌ TOMORROW не вдалося завантажити")
            else:
                log(f"⚠️ TOMORROW зображення відсутнє на сервері")
        except Exception as e:
            log(f"❌ Помилка при завантаженні TOMORROW: {e}")

        # ---- ПІДСУМОК ----
        log("=" * 60)
        success_count = sum(1 for v in result.values() if v is not None)
        log(f"📊 Підсумок завантаження: {success_count}/2 успішно")
        log(f"   TODAY: {'✓' if result['today'] else '✗'}")
        log(f"   TOMORROW: {'✓' if result['tomorrow'] else '✗'}")
        log("=" * 60)
        
        if success_count == 2:
            log("✅ Всі файли завантажено успішно")
        elif success_count > 0:
            log("⚠️ Частково успішно")
        else:
            log("❌ Не вдалося завантажити жодного файлу")

    except Exception as e:
        log(f"❌ КРИТИЧНА ПОМИЛКА: {e}")
        import traceback
        log(f"Traceback:\n{traceback.format_exc()}")
    
    log("Роботу завершено")
    log("")  # Порожній рядок для роздільника
    
    return result


if __name__ == "__main__":
    try:
        files = main()
        if files:
            print(f"\nЗавантажені файли:")
            print(f"  Today: {files.get('today', 'не завантажено')}")
            print(f"  Tomorrow: {files.get('tomorrow', 'не завантажено')}")
        
    except KeyboardInterrupt:
        log("Перервано користувачем")
    except Exception as e:
        log(f"Фатальна помилка: {e}")
        exit(0)