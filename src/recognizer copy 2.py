import cv2
import numpy as np
import pytesseract
import re
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Tuple, List, Dict, Any
from telegram_notify import send_error, send_photo, send_message

# --- ЧАСОВА ЗОНА ---
TZ = ZoneInfo("Europe/Kyiv")

# --- КОНФІГУРАЦІЯ ---
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "full_log.log")
OUTPUT_JSON_PATH = "out/blackouts.json"
OUTPUT_IMG_DIR = "out"
DEBUG_IMAGE_DIR = "DEBUG_IMAGES"

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

def save_debug_visualization(original_img: np.ndarray, data_rows: List, queue_names: List[str], 
                             groups_data: Dict, output_path: str, header_y: int):
    """Зберігає зображення з відміченими клітинками відключень (хрестики)."""
    debug_img = original_img.copy()
    
    # Обводимо заголовок оранжевим прямокутником
    cv2.rectangle(debug_img, (0, 0), (debug_img.shape[1], header_y), (0, 165, 255), 3)
    
    for i, row_data in enumerate(data_rows):
        if i >= len(queue_names):
            break
            
        q_name = queue_names[i]
        time_cells = row_data[-24:]
        
        for col_idx, (cnt, rect) in enumerate(time_cells):
            x, y, w, h = rect
            cell_img = original_img[y:y+h, x:x+w]
            
            is_out_status = get_cell_color_status(cell_img)
            
            center_x = x + w // 2
            center_y = y + h // 2
            cross_size = min(w, h) // 3
            
            color = (0, 0, 255)  # Червоний для хрестиків
            thickness = 2
            
            if is_out_status == 'full':
                cv2.line(debug_img, 
                        (x + 2, y + 2), 
                        (x + w - 2, y + h - 2), 
                        color, thickness)
                cv2.line(debug_img, 
                        (x + w - 2, y + 2), 
                        (x + 2, y + h - 2), 
                        color, thickness)
                        
            elif is_out_status == 'left':
                left_center_x = x + w // 4
                cv2.line(debug_img, 
                        (left_center_x - cross_size//2, center_y - cross_size//2), 
                        (left_center_x + cross_size//2, center_y + cross_size//2), 
                        color, thickness)
                cv2.line(debug_img, 
                        (left_center_x + cross_size//2, center_y - cross_size//2), 
                        (left_center_x - cross_size//2, center_y + cross_size//2), 
                        color, thickness)
                        
            elif is_out_status == 'right':
                right_center_x = x + 3 * w // 4
                cv2.line(debug_img, 
                        (right_center_x - cross_size//2, center_y - cross_size//2), 
                        (right_center_x + cross_size//2, center_y + cross_size//2), 
                        color, thickness)
                cv2.line(debug_img, 
                        (right_center_x + cross_size//2, center_y - cross_size//2), 
                        (right_center_x - cross_size//2, center_y + cross_size//2), 
                        color, thickness)
            
            # Обводимо клітинку синім
            cv2.rectangle(debug_img, (x, y), (x + w, y + h), (255, 0, 0), 2)
    
    cv2.imwrite(output_path, debug_img)
    log(f"🎨 Збережено debug-візуалізацію: {output_path}")

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

def get_date_from_header(image: np.ndarray, table_y: int, original_img: np.ndarray) -> str:
    """Вирізає заголовок над таблицею та шукає дату у кількох форматах."""
    header_img = original_img[0:max(0, table_y), :]
    
    if header_img.size == 0:
        log("⚠️ Область заголовка порожня — використовуємо поточну дату")
        return datetime.now(TZ).strftime("%d.%m.%Y")

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

    m = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)
    if not m:
        m = re.search(r"(\d{2}\.\d{2}\.\d{2})", text)
    if not m:
        m = re.search(r"(\d{2}\.\d{2})", text)
    if not m:
        m = re.search(r"(\d{2}\.\d{2}\.\d)", text)

    if not m:
        clean_date = datetime.now(TZ).strftime("%d.%m.%Y")
        log(f"⚠️ Дата не знайдена в заголовку, використано поточну: {clean_date}")
        return clean_date

    found = m.group(1)
    
    if re.match(r"\d{2}\.\d{2}\.\d{2}$", found):
        y = int(found.split(".")[2])
        yyyy = 2000 + y 
        clean_date = f"{found[:5]}.{yyyy}"
    elif re.match(r"\d{2}\.\d{2}$", found):
        yyyy = datetime.now(TZ).year
        clean_date = f"{found}.{yyyy}"
    elif re.match(r"\d{2}\.\d{2}\.\d$", found):
        last_digit = int(found[-1])
        if last_digit > 9: 
            last_digit = 9
        
        current_year_prefix = str(datetime.now(TZ).year)[:-1]
        clean_date = f"{found[:5]}.{current_year_prefix}{last_digit}"
        
        try:
             datetime.strptime(clean_date, "%d.%m.%Y")
        except:
             clean_date = f"{found[:5]}.{datetime.now(TZ).year}"
    else:
        clean_date = found

    log(f"📅 Знайдено дату: {clean_date}")
    return clean_date

def _is_red_section(section_img: np.ndarray) -> Tuple[bool, int, int]:
    """
    Визначає, чи секція має червоний колір (відключення).
    Червоний має високий R-канал та низькі G/B канали.
    """
    if section_img.size == 0:
        return False, 0, 0
    
    h, w, _ = section_img.shape
    crop = section_img[2:h-2, 2:w-2]
    if crop.size == 0:
        return False, 0, 0
        
    total_pixels = crop.shape[0] * crop.shape[1]
    
    # Розділяємо BGR канали
    b_channel = crop[:, :, 0]
    g_channel = crop[:, :, 1]
    r_channel = crop[:, :, 2]
    
    # Умови для червоного кольору:
    # 1. R-канал повинен бути високим (> 150)
    # 2. G та B канали повинні бути низькими (< 100)
    # 3. R значно більше за G та B
    
    red_mask = (r_channel > 150) & (g_channel < 100) & (b_channel < 100) & \
               (r_channel > g_channel + 50) & (r_channel > b_channel + 50)
    
    num_red_pixels = np.sum(red_mask)
    ratio = num_red_pixels / total_pixels
    
    # Вважаємо секцію червоною, якщо > 30% пікселів червоні
    is_red = ratio > 0.30
    
    return is_red, num_red_pixels, total_pixels

def _is_yellow_section(section_img: np.ndarray) -> Tuple[bool, int, int]:
    """
    Визначає, чи секція має жовтий колір (можлива відсутність).
    Жовтий має високі R та G канали, низький B канал.
    """
    if section_img.size == 0:
        return False, 0, 0
    
    h, w, _ = section_img.shape
    crop = section_img[2:h-2, 2:w-2]
    if crop.size == 0:
        return False, 0, 0
        
    total_pixels = crop.shape[0] * crop.shape[1]
    
    b_channel = crop[:, :, 0]
    g_channel = crop[:, :, 1]
    r_channel = crop[:, :, 2]
    
    # Умови для жовтого кольору:
    # 1. R та G канали високі (> 150)
    # 2. B канал низький (< 150)
    # 3. R та G приблизно однакові
    
    yellow_mask = (r_channel > 150) & (g_channel > 150) & (b_channel < 150) & \
                  (np.abs(r_channel.astype(int) - g_channel.astype(int)) < 50)
    
    num_yellow_pixels = np.sum(yellow_mask)
    ratio = num_yellow_pixels / total_pixels
    
    is_yellow = ratio > 0.30
    
    return is_yellow, num_yellow_pixels, total_pixels

def get_cell_color_status(cell_img: np.ndarray) -> str | bool:
    """
    Визначає статус клітинки на основі кольору:
    - 'full' = вся клітинка червона (повне відключення)
    - 'left' = ліва половина червона
    - 'right' = права половина червона
    - False = немає відключення (зелена або жовта)
    
    ВАЖЛИВО: Жовтий колір НЕ вважається відключенням!
    """
    h, w, _ = cell_img.shape
    if h < 10 or w < 10: 
        return False 
    
    crop = cell_img[3:h-3, 3:w-3]
    h_c, w_c, _ = crop.shape
    if w_c < 2: 
        return False 

    mid_w = w_c // 2
    left_half = crop[:, :mid_w]
    right_half = crop[:, mid_w:]

    # Перевіряємо тільки на червоний колір
    is_left_red, _, _ = _is_red_section(left_half)
    is_right_red, _, _ = _is_red_section(right_half)

    if is_left_red and is_right_red:
        # Додаткова перевірка всієї клітинки
        is_full_red, _, _ = _is_red_section(crop)
        return 'full' if is_full_red else 'full'
        
    elif is_left_red:
        return 'left'
        
    elif is_right_red:
        return 'right'
        
    else:
        # Ні червоного - значить немає відключення
        # (зелений або жовтий - не важливо)
        return False

def run(image_path: str) -> Dict[str, Any]:
    log(f"=== Старт обробки файлу: {image_path} ===")
    
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Файл не знайдено: {image_path}")

    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Не вдалося завантажити зображення: {image_path}")
        
    original = image.copy()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY_INV, 11, 2)

    scale = 15
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (int(image.shape[1] / scale), 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, int(image.shape[0] / scale)))

    horizontal_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel)
    vertical_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vertical_kernel)

    table_mask = cv2.addWeighted(horizontal_lines, 0.5, vertical_lines, 0.5, 0.0)
    _, table_mask = cv2.threshold(table_mask, 0, 255, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(table_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    cell_contours = []
    min_cell_area = 1000 
    max_cell_area = (image.shape[0] * image.shape[1] * 0.05) 
    
    for c in contours:
        area = cv2.contourArea(c)
        if min_cell_area < area < max_cell_area: 
            cell_contours.append(c)

    log(f"Знайдено потенційних клітинок: {len(cell_contours)}")

    if not cell_contours:
        raise ValueError("Не вдалося розпізнати структуру таблиці")

    cnts, bounds = sort_contours(cell_contours, method="top-to-bottom")

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
    
    log(f"Визначено рядків у таблиці (включно з мітками): {len(rows)}")

    if len(rows) < 2:
        min_table_y = min([b[1] for b in bounds])
        log(f"⚠️ Визначено лише {len(rows)} рядків. Межа заголовка = min Y першого рядка: {min_table_y}")
    else:
        first_cell_of_second_row_y = rows[1][0][1][1]
        min_table_y = first_cell_of_second_row_y
        log(f"✅ Межу заголовка встановлено на рівні початку ДРУГОГО рядка таблиці: {min_table_y}")

    date_str = get_date_from_header(image, min_table_y, original)

    data_rows = rows[-12:] 
    
    queue_names = [
        "1.1", "1.2", "2.1", "2.2", "3.1", "3.2", 
        "4.1", "4.2", "5.1", "5.2", "6.1", "6.2"
    ]

    blackouts = {
        "date": {
            date_str: {
                "groups": {}
            }
        }
    }
    groups_data = blackouts["date"][date_str]["groups"]

    for i, row_data in enumerate(data_rows):
        if i >= len(queue_names): 
            break
        
        q_name = queue_names[i]
        groups_data[q_name] = []
        
        time_cells = row_data[-24:] 
        
        if len(time_cells) != 24:
            log(f"⚠️ Увага: рядок {q_name} має {len(time_cells)} клітинок часу замість 24.")
            
        all_half_hour_slots = []

        for col_idx, (cnt, rect) in enumerate(time_cells):
            x, y, w, h = rect
            cell_img = original[y:y+h, x:x+w]
            
            is_out_status = get_cell_color_status(cell_img)
            
            is_p1_outage = is_out_status in ('left', 'full')
            minutes_p1_start = col_idx * 60 
            
            all_half_hour_slots.append({
                'start_minutes': minutes_p1_start,
                'is_outage': is_p1_outage
            })

            is_p2_outage = is_out_status in ('right', 'full')
            minutes_p2_start = col_idx * 60 + 30 
            
            all_half_hour_slots.append({
                'start_minutes': minutes_p2_start,
                'is_outage': is_p2_outage
            })
            
        current_outage_start_minutes = None
        
        all_half_hour_slots.append({
            'start_minutes': 24 * 60,
            'is_outage': False 
        })

        for slot_idx, slot in enumerate(all_half_hour_slots):
            slot_start_minutes = slot['start_minutes']
            is_outage_now = slot['is_outage']
            
            if is_outage_now:
                if current_outage_start_minutes is None:
                    current_outage_start_minutes = slot_start_minutes
            else:
                if current_outage_start_minutes is not None:
                    end_minutes = slot_start_minutes 
                    
                    start_dt = datetime.strptime("00:00", "%H:%M") + timedelta(minutes=current_outage_start_minutes)
                    
                    end_time_str = "24:00" if end_minutes == 1440 else (datetime.strptime("00:00", "%H:%M") + timedelta(minutes=end_minutes)).strftime("%H:%M")
                    
                    groups_data[q_name].append({
                        "start": start_dt.strftime("%H:%M"),
                        "end": end_time_str,
                        "type": "Outage"
                    })
                    current_outage_start_minutes = None
        
        log(f"Парсинг черги {q_name} завершено. Знайдено інтервалів: {len(groups_data[q_name])}")

    debug_output_path = os.path.join(DEBUG_IMAGE_DIR, f"debug_{os.path.basename(image_path)}")
    save_debug_visualization(original, data_rows, queue_names, groups_data, debug_output_path, min_table_y)
    send_photo(debug_output_path, caption=f"🔄 Закарпаттяобленерго {date_str}")

    today = datetime.now(TZ).date() 

    today_str = today.strftime("%d.%m.%Y")
    parsed_date_dt = datetime.strptime(date_str, "%d.%m.%Y").date()

    existing = {}
    if os.path.exists(OUTPUT_JSON_PATH):
        try:
            with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
            log(f"Зчитано існуючий JSON файл.")
        except json.JSONDecodeError:
            log("⚠️ Помилка декодування існуючого JSON. Скидання до порожнього об'єкта.")
            existing = {}
        except Exception as e:
            log(f"Помилка читання існуючого JSON: {e}. Скидання до порожнього об'єкта.")
            existing = {}

    if "date" not in existing or not isinstance(existing["date"], dict):
        existing["date"] = {}
        
    if parsed_date_dt <= today:
        log(f"📅 {date_str} <= {today_str} — ПОВНИЙ ПЕРЕЗАПИС JSON: зберігаємо лише {date_str}.")
        existing["date"] = {
            date_str: blackouts["date"][date_str]
        }
    else:
        dates_in_json = list(existing.get("date", {}).keys())

        if dates_in_json:
            existing_dates = []
            for d_str in dates_in_json:
                try:
                    existing_dates.append(datetime.strptime(d_str, "%d.%m.%Y").date())
                except ValueError:
                    log(f"⚠️ Некоректна дата в JSON: {d_str}, буде видалена")

            if existing_dates and all(d < today for d in existing_dates):
                log(f"📅 {date_str} > {today_str} і всі існуючі дати < {today_str} — ПОВНИЙ ПЕРЕЗАПИС JSON.")
                existing["date"] = {
                    date_str: blackouts["date"][date_str]
                }
            else:
                log(f"📅 {date_str} > {today_str} — дописуємо/оновлюємо день.")
                existing["date"][date_str] = blackouts["date"][date_str]
        else:
            log(f"📅 JSON порожній, створюємо новий з датою {date_str}.")
            existing["date"] = {
                date_str: blackouts["date"][date_str]
            }
        
    final_json_data = existing

    try:
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(final_json_data, f, indent=4, ensure_ascii=False)
        log(f"Оновлений JSON збережено: {OUTPUT_JSON_PATH}")
    except Exception as e:
        log(f"Помилка при збереженні JSON: {e}")
    
    log("=== Обробка завершена успішно ===")
    return final_json_data

if __name__ == "__main__":
    TEST_IMAGE_PATH = "in/GPV.png"
    
    original_file_name = "6920a2598f86b_GPV.png" 
    if os.path.exists(original_file_name) and not os.path.exists(TEST_IMAGE_PATH):
        import shutil
        shutil.copy(original_file_name, TEST_IMAGE_PATH)
        log(f"Скопійовано файл {original_file_name} в {TEST_IMAGE_PATH}")
    elif not os.path.exists(TEST_IMAGE_PATH):
        log(f"❌ Критична помилка: Не знайдено тестового файлу за шляхом: {TEST_IMAGE_PATH}")
        log("Будь ласка, помістіть зображення графіку у папку 'in' під назвою GPV.png.")
    
    if os.path.exists(TEST_IMAGE_PATH):
        try:
            run(TEST_IMAGE_PATH)
        except Exception as e:
            log(f"Критична помилка виконання скрипта: {e}")