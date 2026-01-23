from datetime import datetime, timedelta
import os
from typing import List

from datetime import datetime, timedelta

def clean_log(log_file_path: str, days: int = 7):
    cutoff_time = datetime.now() - timedelta(days=days)
    kept_lines = []
    removed_count = 0

    keep_block = False  # ❗ починаємо НЕ зберігати, поки не знайдемо timestamp

    try:
        with open(log_file_path, "r", encoding="utf-8-sig") as f:
            for line in f:

                is_timestamp = False

                if len(line) >= 19:
                    try:
                        ts = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
                        is_timestamp = True
                        keep_block = ts >= cutoff_time
                    except ValueError:
                        pass

                # ❌ до першого timestamp — усе відкидаємо
                if not is_timestamp and not kept_lines:
                    removed_count += 1
                    continue

                if keep_block:
                    kept_lines.append(line)
                else:
                    removed_count += 1

        with open(log_file_path, "w", encoding="utf-8") as f:
            f.writelines(kept_lines)

        return removed_count

    except FileNotFoundError:
        return None


def clean_old_files(target_dir: str, days: int = 7, extensions: List[str] = None):
    """
    Видаляє файли старше `days` днів у вказаній папці.
    
    target_dir: шлях до папки
    days: кількість днів
    extensions: список розширень файлів (None = всі)

    Приклад:
        clean_old_files("DEBUG_IMAGES", 7, [".png", ".jpg"])
        clean_old_files("in", 3)
        clean_old_files("/home/user/tmp", 1, [".log"])
    """

    cutoff_time = datetime.now() - timedelta(days=days)
    removed_files = []

    if not os.path.exists(target_dir):
        return removed_files

    for filename in os.listdir(target_dir):

        # якщо є фільтр за типом файлів — перевіряємо
        if extensions:
            if not any(filename.lower().endswith(ext.lower()) for ext in extensions):
                continue

        file_path = os.path.join(target_dir, filename)

        # Якщо це папка — пропускаємо
        if os.path.isdir(file_path):
            continue

        try:
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            if file_time < cutoff_time:
                os.remove(file_path)
                removed_files.append(file_path)
        except Exception:
            pass

    return removed_files

def delete_json(json_path: str) -> bool:
    """
    Видаляє JSON файл якщо він існує.
    
    Args:
        json_path: Шлях до JSON файлу
        
    Returns:
        True якщо файл був видалений, False якщо файл не існував
    """
    try:
        if os.path.exists(json_path):
            os.remove(json_path)
            #log(f"🗑️ JSON файл видалено: {json_path}")
            return True
        else:
            #log(f"ℹ️ JSON файл не існує: {json_path}")
            return False
    except Exception as e:
        #log(f"❌ Помилка видалення JSON: {e}")
        raise

