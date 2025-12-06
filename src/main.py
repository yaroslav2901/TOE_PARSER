#!/usr/bin/env python3
"""
Головний скрипт для обробки графіків TOE (today + tomorrow)
"""
import argparse
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime
from telegram_notify import send_error
import downloader
import recognizer
import gener_im_full
import gener_im_1_G
from utils import clean_log, clean_old_files

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "main.log"
FULL_LOG_FILE = LOG_DIR / "full_log.log"
LOG_DIR.mkdir(exist_ok=True)


def log(message):
    """Логування в консоль та файл"""
    timestamp = datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} [main] {message}"
    print(line)
    with open(FULL_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def parse_args():
    """Парсинг аргументів командного рядка"""
    parser = argparse.ArgumentParser(description="TOE графіків processor")
    parser.add_argument(
        "--file", "-f", 
        type=str, 
        default=None, 
        help="Шлях до конкретного зображення для обробки"
    )
    parser.add_argument(
        "--download", "-d", 
        action="store_true", 
        help="Завантажити зображення з API перед обробкою"
    )
    parser.add_argument(
        "--both", "-b",
        action="store_true",
        help="Обробити обидва останні зображення з папки in/"
    )
    return parser.parse_args()


def delete_image(path):
    """Видалення файлу після помилки"""
    try:
        os.remove(path)
        log(f"🗑️ Видалено файл після помилки: {path}")
        send_error(f"🗑️ Видалено файл після помилки: {path}")
    except Exception as e:
        log(f"⚠️ Не вдалося видалити файл: {e}")
        send_error(f"⚠️ Не вдалося видалити файл: {e}")


def run_recognizer(image_path, label):
    """
    Запуск розпізнавання для одного зображення
    
    Args:
        image_path: шлях до файлу
        label: мітка (TODAY/TOMORROW)
    
    Returns:
        bool: True якщо успішно
    """
    try:
        log(f"▶️ [{label}] Запускаю розпізнавання. Файл: {image_path}")
        recognizer.run(image_path)
        log(f"✔️ [{label}] Розпізнавання успішно завершено")
        
        return True
    except Exception as e:
        log(f"❌ [{label}] Помилка розпізнавання: {e}")
        send_error(f"❌ [{label}] Помилка розпізнавання: {e}")
        import traceback
        log(f"Traceback:\n{traceback.format_exc()}")
        delete_image(image_path)
        return False


def run_generators():
    """
    Запуск генераторів зображень (один раз після обробки обох файлів)
    
    Returns:
        bool: True якщо успішно
    """
    try:
        # ---- ГЕНЕРАЦІЯ gener_im_full.py ----
        log("▶️ Запускаю gener_im_full.py")
        gener_im_full.main()
        log("✔️ gener_im_full.py завершено успішно")
    except Exception as e:
        log(f"❌ Помилка gener_im_full.py: {e}")
        send_error(f"❌ Помилка gener_im_full.py: {e}")
        import traceback
        log(f"Traceback:\n{traceback.format_exc()}")
        return False
    
    try:
        # ---- ГЕНЕРАЦІЯ gener_im_1_G.py ----
        log("▶️ Запускаю gener_im_1_G.py")
        gener_im_1_G.main()
        log("✔️ gener_im_1_G.py завершено успішно")
    except Exception as e:
        log(f"❌ Помилка gener_im_1_G.py: {e}")
        send_error(f"❌ Помилка gener_im_1_G.py: {e}")
        import traceback
        log(f"Traceback:\n{traceback.format_exc()}")
        return False
    
    return True


def run_github_upload():
    """
    Публікація результатів на GitHub
    """
    try:
        log("🚀 Запускаю upload_to_github_new.py")
        import upload_to_github_new
        upload_to_github_new.run_upload()
        log("✔️ upload_to_github_new.py завершено успішно")
    except Exception as e:
        log(f"❌ Помилка upload_to_github_new.py: {e}")
        send_error(f"❌ Помилка upload_to_github_new.py: {e}")
        import traceback
        log(f"Traceback:\n{traceback.format_exc()}")
        return False
    
    return True



def process_downloaded_images(files):
    """
    Обробка завантажених зображень
    
    Args:
        files: dict з ключами 'today' та 'tomorrow'
    
    Returns:
        bool: True якщо успішно
    """
    log("=" * 60)
    log("🔄 ОБРОБКА ЗАВАНТАЖЕНИХ ЗОБРАЖЕНЬ")
    log("=" * 60)
    
    # Перевірка чи є обидва файли
    #if not files.get("today") or not files.get("tomorrow"):
    #    log("⚠️ Не всі зображення завантажені")
    #    log(f"   TODAY: {'✓' if files.get('today') else '✗'}")
    #    log(f"   TOMORROW: {'✓' if files.get('tomorrow') else '✗'}")
    #    log("❌ Обробка скасована - потрібні обидва зображення")
    #    send_error("❌ Обробка скасована - не вистачає зображень (today або tomorrow)")
    #    return False
    
    log("✅ Обидва зображення завантажені, починаю обробку")
    
    success_count = 0
    
    # ---- ОБРОБКА TODAY ----
    if files["today"]:
        log("=" * 60)
        log("🔄 ОБРОБКА TODAY")
        log("=" * 60)
        if run_recognizer(files["today"], "TODAY"):
            success_count += 1
        else:
            log("❌ Помилка обробки TODAY")
    
    # ---- ОБРОБКА TOMORROW ----
    if files["tomorrow"]:
        log("=" * 60)
        log("🔄 ОБРОБКА TOMORROW")
        log("=" * 60)
        if run_recognizer(files["tomorrow"], "TOMORROW"):
            success_count += 1
        else:
            log("❌ Помилка обробки TOMORROW")
    
    # Перевірка чи обидва файли успішно оброблені
    #if success_count != 2:
    #    log(f"❌ Не всі файли оброблені успішно ({success_count}/2)")
    #    send_error(f"❌ Розпізнавання завершилось з помилками ({success_count}/2)")
    #    return False
    
    log(f"✅ 'success_count' зображення успішно розпізнано")
    
    # ---- ЗАПУСК ГЕНЕРАТОРІВ ----
    log("=" * 60)
    log("🎨 ГЕНЕРАЦІЯ РЕЗУЛЬТАТІВ")
    log("=" * 60)
    
    if not run_generators():
        log("❌ Помилка при генерації")
        send_error("❌ Помилка при генерації результатів")
        return False
    
    # ---- ПУБЛІКАЦІЯ НА GITHUB ----
    log("=" * 60)
    log("📤 ПУБЛІКАЦІЯ НА GITHUB")
    log("=" * 60)

    if not run_github_upload():
        log("❌ Помилка при публікації на GitHub")
        send_error("❌ Помилка при публікації на GitHub")
        return False
    
    log("=" * 60)
    log("✅ ВСЯ ОБРОБКА ЗАВЕРШЕНА УСПІШНО")
    log("=" * 60)
    
    return True


def get_latest_images(input_dir, count=2):
    """
    Знаходить N останніх PNG файлів в директорії
    
    Args:
        input_dir: шлях до директорії з зображеннями
        count: кількість файлів для повернення
    
    Returns:
        list: список шляхів до файлів
    """
    input_path = Path(input_dir)
    
    if not input_path.is_dir():
        log(f"❌ Папка не існує: {input_dir}")
        send_error(f"❌ Папка не існує: {input_dir}")
        return []

    # Шукаємо всі PNG файли
    files = list(input_path.glob("*.png")) + list(input_path.glob("*.PNG"))

    if not files:
        log(f"❌ У папці {input_dir} немає PNG зображень")
        send_error(f"❌ У папці {input_dir} немає PNG зображень")
        return []

    # Сортуємо за датою модифікації (новіші спочатку)
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    
    # Повертаємо N останніх
    latest_files = files[:count]
    
    log(f"📁 Знайдено {len(latest_files)} останніх файлів:")
    for i, f in enumerate(latest_files, 1):
        log(f"   {i}. {f}")
    
    return [str(f) for f in latest_files]


def process_single_file(image_path):
    """
    Обробка одного файлу (без генераторів)
    
    Args:
        image_path: шлях до файлу
    
    Returns:
        bool: True якщо успішно
    """
    log(f"🔄 Обробка одного файлу: {image_path}")
    
    if not os.path.exists(image_path):
        log(f"❌ Файл не існує: {image_path}")
        send_error(f"❌ Файл не існує: {image_path}")
        return False
    # ---- ОБРОБКА ФАЙЛУ ----
    run_recognizer(image_path, "SINGLE")
    # ---- ЗАПУСК ГЕНЕРАТОРІВ ----
    run_generators()
    # ---- ПУБЛІКАЦІЯ НА GITHUB ----
    run_github_upload()
    
    return True


def main():
    """Головна функція"""
    log("=" * 60)
    log("🚀 Запуск TOE pipeline")
    log("=" * 60)

    # Видаляємо зображення старше 5 днів у кількох папках
    folders = ["in", "DEBUG_IMAGES"]
    deleted_total = 0

    for folder in folders:
        deleted = clean_old_files(folder, 5, [".png", ".jpg", ".jpeg", ".webp"])
        count = len(deleted)
        deleted_total += count

        if count > 0:
            log(f"🗑️ Видалено {count} старих файлів у папці: {folder}")

    if deleted_total > 0:
        log(f"📦 Разом видалено {deleted_total} старих файлів у вибраних папках")

    # Чистимо  лог від даних старше 5 днів
    removed = clean_log(FULL_LOG_FILE, days=5)
    if removed is not None:
        if removed > 0:
            log(f"🧹 Логи очищено — видалено {removed} старих рядків")
    else:
        log("⚠️ Файла логів ще не існує — очищення пропущено")
    
    args = parse_args()

    # ---- РЕЖИМ 1: ЗАВАНТАЖЕННЯ З API ----
    if args.download:
        log("🌐 Режим: Завантаження зображень з TOE API")
        try:
            # Завантаження через downloader
            files = downloader.main()

           # --- ПЕРЕВІРКА ЧИ З'ЯВИЛИСЯ НОВІ ФАЙЛИ ---
            new_files = []
            for key in ("today", "tomorrow"):
                f = files.get(key)
                if f and (datetime.now().timestamp() - Path(f).stat().st_mtime) < 30:
                    new_files.append(f)

            if not new_files:
                log("⏩ Нові файли не з’явилися — припиняю роботу")
                return
                     
            # Обробка завантажених файлів
            if process_downloaded_images(files):
                log("=" * 60)
                log("✅ Pipeline завершено успішно")
                log("=" * 60)
            else:
                log("=" * 60)
                log("❌ Pipeline завершено з помилками")
                log("=" * 60)
            
        except Exception as e:
            log(f"❌ Критична помилка при завантаженні: {e}")
            send_error(f"❌ Критична помилка при завантаженні: {e}")
            import traceback
            log(f"Traceback:\n{traceback.format_exc()}")
        return

    # ---- РЕЖИМ 2: ОБРОБКА ДВОХ ОСТАННІХ ФАЙЛІВ ----
    if args.both:
        log("📁 Режим: Обробка двох останніх файлів з папки in/")
        input_dir = Path("in")
        image_paths = get_latest_images(input_dir, count=2)
        
        if len(image_paths) < 2:
            log("❌ Знайдено менше 2 файлів для обробки")
            send_error("❌ У папці in/ менше 2 файлів")
            return
        
        # Створюємо dict як після завантаження
        files = {
            "today": image_paths[1],      # старіший файл = today
            "tomorrow": image_paths[0]    # новіший файл = tomorrow
        }
        
        if process_downloaded_images(files):
            log("=" * 60)
            log("✅ Pipeline завершено успішно")
            log("=" * 60)
        else:
            log("=" * 60)
            log("❌ Pipeline завершено з помилками")
            log("=" * 60)
        return

    # ---- РЕЖИМ 3: ОБРОБКА КОНКРЕТНОГО ФАЙЛУ ----
    if args.file:
        log(f"📄 Режим: Обробка конкретного файлу")
        success = process_single_file(args.file)
        
        if success:
            log("=" * 60)
            log("✅ Pipeline завершено успішно")
            log("=" * 60)
        else:
            log("=" * 60)
            log("❌ Pipeline завершено з помилками")
            log("=" * 60)
        return

    # ---- РЕЖИМ 4: ОБРОБКА ОСТАННЬОГО ФАЙЛУ (за замовчуванням) ----
    log("📁 Режим: Обробка останнього файлу з папки in/")
    input_dir = Path("in")
    image_paths = get_latest_images(input_dir, count=1)
    
    if not image_paths:
        return

    success = process_single_file(image_paths[0])
    
    if success:
        log("=" * 60)
        log("✅ Pipeline завершено успішно")
        log("=" * 60)
    else:
        log("=" * 60)
        log("❌ Pipeline завершено з помилками")
        log("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("⚠️ Перервано користувачем (Ctrl+C)")
    except Exception as e:
        log(f"❌ Фатальна помилка: {e}")
        send_error(f"❌ Фатальна помилка: {e}")
        import traceback
        log(f"Traceback:\n{traceback.format_exc()}")