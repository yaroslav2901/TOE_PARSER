import cv2
import numpy as np
import pytesseract
import re
import json
import os
import shutil
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Tuple, List, Dict, Any
from telegram_notify import send_error, send_photo 

# --- КОНФІГУРАЦІЯ ТА ШЛЯХИ ---
TZ = ZoneInfo("Europe/Kyiv")
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "full_log.log")
OUTPUT_JSON_PATH = "out/Ternopiloblenerho.json"
OUTPUT_IMG_DIR = "out"
DEBUG_IMAGE_DIR = "DEBUG_IMAGES"

# Створення необхідних папок
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(OUTPUT_IMG_DIR, exist_ok=True)
os.makedirs(DEBUG_IMAGE_DIR, exist_ok=True)
os.makedirs("in", exist_ok=True)


def log(message: str):
    """Логування повідомлень з часовою міткою у Київському часі."""
    timestamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp} [recognizer] {message}")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} [recognizer] {message}\n")

def date_to_unix_timestamp(date_str: str) -> int:
    """Конвертує DD.MM.YYYY у Unix Timestamp (секунди) для початку дня у Київському часі (00:00:00)."""
    try:
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        dt_tz = dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=TZ)
        timestamp = int(dt_tz.timestamp())
        return timestamp
    except ValueError:
        log(f"Помилка конвертації дати {date_str} у Unix Timestamp.")
        return 0

def sort_contours(cnts: List[np.ndarray], method: str = "left-to-right") -> Tuple[List[np.ndarray], List[Tuple[int, int, int, int]]]:
    """Сортує контури (зліва-направо або зверху-вниз)"""
    reverse = False
    i = 0
    if method == "right-to-left" or method == "bottom-to-top":
        reverse = True
    if method == "top-to-bottom" or method == "bottom-to-top":
        i = 1
    
    boundingBoxes = [cv2.boundingRect(c) for c in cnts]
    (cnts, boundingBoxes) = zip(*sorted(zip(cnts, boundingBoxes),
                                         key=lambda b: b[1][i], reverse=reverse))
    return list(cnts), list(boundingBoxes)

def get_date_from_header(image: np.ndarray, table_y: int, original_img: np.ndarray) -> Tuple[str, str]:
    """
    Вирізає заголовок над таблицею та шукає дату у кількох форматах.
    Повертає: (дата_графіка, дата_та_час_оновлення)
    """
    header_img = original_img[0:max(0, table_y), :]
    
    if header_img.size == 0:
        log("⚠️ Область заголовка порожня — використовуємо поточну дату")
        current_date = datetime.now(TZ).strftime("%d.%m.%Y")
        current_datetime = datetime.now(TZ).strftime("%d.%m.%Y %H:%M")
        return current_date, current_datetime

    gray = cv2.cvtColor(header_img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3,3), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    try:
        text = pytesseract.image_to_string(thresh, lang='ukr+eng', config='--psm 6 --oem 3')
    except Exception as e:
        log(f"Помилка pytesseract: {e}")
        text = ""
    text = text.replace('\n', ' ')
    log(f"Розпізнаний текст заголовка: {text}")

    # --- ПОШУК ДАТИ ГРАФІКА ---
    # Шукаємо дату перед "р." або "(станом"
    m = re.search(r"на\s+(\d{2}\.\d{2}\.\d{4})", text)
    if not m:
        m = re.search(r"(\d{2}\.\d{2}\.\d{4})р\.", text)
    if not m:
        m = re.search(r"(\d{2}\.\d{2}\.\d{2})", text)
    if not m:
        m = re.search(r"(\d{2}\.\d{2})", text)

    if not m:
        clean_date = datetime.now(TZ).strftime("%d.%m.%Y")
        log(f"⚠️ Дата графіка не знайдена в заголовку, використано поточну: {clean_date}")
    else:
        found = m.group(1)
        
        if re.match(r"\d{2}\.\d{2}\.\d{2}$", found):
            y = int(found.split(".")[2])
            yyyy = 2000 + y 
            clean_date = f"{found[:5]}.{yyyy}"
        elif re.match(r"\d{2}\.\d{2}$", found):
            yyyy = datetime.now(TZ).year
            clean_date = f"{found}.{yyyy}"
        else:
            clean_date = found
        
        log(f"📅 Знайдено дату графіка: {clean_date}")

    # --- ПОШУК ДАТИ ТА ЧАСУ ОНОВЛЕННЯ "(станом на ...)" ---
    # Шукаємо "(станом на DD.MM.YYYY HH:MM)" або "(станом на DD.MM.YYYY HH.MM)"
    update_match = re.search(r"\(станом\s+на\s+(\d{2}\.\d{2}\.\d{4})\s+(\d{2})[:.](\d{2})\)", text)
    
    if update_match:
        update_date = update_match.group(1)
        update_hour = update_match.group(2)
        update_minute = update_match.group(3)
        update_str = f"{update_date} {update_hour}:{update_minute}"
        log(f"🕒 Знайдено дату та час оновлення: {update_str}")
    else:
        # Якщо не знайдено, використовуємо поточну дату та час
        update_str = datetime.now(TZ).strftime("%d.%m.%Y %H:%M")
        log(f"⚠️ Дата оновлення не знайдена, використано поточну: {update_str}")

    return clean_date, update_str

