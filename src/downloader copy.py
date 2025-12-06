#!/usr/bin/env python3
"""
Головний скрипт для обробки графіків TOE
"""
import argparse
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime
from telegram_notify import send_error
import downloader

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


def process_image(image_path):
    """
    Обробка одного зображення через весь пайплайн
    
    Args:
        image_path: шлях до файлу зображення
    
    Returns:
        bool: True якщо обробка успішна, False якщо помилка
    """
    log(f"🔄 Початок обробки файлу: {image_path}")
    
    # Перевірка існування файлу
    if not os.path.exists(image_path):
        log(f"❌ Файл не існує: {image_path}")
        send_error(f"❌ Файл не існує: {image_path}")
        return False
    
    # TODO: Додати вашу логіку обробки
    # Наприклад:
    # - розпізнавання тексту з графіка
    # - парсинг даних
    # - генерація нових зображень
    # - завантаження на GitHub
    
    try:
        # ---- КРОК 1: РОЗПІЗНАВАННЯ ----
        log(f"▶️ Запускаю розпізнавання. Файл: {image_path}")
        # recognizer.run(image_path)  # Розкоментувати коли буде готово
        log("✔️ Розпізнавання успішно завершено")
    except Exception as e:
        log(f"❌ Помилка розпізнавання: {e}")
        send_error(f"❌ Помилка розпізнавання: {e}")
        delete_image(image_path)
        return False

    try:
        # ---- КРОК 2: КОНВЕРТАЦІЯ ----
        log("▶️ Запускаю конвертацію даних")
        # convert_data.main()  # Розкоментувати коли буде готово
        log("✔️ Конвертація завершена")
    except Exception as e:
        log(f"❌ Помилка конвертації: {e}")
        send_error(f"❌ Помилка конвертації: {e}")
        delete_image(image_path)
        return False
        
    try:
        # ---- КРОК 3: ГЕНЕРАЦІЯ ЗОБРАЖЕНЬ ----
        log("▶️ Запускаю генерацію результатів")
        # generate_output.main()  # Розкоментувати коли буде готово
        log("✔️ Генерація завершена")
    except Exception as e:
        log(f"❌ Помилка генерації: {e}")
        send_error(f"❌ Помилка генерації: {e}")
        delete_image(image_path)
        return False

    try:
        # ---- КРОК 4: ЗАВАНТАЖЕННЯ НА GITHUB ----
        log("▶️ Запускаю завантаження даних на GitHub")
        # upload_to_github.run()  # Розкоментувати коли буде готово
        log("✔️ Завантаження на GitHub успішно завершено")
    except Exception as e:
        log(f"❌ Помилка завантаження на GitHub: {e}")
        send_error(f"❌ Помилка завантаження на GitHub: {e}")
        delete_image(image_path)
        return False
    
    log(f"✅ Обробка файлу {image_path} завершена успішно")
    return True


def get_latest_image(input_dir):
    """
    Знаходить останній PNG файл в директорії
    
    Args:
        input_dir: шлях до директорії з зображеннями
    
    Returns:
        str: шлях до останнього файлу або None
    """
    input_path = Path(input_dir)
    
    if not input_path.is_dir():
        log(f"❌ Папка не існує: {input_dir}")
        send_error(f"❌ Папка не існує: {input_dir}")
        return None

    # Шукаємо всі PNG файли
    files = list(input_path.glob("*.png")) + list(input_path.glob("*.PNG"))

    if not files:
        log(f"❌ У папці {input_dir} немає PNG зображень")
        send_error(f"❌ У папці {input_dir} немає PNG зображень")
        return None

    # Знаходимо найновіший файл
    latest_file = max(files, key=lambda f: f.stat().st_mtime)
    log(f"📁 Знайдено найновіший файл: {latest_file}")
    
    return str(latest_file)


def main():
    """Головна функція"""
    log("=" * 60)
    log("🚀 Запуск TOE pipeline")
    log("=" * 60)
    
    args = parse_args()

    # ---- РЕЖИМ 1: ЗАВАНТАЖЕННЯ З API ----
    if args.download:
        log("🌐 Режим: Завантаження зображень з TOE API")
        try:
            downloader.main(process_callback=process_image)
            log("✅ Завантаження та обробка завершені")
            return
        except Exception as e:
            log(f"❌ Критична помилка при завантаженні: {e}")
            send_error(f"❌ Критична помилка при завантаженні: {e}")
            return

    # ---- РЕЖИМ 2: ОБРОБКА КОНКРЕТНОГО ФАЙЛУ ----
    if args.file:
        log(f"📄 Режим: Обробка конкретного файлу")
        image_path = args.file
    else:
        # ---- РЕЖИМ 3: ОБРОБКА ОСТАННЬОГО ФАЙЛУ З ПАПКИ ----
        log("📁 Режим: Обробка останнього файлу з папки in/")
        input_dir = Path("in")
        image_path = get_latest_image(input_dir)
        
        if not image_path:
            return

    # Запуск обробки
    success = process_image(image_path)
    
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