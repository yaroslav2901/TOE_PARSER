#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Створення PNG графіка погодинних відключень з JSON.
Генерує:
- gpv-all-today.png для сьогоднішньої дати
- gpv-all-tomorrow.png для завтрашньої дати (якщо є)
Видаляє gpv-all-tomorrow.png якщо графіку на завтра немає
НОВЕ: Підсвічує зміни порівняно з попереднім графіком
"""
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
import os
import sys
from telegram_notify import send_error, send_photo, send_message

# --- Налаштування шляхів ---
BASE = Path(__file__).parent.parent.absolute()
JSON_DIR = BASE / "out"
OUT_DIR = BASE / "out/images"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PREV_STATE_DIR = BASE / "out/prev_state"
PREV_STATE_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR = BASE / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
FULL_LOG_FILE = LOG_DIR / "full_log.log"

# Файл для збереження попереднього стану
PREV_STATE_FILE = PREV_STATE_DIR / "previous_state.json"

def log(message):
    timestamp = datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} [gener_im_full] {message}"
    print(line)
    try:
        with open(FULL_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

# --- Візуальні параметри ---
CELL_W = 44 # Ширина однієї клітинки (1 година)
CELL_H = 36 # Висота однієї клітинки
LEFT_COL_W = 140 # Ширина лівої колонки з назвами груп
HEADER_H = 34 # Висота заголовка
SPACING = 60 # Відступи з усіх сторін
LEGEND_H = 100 # Висота області для легенди та інформації внизу
HOUR_ROW_H = 90 # Висота рядка з годинами над таблицею
HEADER_SPACING = 35 # Відстань між заголовком і рядком годин
HOUR_LINE_GAP = 15 # Відстань між рядками годин (наприклад, між "00", "-", "01")

# --- Шрифти ---
TITLE_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
TITLE_FONT_SIZE = 34
HOUR_FONT_SIZE = 15
GROUP_FONT_SIZE = 20
SMALL_FONT_SIZE = 16
LEGEND_FONT_SIZE = 14 # Розмір шрифту для легенди та інформації внизу

# --- Кольори ---
BG = (250, 250, 250)
TABLE_BG = (255, 255, 255)
GRID_COLOR = (139, 139, 139)
TEXT_COLOR = (0, 0, 0)
OUTAGE_COLOR = (147, 170, 210)
POSSIBLE_COLOR = (255, 220, 115)
AVAILABLE_COLOR = (255, 255, 255)
HEADER_BG = (245, 247, 250)
FOOTER_COLOR = (140, 140, 140)

# Кольори для підсвічування змін
WORSE_OUTLINE = (220, 53, 69)  # Червоний - більше відключень
BETTER_OUTLINE = (40, 167, 69)  # Зелений - менше відключень
HIGHLIGHT_WIDTH = 3  # Товщина обводки

# --- Функції для роботи з попереднім станом ---
def load_previous_state():
    """Завантажує попередній стан графіків"""
    if PREV_STATE_FILE.exists():
        try:
            with open(PREV_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"⚠️ Помилка при завантаженні попереднього стану: {e}")
    return {}

def save_current_state(data: dict):
    """Зберігає поточний стан графіків"""
    try:
        fact = data.get("fact", {})
        state_to_save = {
            "data": fact.get("data", {}),
            "update": fact.get("update"),
            "timestamp": datetime.now(ZoneInfo("Europe/Kyiv")).isoformat()
        }
        with open(PREV_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state_to_save, f, ensure_ascii=False, indent=2)
        log(f"💾 Збережено поточний стан у {PREV_STATE_FILE}")
    except Exception as e:
        log(f"⚠️ Помилка при збереженні поточного стану: {e}")

def calculate_outage_severity(state: str) -> int:
    """
    Повертає числове значення "важкості" відключення
    Більше число = гірший стан (більше відключень)
    """
    severity_map = {
        "yes": 0,        # Світло є
        "maybe": 2,      # Можливе відключення
        "mfirst": 2,     # Можливе відключення перші 30 хв
        "msecond": 2,    # Можливе відключення другі 30 хв
        "first": 3,      # Відключення перші 30 хв
        "second": 3,     # Відключення другі 30 хв
        "no": 4          # Повне відключення
    }
    return severity_map.get(state, 0)

def compare_states(old_state: str, new_state: str) -> str:
    """
    Порівнює два стани і повертає:
    - "worse" якщо стан погіршився (більше відключень)
    - "better" якщо стан покращився (менше відключень)
    - "same" якщо стан не змінився
    """
    old_severity = calculate_outage_severity(old_state)
    new_severity = calculate_outage_severity(new_state)
    
    if new_severity > old_severity:
        return "worse"
    elif new_severity < old_severity:
        return "better"
    else:
        return "same"

# --- Завантаження останнього JSON ---
def load_latest_json(json_dir: Path):
    files = sorted(json_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("Не знайдено JSON файлів у " + str(json_dir))
    with open(files[0], "r", encoding="utf-8") as f:
        data = json.load(f)
    return data, files[0]

# --- Вибір шрифту з fallback ---
def pick_font(size, bold=False):
    try:
        path = TITLE_FONT_PATH if bold else FONT_PATH
        return ImageFont.truetype(path, size=size)
    except Exception:
        try:
            return ImageFont.load_default()
        except Exception:
            return None

# --- Видалення зображення tomorrow якщо воно не потрібне ---
def cleanup_tomorrow_image(generated_files: list):
    """
    Видаляє gpv-all-tomorrow.png якщо його немає в списку згенерованих файлів
    
    Args:
        generated_files: список назв файлів, які було згенеровано
    """
    tomorrow_file = OUT_DIR / "gpv-all-tomorrow.png"
    
    # Якщо файл існує, але не був згенерований в цій сесії
    if tomorrow_file.exists() and "gpv-all-tomorrow.png" not in generated_files:
        try:
            tomorrow_file.unlink()
            log(f"🗑️ Видалено застаріле зображення: {tomorrow_file}")
        except Exception as e:
            log(f"⚠️ Помилка при видаленні {tomorrow_file}: {e}")

# --- Визначення дат для генерації ---
def get_dates_to_generate(fact_data: dict) -> list:
    """
    Повертає список кортежів (timestamp, day_key, filename, date_label) для генерації.
    
    Args:
        fact_data: Словник з даними fact.data
        
    Returns:
        list: Список кортежів для кожної дати
    """
    available_dates = list(fact_data.keys())
    
    if not available_dates:
        raise ValueError("Немає доступних дат у fact.data")
    
    # Сортуємо дати як числа (timestamp) у зростаючому порядку
    try:
        sorted_dates = sorted(available_dates, key=lambda x: int(x))
    except (ValueError, TypeError):
        sorted_dates = sorted(available_dates)
    
    # Отримуємо поточну дату (початок доби) в Києві
    kyiv_tz = ZoneInfo("Europe/Kyiv")
    now = datetime.now(kyiv_tz)
    today_start = datetime(now.year, now.month, now.day, tzinfo=kyiv_tz)
    today_ts = int(today_start.timestamp())
    tomorrow_ts = today_ts + 86400  # +1 день
    
    result = []
    
    for day_key in sorted_dates:
        timestamp = int(day_key)
        date_obj = datetime.fromtimestamp(timestamp, kyiv_tz)
        date_str = date_obj.strftime("%d.%m.%Y")
        
        # Визначаємо, це сьогодні чи завтра
        day_diff = (timestamp - today_ts) // 86400
        
        if day_diff == 0:
            # Сьогодні
            filename = "gpv-all-today.png"
            date_label = "сьогодні"
            log(f"Знайдено дату для СЬОГОДНІ: {day_key} ({date_str})")
        elif day_diff == 1:
            # Завтра
            filename = "gpv-all-tomorrow.png"
            date_label = "завтра"
            log(f"Знайдено дату для ЗАВТРА: {day_key} ({date_str})")
        else:
            # Інша дата - пропускаємо або використовуємо як сьогодні
            log(f"Знайдено іншу дату: {day_key} ({date_str}), різниця днів: {day_diff}")
            if len(sorted_dates) == 1:
                # Якщо тільки одна дата, генеруємо як today
                filename = "gpv-all-today.png"
                date_label = date_str
            else:
                continue
        
        result.append((timestamp, day_key, filename, date_str))
    
    if not result:
        # Якщо не знайшли підходящих дат, беремо останню як today
        day_key = sorted_dates[-1]
        timestamp = int(day_key)
        date_str = datetime.fromtimestamp(timestamp, kyiv_tz).strftime("%d.%m.%Y")
        result.append((timestamp, day_key, "gpv-all-today.png", date_str))
        log(f"Використовую останню дату як today: {day_key} ({date_str})")
    
    return result

# --- Функція для отримання кольору за станом ---
def get_color_for_state(state: str) -> tuple:
    color_map = {
        "yes": AVAILABLE_COLOR,
        "no": OUTAGE_COLOR,
        "maybe": POSSIBLE_COLOR,
        "first": OUTAGE_COLOR,
        "second": OUTAGE_COLOR,
        "mfirst": POSSIBLE_COLOR,
        "msecond": POSSIBLE_COLOR
    }
    return color_map.get(state, AVAILABLE_COLOR)

# --- Функція для отримання опису стану ---
def get_description_for_state(state: str, preset: dict) -> str:
    time_type = preset.get("time_type", {})
    descriptions = {
        "yes": "Світло є",
        "no": "Світла немає", 
        "maybe": "Можливе відключення",
        "first": "Світла не буде перші 30 хв.",
        "second": "Світла не буде другі 30 хв.",
        "mfirst": "Світла можливо не буде перші 30 хв.",
        "msecond": "Світла можливо не буде другі 30 хв."
    }
    return time_type.get(state, descriptions.get(state, "Невідомий стан"))

# --- Функція для малювання розділеної клітинки ---
def draw_split_cell(draw, x0, y0, x1, y1, state, prev_state, next_state, change_type=None):
    half = (x1 - x0) // 2

    if state == "yes":
        left = right = AVAILABLE_COLOR

    elif state == "no":
        left = right = OUTAGE_COLOR

    elif state == "maybe":
        left = right = POSSIBLE_COLOR

    elif state == "first":
        left = OUTAGE_COLOR
        right = OUTAGE_COLOR if next_state in ["no", "first","maybe"] else AVAILABLE_COLOR

    elif state == "second":
        right = OUTAGE_COLOR
        left = OUTAGE_COLOR if prev_state in ["no", "second","maybe"] else AVAILABLE_COLOR

    elif state == "mfirst":
        left = POSSIBLE_COLOR
        if next_state is not None: # Перевіряємо, чи існує next_state
            if next_state in ["no", "first"]:
                right = OUTAGE_COLOR
            else:
                right = AVAILABLE_COLOR
        else:
            if prev_state in ["no", "first", "second","maybe", "mfirst","msecond"]:
                right = AVAILABLE_COLOR
            else:
                right = OUTAGE_COLOR

    elif state == "msecond":
        right = POSSIBLE_COLOR
        if prev_state is not None:
            if prev_state in ["no", "second"]:
                left = OUTAGE_COLOR
            else:
                left = AVAILABLE_COLOR
        else:
            if next_state in ["no", "first", "second","maybe", "mfirst","msecond"]:
                left = AVAILABLE_COLOR
            else:
                left = OUTAGE_COLOR            

    else:
        left = right = AVAILABLE_COLOR

    # --- Малювання ---
    if left == right:
        draw.rectangle([x0, y0, x1, y1], fill=left, outline=GRID_COLOR)
    else:
        draw.rectangle([x0, y0, x0 + half, y1], fill=left)
        draw.rectangle([x0 + half, y0, x1, y1], fill=right)
        draw.rectangle([x0, y0, x1, y1], outline=GRID_COLOR)
    
    # --- Підсвічування змін ---
    if change_type == "worse":
        # Червона обводка для погіршення
        for i in range(HIGHLIGHT_WIDTH):
            draw.rectangle([x0 + i, y0 + i, x1 - i, y1 - i], outline=WORSE_OUTLINE)
    elif change_type == "better":
        # Зелена обводка для покращення
        for i in range(HIGHLIGHT_WIDTH):
            draw.rectangle([x0 + i, y0 + i, x1 - i, y1 - i], outline=BETTER_OUTLINE)

# --- Основна функція рендерингу ---
def render_single_date(data: dict, day_ts: int, day_key: str, output_filename: str, date_str: str, prev_data: dict = None):
    fact = data.get("fact", {})
    preset = data.get("preset", {}) or {}
    
    day_map = fact["data"].get(day_key, {})
    
    # Отримуємо попередні дані для порівняння
    prev_day_map = {}
    has_changes = False
    if prev_data:
        prev_day_map = prev_data.get(day_key, {})
        log(f"📊 Порівнюю з попереднім графіком для {day_key}")

    # Сортування груп
    def sort_key(s):
        try:
            if "GPV" in s:
                import re
                m = re.search(r"(\d+)", s)
                return (0, int(m.group(1)) if m else s)
        except Exception:
            pass
        return (1, s)
    groups = sorted(list(day_map.keys()), key=sort_key)
    rows = groups

    n_hours = 24
    n_rows = max(1, len(rows))
    width = SPACING*2 + LEFT_COL_W + n_hours*CELL_W
    height = SPACING*2 + HEADER_H + HOUR_ROW_H + n_rows*CELL_H + LEGEND_H + 40

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    # --- Шрифти ---
    font_title = pick_font(TITLE_FONT_SIZE, bold=True)
    font_hour = pick_font(HOUR_FONT_SIZE)
    font_group = pick_font(GROUP_FONT_SIZE)
    font_small = pick_font(SMALL_FONT_SIZE)
    font_legend = pick_font(LEGEND_FONT_SIZE)

    # --- Заголовок ---
    title_text = f"Графік погодинних відключень на {date_str}"
    bbox = draw.textbbox((0,0), title_text, font=font_title)
    w_title = bbox[2] - bbox[0]
    h_title = bbox[3] - bbox[1]
    title_x = SPACING + (LEFT_COL_W + n_hours*CELL_W - w_title) / 2
    title_y = SPACING + 6
    draw.text((title_x, title_y), title_text, fill=TEXT_COLOR, font=font_title)

    # --- Таблиця ---
    table_x0 = SPACING
    table_y0 = SPACING + HEADER_H + HOUR_ROW_H + HEADER_SPACING
    table_x1 = table_x0 + LEFT_COL_W + n_hours*CELL_W
    table_y1 = table_y0 + n_rows*CELL_H
    draw.rectangle([table_x0, table_y0, table_x1, table_y1], fill=TABLE_BG, outline=GRID_COLOR)

    # --- Рядок годин ---
    hour_y0 = table_y0 - HOUR_ROW_H
    hour_y1 = table_y0
    for h in range(24):
        x0 = table_x0 + LEFT_COL_W + h*CELL_W
        x1 = x0 + CELL_W
        draw.rectangle([x0, hour_y0, x1, hour_y1], fill=HEADER_BG, outline=GRID_COLOR)
        start = f"{h:02d}"
        middle = "-"
        end = f"{(h+1)%24:02d}"
        bbox1 = draw.textbbox((0,0), start, font=font_hour)
        bbox2 = draw.textbbox((0,0), middle, font=font_hour)
        bbox3 = draw.textbbox((0,0), end, font=font_hour)
        h1 = bbox1[3]-bbox1[1]
        h2 = bbox2[3]-bbox2[1]
        h3 = bbox3[3]-bbox3[1]
        total_h = h1 + HOUR_LINE_GAP + h2 + HOUR_LINE_GAP + h3
        y_cursor = hour_y0 + (HOUR_ROW_H - total_h)/2
        draw.text((x0 + (CELL_W - (bbox1[2]-bbox1[0]))/2, y_cursor), start, fill=TEXT_COLOR, font=font_hour)
        y_cursor += h1 + HOUR_LINE_GAP
        draw.text((x0 + (CELL_W - (bbox2[2]-bbox2[0]))/2, y_cursor), middle, fill=TEXT_COLOR, font=font_hour)
        y_cursor += h2 + HOUR_LINE_GAP
        draw.text((x0 + (CELL_W - (bbox3[2]-bbox3[0]))/2, y_cursor), end, fill=TEXT_COLOR, font=font_hour)

    # --- Ліва колонка ---
    left_label = "Черга"
    draw.rectangle([table_x0, hour_y0, table_x0+LEFT_COL_W, hour_y1], fill=HEADER_BG, outline=GRID_COLOR)
    bbox = draw.textbbox((0,0), left_label, font=font_hour)
    draw.text((table_x0 + (LEFT_COL_W - (bbox[2]-bbox[0]))/2, hour_y0 + (HOUR_ROW_H - (bbox[3]-bbox[1]))/2),
              left_label, fill=TEXT_COLOR, font=font_hour)

    # Лічильники змін
    changes_worse = 0
    changes_better = 0

    # --- Рядки груп і клітинки ---
    for r, group in enumerate(rows):
        y0 = table_y0 + r*CELL_H
        y1 = y0 + CELL_H
        draw.rectangle([table_x0, y0, table_x0 + LEFT_COL_W, y1], outline=GRID_COLOR, fill=TABLE_BG)
        label = group.replace("GPV", "").strip()
        bbox = draw.textbbox((0,0), label, font=font_group)
        draw.text((table_x0 + (LEFT_COL_W - (bbox[2]-bbox[0]))/2, y0 + (CELL_H - (bbox[3]-bbox[1]))/2),
                  label, fill=TEXT_COLOR, font=font_group)

        gp_hours = day_map.get(group, {}) if isinstance(day_map.get(group, {}), dict) else {}
        prev_gp_hours = prev_day_map.get(group, {}) if isinstance(prev_day_map.get(group, {}), dict) else {}
        
        for h in range(24):
            h_key = str(h + 1)
            state = gp_hours.get(h_key, "yes")
            
            prev_h_key = str(h) if h > 0 else None
            next_h_key = str(h + 2) if h < 23 else None            
            prev_state = gp_hours.get(prev_h_key) if prev_h_key else None
            next_state = gp_hours.get(next_h_key) if next_h_key else None

            # Порівняння з попереднім станом
            change_type = None
            if prev_gp_hours:
                old_state = prev_gp_hours.get(h_key, "yes")
                comparison = compare_states(old_state, state)
                if comparison == "worse":
                    change_type = "worse"
                    changes_worse += 1
                elif comparison == "better":
                    change_type = "better"
                    changes_better += 1
            
            x0h = table_x0 + LEFT_COL_W + h*CELL_W
            x1h = x0h + CELL_W
            
            draw_split_cell(draw, x0h, y0, x1h, y1, state, prev_state, next_state, change_type)

    # Виводимо статистику змін
    if changes_worse > 0 or changes_better > 0:
        log(f"📈 Зміни в графіку: погіршень={changes_worse}, покращень={changes_better}")
        has_changes = True

    # --- Лінії сітки ---
    for i in range(0, 25):
        x = table_x0 + LEFT_COL_W + i*CELL_W
        draw.line([(x, table_y0 - HOUR_ROW_H), (x, table_y1)], fill=GRID_COLOR)
    for r in range(n_rows+1):
        y = table_y0 + r*CELL_H
        draw.line([(table_x0, y), (table_x1, y)], fill=GRID_COLOR)

    # --- Легенда ---
    legend_states = ["yes", "no", "maybe"]
    legend_y_start = table_y1 + 15
    box_size = 18
    gap = 15
    
    x_cursor = SPACING
    for state in legend_states:
        color = get_color_for_state(state)
        description = get_description_for_state(state, preset)
        text_bbox = draw.textbbox((0,0), description, font=font_legend)
        w_text = text_bbox[2] - text_bbox[0]
        
        draw.rectangle([x_cursor, legend_y_start, x_cursor + box_size, legend_y_start + box_size], 
                      fill=color, outline=GRID_COLOR)
        draw.text((x_cursor + box_size + 4, legend_y_start + (box_size - (text_bbox[3]-text_bbox[1]))/2), 
                 description, fill=TEXT_COLOR, font=font_legend)
        x_cursor += box_size + 4 + w_text + gap
    
    # Додаємо легенду для змін якщо є зміни
    if has_changes:
        x_cursor += gap * 2
        
        # Червона рамка - погіршення
        draw.rectangle([x_cursor, legend_y_start, x_cursor + box_size, legend_y_start + box_size], 
                      fill=TABLE_BG, outline=WORSE_OUTLINE, width=HIGHLIGHT_WIDTH)
        worse_text = "Більше відключень"
        text_bbox = draw.textbbox((0,0), worse_text, font=font_legend)
        draw.text((x_cursor + box_size + 4, legend_y_start + (box_size - (text_bbox[3]-text_bbox[1]))/2), 
                 worse_text, fill=TEXT_COLOR, font=font_legend)
        x_cursor += box_size + 4 + (text_bbox[2] - text_bbox[0]) + gap
        
        # Зелена рамка - покращення
        draw.rectangle([x_cursor, legend_y_start, x_cursor + box_size, legend_y_start + box_size], 
                      fill=TABLE_BG, outline=BETTER_OUTLINE, width=HIGHLIGHT_WIDTH)
        better_text = "Менше відключень"
        text_bbox = draw.textbbox((0,0), better_text, font=font_legend)
        draw.text((x_cursor + box_size + 4, legend_y_start + (box_size - (text_bbox[3]-text_bbox[1]))/2), 
                 better_text, fill=TEXT_COLOR, font=font_legend)

    # --- Інформація про публікацію ---
    pub_text = fact.get("update") or data.get("lastUpdated") or datetime.now(ZoneInfo('Europe/Kyiv')).strftime("%d.%m.%Y")
    pub_label = f"Опубліковано {pub_text}"
    bbox_pub = draw.textbbox((0,0), pub_label, font=font_small)
    w_pub = bbox_pub[2] - bbox_pub[0]
    pub_x = width - w_pub - SPACING
    pub_y = legend_y_start + box_size + 20
    draw.text((pub_x, pub_y), pub_label, fill=FOOTER_COLOR, font=font_small)

    # --- Інформація про проєкт ---   
    info_y_start = legend_y_start + box_size + 20
    x_text = SPACING
    line_gap = 6

    
    info_lines = [
        "Цей проєкт створено волонтерами для вас. Разом ми можемо зробити інформацію доступною для всіх.",
        "Помітили розбіжності між графіком та офіційним джерелом? Напишіть нам: https://t.me/OUTAGE_CHAT",
        "Офіційна спільнота проєкту: https://t.me/svitlobot_api"        
    ]


    for i, line in enumerate(info_lines):
        bbox_line = draw.textbbox((0, 0), line, font=font_small)
        draw.text(
            (x_text, info_y_start + i * (bbox_line[3] - bbox_line[1] + line_gap)),
            line,
            fill=FOOTER_COLOR,
            font=font_small
        )

    out_path = OUT_DIR / output_filename
    scale = 3
    img_resized = img.resize((img.width*scale, img.height*scale), resample=Image.LANCZOS)
    img_resized.save(out_path, optimize=True)
    log(f"✅ Збережено {out_path}")

# --- Головна функція рендерингу ---
def render(data: dict, json_path: Path):
    fact = data.get("fact", {})
    if "today" not in fact or "data" not in fact:
        raise ValueError("JSON не містить ключі 'fact.today' або 'fact.data'")

    # Завантажуємо попередній стан для порівняння
    prev_state = load_previous_state()
    prev_fact_data = prev_state.get("data", {})

    # Отримуємо всі дати для генерації
    dates_to_generate = get_dates_to_generate(fact["data"])
    
    log(f"📅 Буде згенеровано {len(dates_to_generate)} зображень(я)")
    
    # Список згенерованих файлів
    generated_files = []
    
    # Генеруємо зображення для кожної дати
    for day_ts, day_key, filename, date_str in dates_to_generate:
        log(f"🖼️ Генерую {filename} для дати {date_str}")
        render_single_date(data, day_ts, day_key, filename, date_str, prev_fact_data)
        generated_files.append(filename)
    
    # Видаляємо tomorrow якщо його не було згенеровано
    cleanup_tomorrow_image(generated_files)
    
    # Зберігаємо поточний стан для наступного порівняння
    save_current_state(data)

def generate_from_json(json_path):
    path = Path(json_path)
    if not path.exists():
        log(f"❌ JSON файл не знайдено: {json_path}")
        send_error(f"❌ JSON файл не знайдено: {json_path}")
        raise FileNotFoundError(f"JSON файл не знайдено: {json_path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    log(f"▶️ Запускаю генерацію зображень з {json_path}")
    render(data, path)

def main():
    try:
        data, path = load_latest_json(JSON_DIR)
    except Exception as e:
        log(f"❌ Помилка при завантаженні JSON: {e}")
        send_error(f"❌ Помилка при завантаженні JSON: {e}")
        sys.exit(1)
    
    log("▶️ Запускаю генерацію зображень з " + str(path))
    try:
        render(data, path)
    except Exception as e:
        log(f"❌ Помилка під час рендерингу: {e}")
        send_error(f"❌ Помилка під час рендерингу: {e}")
        raise

if __name__ == "__main__":
    main()