def _is_red_section(section_img: np.ndarray) -> Tuple[bool, int, int]:
    """Визначає, чи секція має червоний колір (відключення)."""
    if section_img.size == 0: return False, 0, 0
    h, w, _ = section_img.shape
    if h < 5 or w < 5: return False, 0, 0
    crop = section_img[2:h-2, 2:w-2]
    if crop.size == 0: return False, 0, 0
    total_pixels = crop.shape[0] * crop.shape[1]
    b_channel = crop[:, :, 0]
    g_channel = crop[:, :, 1]
    r_channel = crop[:, :, 2]
    
    # Маска для червоного кольору (переважання R, низькі G і B)
    red_mask = (r_channel > 150) & (g_channel < 100) & (b_channel < 100) & \
               (r_channel > g_channel + 50) & (r_channel > b_channel + 50)
    num_red_pixels = np.sum(red_mask)
    ratio = num_red_pixels / total_pixels
    is_red = ratio > 0.30 # 30% червоних пікселів
    return is_red, num_red_pixels, total_pixels

def _is_yellow_section(section_img: np.ndarray) -> Tuple[bool, int, int]:
    """Визначає, чи секція має жовтий колір (можлива відсутність)."""
    if section_img.size == 0: return False, 0, 0
    h, w, _ = section_img.shape
    if h < 5 or w < 5: return False, 0, 0
    crop = section_img[2:h-2, 2:w-2]
    if crop.size == 0: return False, 0, 0
    total_pixels = crop.shape[0] * crop.shape[1]
    b_channel = crop[:, :, 0]
    g_channel = crop[:, :, 1]
    r_channel = crop[:, :, 2]
    
    # Маска для жовтого кольору (високі R і G, низький B)
    yellow_mask = (r_channel > 150) & (g_channel > 150) & (b_channel < 150) & \
                  (np.abs(r_channel.astype(int) - g_channel.astype(int)) < 50)
    num_yellow_pixels = np.sum(yellow_mask)
    ratio = num_yellow_pixels / total_pixels
    is_yellow = ratio > 0.30 # 30% жовтих пікселів
    return is_yellow, num_yellow_pixels, total_pixels

def get_cell_color_status(cell_img: np.ndarray) -> str:
    """
    Визначає погодинний статус клітинки.
    Повертає: 'yes', 'no', 'first', 'second', 'maybe', 'mfirst', 'msecond'.
    """
    h, w, _ = cell_img.shape
    if h < 10 or w < 10: return 'yes'
    
    # Обрізаємо краї, щоб уникнути ліній сітки
    crop = cell_img[3:h-3, 3:w-3]
    h_c, w_c, _ = crop.shape
    if w_c < 2: return 'yes'

    mid_w = w_c // 2
    left_half = crop[:, :mid_w]
    right_half = crop[:, mid_w:]

    # Червоний колір (гарантоване відключення)
    is_left_red, _, _ = _is_red_section(left_half)
    is_right_red, _, _ = _is_red_section(right_half)
    
    # Жовтий колір (можливе відключення)
    is_left_yellow, _, _ = _is_yellow_section(left_half)
    is_right_yellow, _, _ = _is_yellow_section(right_half)

    # 1. Можливе відключення (жовтий)
    if is_left_yellow and is_right_yellow:
        return 'maybe'
    elif is_left_yellow:
        return 'mfirst'
    elif is_right_yellow:
        return 'msecond'

    # 2. Точне відключення (червоний)
    elif is_left_red and is_right_red:
        return 'no'
    elif is_left_red:
        return 'first'
    elif is_right_red:
        return 'second'

    # 3. Є світло
    return 'yes'


