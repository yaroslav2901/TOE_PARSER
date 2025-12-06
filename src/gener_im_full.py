#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Створення PNG графіка погодинних відключень з JSON.
Виводить одне зображення для останнього JSON у out/images/ як: gpv-all-today.png
Покращено:
 - генерація для більшої дати, якщо в JSON дві дати
 - більш надійна робота з відсутніми шрифтами/файлами
 - правильне центрування заголовка
 - безпечніша обробка day_key в fact.data
 - трирядкові підписи годин
 - збільшена висота рядка годин
 - розділення години на дві половини для станів first/second/mfirst/msecond
 - легенда в один рядок
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
# Визначаємо BASE як батьківську директорію проекту TOE_PARSER 
BASE = Path(__file__).parent.parent.absolute()
#BASE = Path("/home/yaroslav/bots/TOE_PARSER")
JSON_DIR = BASE / "out"
OUT_DIR = BASE / "out/images"
OUT_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR = BASE / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
FULL_LOG_FILE = LOG_DIR / "full_log.log"

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
CELL_W = 44          # ширина клітинки за годину
CELL_H = 36          # висота рядка групи
LEFT_COL_W = 140     # ширина лівої колонки
HEADER_H = 34        # висота області заголовка
SPACING = 60         # зовнішні відступи
LEGEND_H = 60        # блок легенди під таблицею (зменшено для одного рядка)
HOUR_ROW_H = 90      # висота рядка з годинами
HEADER_SPACING = 35  # негатив піднімає таблицю ближче до заголовка
HOUR_LINE_GAP = 15   # відстань між трьома рядками годин

# --- Шрифти ---
TITLE_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
TITLE_FONT_SIZE = 34
HOUR_FONT_SIZE = 15
GROUP_FONT_SIZE = 20
SMALL_FONT_SIZE = 16
LEGEND_FONT_SIZE = 14

# --- Кольори ---
BG = (250, 250, 250)
TABLE_BG = (255, 255, 255)
GRID_COLOR = (139, 139, 139)
TEXT_COLOR = (0, 0, 0)
OUTAGE_COLOR = (147, 170, 210)      # Світла немає (синій)
POSSIBLE_COLOR = (255, 220, 115)    # Можливе відключення (жовтий)
AVAILABLE_COLOR = (255, 255, 255)   # Світло є (білий)
#FIRST_HALF_COLOR = (147, 170, 210)  # Перші 30 хв немає (синій)
#SECOND_HALF_COLOR = (147, 170, 210) # Другі 30 хв немає (синій)
#MFIRST_HALF_COLOR = (255, 220, 115) # Можливо перші 30 хв немає (жовтий)
#MSECOND_HALF_COLOR = (255, 220, 115) # Можливо другі 30 хв немає (жовтий)
HEADER_BG = (245, 247, 250)
FOOTER_COLOR = (140, 140, 140)

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

# --- Отримання дати для відображення (більша з доступних) ---
def get_target_date(fact_data: dict) -> tuple:
    """
    Повертає timestamp і ключ для більшої дати з доступних.
    
    Args:
        fact_data: Словник з даними fact.data
        
    Returns:
        tuple: (timestamp, day_key) для обраної дати
    """
    available_dates = list(fact_data.keys())
    
    if not available_dates:
        raise ValueError("Немає доступних дат у fact.data")
    
    if len(available_dates) == 1:
        # Тільки одна дата - використовуємо її
        day_key = available_dates[0]
        try:
            timestamp = int(day_key)
        except ValueError:
            timestamp = int(fact_data.get("today", day_key))
        return timestamp, day_key
    
    # Дві або більше дат - вибираємо більшу (пізнішу)
    log(f"Знайдено {len(available_dates)} дат: {available_dates}")
    
    # Сортуємо дати як числа (timestamp) у зростаючому порядку
    try:
        sorted_dates = sorted(available_dates, key=lambda x: int(x))
    except (ValueError, TypeError):
        # Якщо не вдається перетворити на числа, сортуємо як строки
        sorted_dates = sorted(available_dates)
    
    # Беремо останню (найбільшу) дату
    day_key = sorted_dates[-1]
    timestamp = int(day_key)
    
    log(f"Обрано дату: {day_key} ({datetime.fromtimestamp(timestamp, ZoneInfo('Europe/Kyiv')).strftime('%d.%m.%Y')})")
    return timestamp, day_key