def run(image_path: str) -> Dict[str, Any]:
    log(f"=== Старт обробки файлу: {image_path} ===")
    
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Файл не знайдено: {image_path}")
        
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Не вдалося завантажити зображення: {image_path}")
        
    original = image.copy()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Бінаризація та морфологічні операції для виділення сітки
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY_INV, 9, 2)
    
    scale = 10 
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (int(image.shape[1] / scale), 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, int(image.shape[0] / scale)))

    horizontal_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel)
    vertical_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vertical_kernel)

    table_mask = cv2.addWeighted(horizontal_lines, 0.5, vertical_lines, 0.5, 0.0)
    _, table_mask = cv2.threshold(table_mask, 0, 255, cv2.THRESH_BINARY)

    # Знаходження контурів
    contours, _ = cv2.findContours(table_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    cell_contours = []
    min_cell_area = 1000 
    max_cell_area = (image.shape[0] * image.shape[1] * 0.05) 
    
    for c in contours:
        area = cv2.contourArea(c)
        if min_cell_area < area < max_cell_area: 
            cell_contours.append(c)

    if not cell_contours:
        log("❌ Не вдалося розпізнати структуру таблиці.")
        raise ValueError("Не вдалося розпізнати структуру таблиці")

    cnts, bounds = sort_contours(cell_contours, method="top-to-bottom")

    # Групування контурів у рядки
    rows = []
    current_row = []
    previous_y = bounds[0][1]
    row_tolerance = 15 

    for c, b in zip(cnts, bounds):
        x, y, w, h = b
        if abs(y - previous_y) <= row_tolerance:
            current_row.append((c, b))
        else:
            current_row.sort(key=lambda k: k[1][0])
            rows.append(current_row)
            current_row = [(c, b)]
            previous_y = y
    current_row.sort(key=lambda k: k[1][0])
    rows.append(current_row)
    
    # Визначення межі заголовка
    if len(rows) < 2:
        min_table_y = min([b[1] for b in bounds])
    else:
        # Беремо Y перших клітинок двох верхніх рядів
        y_row1 = rows[0][0][1][1]
        y_row2 = rows[1][0][1][1]
        # Беремо середину між рядком 1 і 2, щоб OCR охоплював більше тексту
        min_table_y = int((y_row1 + y_row2) / 2)    
        # Трошки піднімемо OCR ще вище (на 10–25px)
        min_table_y = max(0, min_table_y - 35)


    # Отримання дати та Unix Timestamp
    # Отримання дати графіка та дати оновлення
    date_str, update_str = get_date_from_header(image, min_table_y, original)
    date_timestamp = date_to_unix_timestamp(date_str)
    date_timestamp_str = str(date_timestamp)
    
    # Останні 12 рядків — це черги
    data_rows = rows[-12:] 
    
    queue_names = [
        "1.1", "1.2", "2.1", "2.2", "3.1", "3.2", 
        "4.1", "4.2", "5.1", "5.2", "6.1", "6.2"
    ]
    
    groups_data: Dict[str, Dict[str, str]] = {}
    
    # --- Візуалізація на debug-зображенні ---
    debug_img = original.copy()
    # 🔶 Обведення заголовка ОРАНЖЕВИМ
    cv2.rectangle(debug_img, (0, 0), (image.shape[1], min_table_y), (0,165,255), 3)
    
    # --- Обробка кожного рядка даних ---    
    for i, row_data in enumerate(data_rows):
        if i >= len(queue_names): 
            break
        
        q_name_original = queue_names[i]
        q_name_fact = f"GPV{q_name_original}" 
        groups_data[q_name_fact] = {}
        
        # Беремо лише 24 клітинки часу (для 24 годин)
        time_cells = row_data[-24:] 
        
        if len(time_cells) != 24:
            log(f"⚠️ Увага: рядок {q_name_original} має {len(time_cells)} клітинок часу замість 24.")

        # Обробка кожної клітинки часу   
        for col_idx, (cnt, rect) in enumerate(time_cells):

            x, y, w, h = rect
            cell_img = original[y:y+h, x:x+w]
            
            # Отримання статусу (він вже відповідає погодинному статусу)
            hourly_status = get_cell_color_status(cell_img)
            
            # Ключі годин: "1", "2", ..., "24"
            hour_key = str(col_idx + 1)  
            groups_data[q_name_fact][hour_key] = hourly_status
            
            # 🔷 Обведення ВСІХ знайдених клітинок СИНІМ
            cv2.rectangle(debug_img, (x, y), (x+w, y+h), (255, 0, 0), 2)

            # Візуалізація: малюємо маркер залежно від статусу           
            if hourly_status in ('no', 'first', 'second'):
                # Хрестик для відключень
                cv2.line(debug_img, (x + 5, y + 5), (x + w - 5, y + h - 5), (0, 0, 0), 2)
                cv2.line(debug_img, (x + w - 5, y + 5), (x + 5, y + h - 5), (0, 0, 0), 2)
            elif hourly_status in ('maybe', 'mfirst', 'msecond'):
                # Квадрат для можливих відключень
                #cv2.rectangle(debug_img, (x + 5, y + 5), (x + w - 5, y + h - 5), (0, 0, 0), 2)
                # Хрестик для можливих відключень
                cv2.line(debug_img, (x + 5, y + 5), (x + w - 5, y + h - 5), (0, 0, 0), 2)
                cv2.line(debug_img, (x + w - 5, y + 5), (x + 5, y + h - 5), (0, 0, 0), 2)
            # Якщо 'yes', нічого не малюємо
                

    # Збереження debug-зображення
    debug_output_path = os.path.join(DEBUG_IMAGE_DIR, f"debug_{os.path.basename(image_path)}")
    cv2.imwrite(debug_output_path, debug_img)
    send_photo(debug_output_path, caption=f"🔄 <b>Тернопільобленерго</b>\n #Тернопільобленерго")
    
    # --- Об'єднання з існуючим JSON та фінальна структура ---    
    existing = {}
    if os.path.exists(OUTPUT_JSON_PATH):
        try:
            with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
            log(f"Зчитано існуючий JSON файл.")
        except (json.JSONDecodeError, Exception) as e:
            log(f"⚠️ Помилка читання існуючого JSON: {e}. Скидання.")
            existing = {}

    # Ініціалізація/перевірка секції 'fact.data'
    if "fact" not in existing or not isinstance(existing["fact"], dict):
        existing["fact"] = {"data": {}}
    if "data" not in existing["fact"] or not isinstance(existing["fact"]["data"], dict):
        existing["fact"]["data"] = {}
        
    # Оновлюємо або додаємо дані для поточної дати (Unix Timestamp)
    existing["fact"]["data"][date_timestamp_str] = groups_data
    
    # Видалення старих даних
    now_tz = datetime.now(TZ)
    today_timestamp = date_to_unix_timestamp(now_tz.strftime("%d.%m.%Y"))
    # Видаляємо всі записи з датами меншими за сьогоднішню
    keys_to_delete = [
        ts for ts in existing["fact"]["data"].keys() 
        if int(ts) < today_timestamp
    ]
    for ts in keys_to_delete:
        del existing["fact"]["data"][ts]
        log(f"Видалено застарілі дані для Unix Timestamp: {ts}")

    # Оновлюємо update та today у секції fact
    existing["fact"]["update"] = update_str
    existing["fact"]["today"] = today_timestamp

    # Формування фінальної структури
    #last_updated_iso = now_tz.isoformat()
    last_updated_iso = now_tz.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    
    final_json_data ={
        "regionId": existing.get("regionId", "Ternopil"),
        #"lastUpdated": last_updated_iso,
        "lastUpdated": datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "fact": existing["fact"],  # Тут вже є update та today
        "preset": {
            "time_zone": {
                str(i + 1): [
                    f"{i :02d}-{(i +1) :02d}", 
                    f"{i:02d}:00", 
                    f"{(i + 1) % 24:02d}:00" if i < 23 else "24:00"
                ] 
                for i in range(24)
            },
            "time_type": {
                "yes": "Світло є",
                "maybe": "Можливе відключення",
                "no": "Світла немає",
                "first": "Світла не буде перші 30 хв.",
                "second": "Світла не буде другі 30 хв",
                "mfirst": "Світла можливо не буде перші 30 хв.",
                "msecond": "Світла можливо не буде другі 30 хв"
            }
        }
    }

    try:
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(final_json_data, f, indent=2, ensure_ascii=False)
        log(f"Оновлений JSON збережено у новому форматі: {OUTPUT_JSON_PATH}")
    except Exception as e:
        log(f"Помилка при збереженні JSON: {e}")
    
    log("=== Обробка завершена успішно ===")
    return final_json_data

if __name__ == "__main__":
    TEST_IMAGE_PATH = "in/GPV.png"
    
    # Автоматичне копіювання файлу, якщо він завантажений, але не знаходиться у папці 'in'
    if os.path.exists("GPV.png") and not os.path.exists(TEST_IMAGE_PATH):
        shutil.copy("GPV.png", TEST_IMAGE_PATH)
        log(f"Скопійовано файл GPV.png в {TEST_IMAGE_PATH}")
    elif not os.path.exists(TEST_IMAGE_PATH):
        log(f"❌ Критична помилка: Не знайдено тестового файлу за шляхом: {TEST_IMAGE_PATH}")
        log("Будь ласка, помістіть зображення графіку у папку 'in' під назвою GPV.png.")
    
    if os.path.exists(TEST_IMAGE_PATH):
        try:
            run(TEST_IMAGE_PATH)
        except Exception as e:
            log(f"Критична помилка виконання скрипта: {e}")
            send_error(f"Критична помилка виконання скрипта: {e}")