# --- Функція для отримання кольору за станом ---
def get_color_for_state(state: str) -> tuple:
    """Повертає колір клітинки залежно від стану"""
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
    """Повертає опис стану з preset.time_type або стандартний"""
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
def draw_split_cell(draw, x0: int, y0: int, x1: int, y1: int, state: str, prev_state: str, next_state: str, outline_color: tuple):
    """
    Малює клітинку відповідно до її власного стану з урахуванням сусідніх годин для mfirst/msecond.
    
    Логіка станів:
    - "yes" → вся біла
    - "no" → вся синя
    - "maybe" → вся жовта
    - "first" → ліва синя, права біла
    - "second" → ліва біла, права синя
    - "mfirst" → ліва жовта, права залежить від НАСТУПНОЇ години
    - "msecond" → ліва залежить від ПОПЕРЕДНЬОЇ години, права жовта
    
    Приклади:
    - Година 11="mfirst", година 12="no": клітинка 11 ліва жовта, права синя (від години 12)
    - Година 13="yes", година 14="msecond": клітинка 14 ліва біла (від години 13), права жовта
    """
    cell_width = x1 - x0
    half_width = cell_width // 2
    
    # Визначаємо кольори на основі власного стану
    if state == "no":
        left_color = right_color = OUTAGE_COLOR
    elif state == "maybe":
        left_color = right_color = POSSIBLE_COLOR
    elif state == "yes":
        left_color = right_color = AVAILABLE_COLOR
    elif state == "first":
        # Ліва синя, права залежить від НАСТУПНОЇ години
        left_color = OUTAGE_COLOR
        # Перевіряємо стан наступної години
        if next_state == "no":
            right_color = OUTAGE_COLOR
        elif next_state == "maybe":
            right_color = POSSIBLE_COLOR
        elif next_state in ["first", "mfirst"]:
            right_color = OUTAGE_COLOR if next_state == "first" else POSSIBLE_COLOR
        elif next_state in ["second", "msecond"]:
            right_color = AVAILABLE_COLOR  # Перша половина наступної години зі світлом
        else:
            right_color = AVAILABLE_COLOR  # За замовчуванням
    elif state == "second":
        # Ліва залежить від ПОПЕРЕДНЬОЇ години, права синя
        right_color = OUTAGE_COLOR
        # Перевіряємо стан попередньої години
        if prev_state == "no":
            left_color = OUTAGE_COLOR
        elif prev_state == "maybe":
            left_color = POSSIBLE_COLOR
        elif prev_state in ["second", "msecond"]:
            # колір лівої половини залежить від попередньої години якщо вона була msecond ТО ж жовта, інакше синя
            left_color = OUTAGE_COLOR if prev_state == "second" else POSSIBLE_COLOR
        elif prev_state in ["first", "mfirst"]:
            left_color = AVAILABLE_COLOR  # Друга половина попередньої години зі світлом
        else:
            left_color = AVAILABLE_COLOR  # За замовчуванням
    elif state == "mfirst":
        # Ліва жовта, права залежить від НАСТУПНОЇ години
        left_color = POSSIBLE_COLOR
        # Перевіряємо стан наступної години
        if next_state == "no":
            right_color = OUTAGE_COLOR
        elif next_state == "maybe":
            right_color = POSSIBLE_COLOR
        elif next_state in ["first", "mfirst"]:
            right_color = OUTAGE_COLOR 
        elif next_state in ["second", "msecond"]:
            right_color = OUTAGE_COLOR
        else:
            right_color = AVAILABLE_COLOR  # За замовчуванням
    elif state == "msecond":
        # Ліва залежить від ПОПЕРЕДНЬОЇ години, права жовта
        right_color = POSSIBLE_COLOR
        # Перевіряємо стан попередньої години
        if prev_state == "no":
            left_color = OUTAGE_COLOR
        elif prev_state == "maybe":
            left_color = POSSIBLE_COLOR
        elif prev_state in ["second", "msecond"]:
            # колір лівої половини залежить від попередньої години якщо вона була msecond ТО ж жовта, інакше синя
            left_color = OUTAGE_COLOR
        elif prev_state in ["first", "mfirst"]:
            left_color = OUTAGE_COLOR 
        else:
            left_color = AVAILABLE_COLOR  # За замовчуванням
    else:
        left_color = right_color = AVAILABLE_COLOR
    
    # Малюємо клітинку
    if left_color == right_color:
        # Якщо обидві половини однакового кольору, малюємо суцільну клітинку
        draw.rectangle([x0, y0, x1, y1], fill=left_color, outline=outline_color)
    else:
        # Якщо кольори різні, малюємо дві половини з розділювальною лінією
        draw.rectangle([x0, y0, x0 + half_width, y1], fill=left_color)
        draw.rectangle([x0 + half_width, y0, x1, y1], fill=right_color)
        # Вертикальна лінія розділення
        #draw.line([(x0 + half_width, y0), (x0 + half_width, y1)], fill=outline_color)

# --- Основна функція рендерингу ---
def render(data: dict, json_path: Path):
    fact = data.get("fact", {})
    preset = data.get("preset", {}) or {}
    if "today" not in fact or "data" not in fact:
        raise ValueError("JSON не містить ключі 'fact.today' або 'fact.data'")

    # Отримуємо цільову дату (більшу з доступних)
    day_ts, day_key = get_target_date(fact["data"])
    day_map = fact["data"].get(day_key, {})

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
    date_for_title = datetime.fromtimestamp(day_ts, ZoneInfo("Europe/Kyiv")).strftime("%d.%m.%Y")
    title_text = f"Графік погодинних відключень на {date_for_title}"
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

    # --- Рядок годин (тримірний) ---
    hour_y0 = table_y0 - HOUR_ROW_H
    hour_y1 = table_y0
    for h in range(24):
        x0 = table_x0 + LEFT_COL_W + h*CELL_W
        x1 = x0 + CELL_W
        draw.rectangle([x0, hour_y0, x1, hour_y1], fill=HEADER_BG, outline=GRID_COLOR)
        # трирядковий підпис
        start = f"{h:02d}"
        middle = "-"
        end = f"{(h+1)%24:02d}"
        # обчислення вертикальної позиції
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
        for h in range(24):
            h_key = str(h + 1)
            state = gp_hours.get(h_key, "yes")
            
            # Отримуємо стани сусідніх годин
            prev_h_key = str(h) if h > 0 else "24"
            next_h_key = str(h + 2) if h < 23 else "1"
            prev_state = gp_hours.get(prev_h_key, "yes")
            next_state = gp_hours.get(next_h_key, "yes")
            
            x0h = table_x0 + LEFT_COL_W + h*CELL_W
            x1h = x0h + CELL_W
            
            # Використовуємо функцію для малювання розділеної клітинки з урахуванням сусідів
            draw_split_cell(draw, x0h, y0, x1h, y1, state, prev_state, next_state, GRID_COLOR)

    # --- Лінії сітки ---
    for i in range(0, 25):
        x = table_x0 + LEFT_COL_W + i*CELL_W
        draw.line([(x, table_y0 - HOUR_ROW_H), (x, table_y1)], fill=GRID_COLOR)
    for r in range(n_rows+1):
        y = table_y0 + r*CELL_H
        draw.line([(table_x0, y), (table_x1, y)], fill=GRID_COLOR)

    # --- Легенда в один рядок ---
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

    # --- Інформація про публікацію ---
    pub_text = fact.get("update") or data.get("lastUpdated") or datetime.now(ZoneInfo('Europe/Kyiv')).strftime("%d.%m.%Y")
    pub_label = f"Опубліковано {pub_text}"
    bbox_pub = draw.textbbox((0,0), pub_label, font=font_small)
    w_pub = bbox_pub[2] - bbox_pub[0]
    pub_x = width - w_pub - SPACING
    pub_y = legend_y_start + box_size + 20
    draw.text((pub_x, pub_y), pub_label, fill=FOOTER_COLOR, font=font_small)

    out_name = OUT_DIR / "gpv-all-today.png"
    scale = 3
    img_resized = img.resize((img.width*scale, img.height*scale), resample=Image.LANCZOS)
    img_resized.save(out_name, optimize=True)
    log(f"Збережено {out_name}")

def generate_from_json(json_path):
    path = Path(json_path)
    if not path.exists():
        log(f"❌ JSON файл не знайдено: {json_path}")
        send_error(f"❌ JSON файл не знайдено: {json_path}")
        raise FileNotFoundError(f"JSON файл не знайдено: {json_path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    log(f"▶️ Запускаю генерацію зображення gpv-all-today.png з {json_path}")
    render(data, path)

def main():
    try:
        data, path = load_latest_json(JSON_DIR)
    except Exception as e:
        log(f"❌ Помилка при завантаженні JSON: {e}")
        send_error(f"❌ Помилка при завантаженні JSON: {e}")
        sys.exit(1)
    
    log("▶️ Запускаю генерацію зображення gpv-all-today.png з " + str(path))
    try:
        render(data, path)
    except Exception as e:
        log(f"❌ Помилка під час рендерингу: {e}")
        send_error(f"❌ Помилка під час рендерингу: {e}")
        raise

if __name__ == "__main__":
    main()