#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Графік погодинних відключень для 1 групи на 2 дате.
Ліва колонка показує дату (напр., 13 листопада).
Години по вертикалі, як у останньому варіанті.
Решта (легенда, дата публікації) лишається.
Заголовок розділений на лівий і правий текст з виділенням фоном з заокругленими кутами.
Підтримка станів first/second/mfirst/msecond з розділенням клітинки на дві половини.
НОВЕ: Підсвічує зміни порівняно з попереднім графіком
"""
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
import locale
import sys
from telegram_notify import send_error

# Спроба встановити локаль для українських назв місяців
try:
    locale.setlocale(locale.LC_TIME, "uk_UA.UTF-8")
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, "Ukrainian_Ukraine.1251")
    except locale.Error:
        print("Попередження: не вдалося встановити українську локаль")

# --- Налаштування шляхів ---
BASE = Path(__file__).parent.parent.absolute()
JSON_DIR = BASE / "out"
OUT_DIR = BASE / "out/images"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PREV_STATE_DIR = BASE / "out/prev_state_1g"
PREV_STATE_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR = BASE / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
FULL_LOG_FILE = LOG_DIR / "full_log.log"

# Файл для збереження попереднього стану
PREV_STATE_FILE = PREV_STATE_DIR / "previous_state.json"

def log(message):
    """Логування повідомлень з timestamp"""
    timestamp = datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} [gener_im_1_G] {message}"
    print(line)
    try:
        with open(FULL_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"Помилка логування: {e}")

class Config:
    """Клас для зберігання всіх констант конфігурації"""
    CELL_W = 44 # Ширина однієї клітинки (1 година)
    CELL_H = 36 # Висота однієї клітинки
    LEFT_COL_W = 160 # Ширина лівої колонки з назвами груп
    SPACING = 60 # Відступи з усіх сторін
    HEADER_SPACING = 45 # Відстань між заголовком і рядком годин
    LEGEND_H = 100 # Висота області для легенди та інформації внизу
    HOUR_ROW_H = 70 # Висота рядка з годинами над таблицею
    HEADER_H = 34 # Висота заголовка
    RIGHT_TITLE_PADDING = 12 # Відступ між текстом правого заголовка і його фоном
    RIGHT_TITLE_RADIUS = 20 # Радіус заокруглення фону правого заголовка
    RIGHT_TITLE_EXTRA_H = 10 # Додаткова висота фону правого заголовка для кращого вигляду
    
    TITLE_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    TITLE_FONT_SIZE = 36
    HOUR_FONT_SIZE = 15
    DATE_FONT_SIZE = 20
    SMALL_FONT_SIZE = 16
    LEGEND_FONT_SIZE = 16
    
    BG = (250, 250, 250)
    TABLE_BG = (255, 255, 255)
    GRID_COLOR = (139, 139, 139)
    TEXT_COLOR = (0, 0, 0)
    HIGHLIGHT_COLOR = (0, 0, 0)
    HIGHLIGHT_BG = (255, 220, 115)
    HIGHLIGHT_BORDER = (0, 0, 0)
    OUTAGE_COLOR = (147, 170, 210)
    POSSIBLE_COLOR = (255, 220, 115)
    AVAILABLE_COLOR = (255, 255, 255)
    HEADER_BG = (245, 247, 250)
    FOOTER_COLOR = (140, 140, 140)
    WORSE_OUTLINE = (220, 53, 69)
    BETTER_OUTLINE = (40, 167, 69)
    HIGHLIGHT_WIDTH = 3 # Ширина контуру для підсвічування змін
    TIMEZONE = "Europe/Kyiv" # Часова зона для відображення дат і часу
    OUTPUT_SCALE = 3 # Масштаб для покращення якості зображення при збереженні

def load_previous_state():
    """Завантажує попередній стан графіків"""
    if PREV_STATE_FILE.exists():
        try:
            with open(PREV_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                log(f"📂 Завантажено попередній стан. Дата оновлення: {data.get('update', 'невідомо')}")
                return data
        except Exception as e:
            log(f"⚠️ Помилка при завантаженні попереднього стану: {e}")
    else:
        log(f"ℹ️ Файл попереднього стану не знайдено: {PREV_STATE_FILE}")
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
        log(f"💾 Збережено поточний стан у {PREV_STATE_FILE}. Дата оновлення: {state_to_save.get('update', 'невідомо')}")
    except Exception as e:
        log(f"⚠️ Помилка при збереженні поточного стану: {e}")

def calculate_outage_severity(state: str) -> int:
    """Повертає числове значення важкості відключення"""
    severity_map = {
        "yes": 0,
        "maybe": 2,
        "mfirst": 2,
        "msecond": 2,
        "first": 3,
        "second": 3,
        "no": 4
    }
    return severity_map.get(state, 0)

def compare_states(old_state: str, new_state: str) -> str:
    """Порівнює два стани"""
    old_severity = calculate_outage_severity(old_state)
    new_severity = calculate_outage_severity(new_state)
    
    if new_severity > old_severity:
        return "worse"
    elif new_severity < old_severity:
        return "better"
    return "same"

class FontManager:
    @staticmethod
    def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        try:
            path = Config.TITLE_FONT_PATH if bold else Config.FONT_PATH
            return ImageFont.truetype(path, size=size)
        except Exception as e:
            log(f"Помилка завантаження шрифту: {e}")
            return ImageFont.load_default()

class DataProcessor:
    @staticmethod
    def load_json_data(json_path: str) -> dict:
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"JSON файл не знайдено: {json_path}")
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        log(f"Завантажено JSON: {path.name}")
        return data
    
    @staticmethod
    def get_groups_from_data(data: dict) -> list:
        fact = data.get("fact", {})
        day_keys = list(fact.get("data", {}).keys())
        
        if not day_keys:
            raise ValueError("JSON не містить даних фактів")
        
        first_day = fact["data"][day_keys[0]]
        groups = list(first_day.keys())
        
        log(f"Знайдені групи: {groups}")
        return groups
    
    @staticmethod
    def get_dates_for_display(data: dict, max_dates: int = 2) -> list:
        fact = data.get("fact", {})
        day_keys = list(fact.get("data", {}).keys())[:max_dates]
        
        if not day_keys:
            raise ValueError("У JSON немає дат для відображення")
        
        return day_keys

class ImageRenderer:
    def __init__(self, data: dict, json_path: Path, group_name: str, prev_state: dict = None):
        self.data = data
        self.json_path = json_path
        self.group_name = group_name
        self.prev_data = prev_state.get("data", {}) if prev_state else {}
        self.font_manager = FontManager()
        self.processor = DataProcessor()
        self.changes_worse = 0
        self.changes_better = 0
        
        if self.prev_data:
            log(f"🔍 Попередні дані завантажені для {group_name}. Кількість днів: {len(self.prev_data)}")
        else:
            log(f"ℹ️ Попередніх даних немає для {group_name}")
        
    def render(self) -> None:
        try:
            day_keys = self.processor.get_dates_for_display(self.data)
            img = self._create_base_image(day_keys)
            draw = ImageDraw.Draw(img)
            
            self._draw_header(draw)
            self._draw_hours_header(draw, day_keys)
            self._draw_dates_column(draw, day_keys)
            self._draw_data_cells(draw, day_keys)
            self._draw_grid(draw, day_keys)
            self._draw_legend(draw, day_keys)
            self._draw_footer(draw)
            
            self._save_image(img)
            
            if self.changes_worse > 0 or self.changes_better > 0:
                log(f"📈 Зміни в графіку {self.group_name}: погіршень={self.changes_worse}, покращень={self.changes_better}")
            else:
                log(f"ℹ️ Графік {self.group_name}: змін не виявлено")
            
        except Exception as e:
            log(f"Помилка рендерингу для групи {self.group_name}: {e}")
            raise
    
    def _create_base_image(self, day_keys: list) -> Image.Image:
        n_hours = 24
        n_rows = len(day_keys)
        
        width = (Config.SPACING * 2 + Config.LEFT_COL_W + n_hours * Config.CELL_W)
        height = (Config.SPACING * 2 + Config.HEADER_H + Config.HOUR_ROW_H + 
                 n_rows * Config.CELL_H + Config.LEGEND_H + 40 + Config.HEADER_SPACING)
        
        return Image.new("RGB", (width, height), Config.BG)
    
    def _draw_header(self, draw: ImageDraw.Draw) -> None:
        font_title = self.font_manager.get_font(Config.TITLE_FONT_SIZE, bold=True)
        left_title = "Графік відключень:"
        draw.text((Config.SPACING, Config.SPACING), left_title, 
                 fill=Config.TEXT_COLOR, font=font_title)
        self._draw_right_header(draw, font_title)
    
    def _draw_right_header(self, draw: ImageDraw.Draw, font: ImageFont.FreeTypeFont) -> None:
        right_title = f"Черга {self.group_name.replace('GPV', '')}"
        bbox_right = draw.textbbox((0, 0), right_title, font=font)
        w_right = bbox_right[2] - bbox_right[0]
        h_right = bbox_right[3] - bbox_right[1]
        
        x0_bg = (Config.SPACING * 2 + Config.LEFT_COL_W + 24 * Config.CELL_W - 
                Config.SPACING - w_right - 2 * Config.RIGHT_TITLE_PADDING)
        y0_bg = Config.SPACING
        x1_bg = Config.SPACING * 2 + Config.LEFT_COL_W + 24 * Config.CELL_W - Config.SPACING
        y1_bg = Config.SPACING + h_right + Config.RIGHT_TITLE_EXTRA_H
        
        draw.rounded_rectangle([x0_bg, y0_bg, x1_bg, y1_bg], 
                             radius=Config.RIGHT_TITLE_RADIUS, 
                             fill=Config.HIGHLIGHT_BG, 
                             outline=Config.HIGHLIGHT_BORDER, 
                             width=3)
        
        text_x = x0_bg + (x1_bg - x0_bg - w_right) / 2
        text_y = y0_bg + (y1_bg - y0_bg - h_right) / 2
        draw.text((text_x, text_y), right_title, 
                 fill=Config.HIGHLIGHT_COLOR, font=font)
    
    def _draw_hours_header(self, draw: ImageDraw.Draw, day_keys: list) -> None:
        table_x0 = Config.SPACING
        hour_y0 = Config.SPACING + Config.HEADER_H + Config.HEADER_SPACING
        hour_y1 = hour_y0 + Config.HOUR_ROW_H
        
        font_hour = self.font_manager.get_font(Config.HOUR_FONT_SIZE)
        
        for h in range(24):
            x0 = table_x0 + Config.LEFT_COL_W + h * Config.CELL_W
            x1 = x0 + Config.CELL_W
            draw.rectangle([x0, hour_y0, x1, hour_y1], 
                          fill=Config.HEADER_BG, outline=Config.GRID_COLOR)
            
            next_hour = (h + 1) % 24
            lines = [f"{h:02d}", "–", f"{next_hour:02d}"]
            line_height = Config.HOUR_ROW_H / len(lines)
            
            for i, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=font_hour)
                w_line = bbox[2] - bbox[0]
                h_line = bbox[3] - bbox[1]
                y = hour_y0 + i * line_height + (line_height - h_line) / 2
                draw.text((x0 + (Config.CELL_W - w_line) / 2, y), 
                         line, fill=Config.TEXT_COLOR, font=font_hour)
    
    def _draw_dates_column(self, draw: ImageDraw.Draw, day_keys: list) -> None:
        table_x0 = Config.SPACING
        table_y0 = (Config.SPACING + Config.HEADER_H + 
                   Config.HOUR_ROW_H + Config.HEADER_SPACING)
        
        draw.rectangle([table_x0, table_y0 - Config.HOUR_ROW_H, 
                       table_x0 + Config.LEFT_COL_W, table_y0], 
                      fill=Config.HEADER_BG, outline=Config.GRID_COLOR)
        
        font_date = self.font_manager.get_font(Config.DATE_FONT_SIZE)
        header_text = "Дата"
        bbox_header = draw.textbbox((0, 0), header_text, font=font_date)
        w_header = bbox_header[2] - bbox_header[0]
        h_header = bbox_header[3] - bbox_header[1]
        
        draw.text((table_x0 + (Config.LEFT_COL_W - w_header) / 2,
                  table_y0 - Config.HOUR_ROW_H + (Config.HOUR_ROW_H - h_header) / 2),
                 header_text, fill=Config.TEXT_COLOR, font=font_date)
        
        for r, day_key in enumerate(day_keys):
            y0 = table_y0 + r * Config.CELL_H
            draw.rectangle([table_x0, y0, table_x0 + Config.LEFT_COL_W, y0 + Config.CELL_H], 
                          fill=Config.TABLE_BG, outline=Config.GRID_COLOR)
            
            dt = datetime.fromtimestamp(int(day_key), ZoneInfo(Config.TIMEZONE))
            date_label = dt.strftime("%d %B")
            bbox = draw.textbbox((0, 0), date_label, font=font_date)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            
            draw.text((table_x0 + (Config.LEFT_COL_W - w) / 2, 
                      y0 + (Config.CELL_H - h) / 2), 
                     date_label, fill=Config.TEXT_COLOR, font=font_date)
    
    def _draw_split_cell(self, draw: ImageDraw.Draw, x0: int, y0: int, x1: int, y1: int, 
                        state: str, prev_state: str, next_state: str, outline_color: tuple,
                        change_type: str = None):
        cell_width = x1 - x0
        half_width = cell_width // 2

        if state == "yes":
            left_color = right_color = Config.AVAILABLE_COLOR
        elif state == "no":
            left_color = right_color = Config.OUTAGE_COLOR
        elif state == "maybe":
            left_color = right_color = Config.POSSIBLE_COLOR
        elif state == "first":
            left_color = Config.OUTAGE_COLOR
            right_color = Config.OUTAGE_COLOR if next_state in ["no", "first","maybe"] else Config.AVAILABLE_COLOR
        elif state == "second":
            right_color = Config.OUTAGE_COLOR
            left_color = Config.OUTAGE_COLOR if prev_state in ["no", "second","maybe"] else Config.AVAILABLE_COLOR
        elif state == "mfirst":
            left_color = Config.POSSIBLE_COLOR
            if next_state is not None:
                if next_state in ["no", "first"]:
                    right_color = Config.OUTAGE_COLOR
                else:
                    right_color = Config.AVAILABLE_COLOR
            else:
                if prev_state in ["no", "first", "second","maybe", "mfirst","msecond"]:
                    right_color = Config.AVAILABLE_COLOR
                else:
                    right_color = Config.OUTAGE_COLOR
        elif state == "msecond":
            right_color = Config.POSSIBLE_COLOR
            if prev_state is not None:
                if prev_state in ["no", "second"]:
                    left_color = Config.OUTAGE_COLOR
                else:
                    left_color = Config.AVAILABLE_COLOR
            else:
                if next_state in ["no", "first", "second","maybe", "mfirst","msecond"]:
                    left_color = Config.AVAILABLE_COLOR
                else:
                    left_color = Config.OUTAGE_COLOR
        else:
            left_color = right_color = Config.AVAILABLE_COLOR

        if left_color == right_color:
            draw.rectangle([x0, y0, x1, y1], fill=left_color, outline=outline_color)
        else:
            draw.rectangle([x0, y0, x0 + half_width, y1], fill=left_color)
            draw.rectangle([x0 + half_width, y0, x1, y1], fill=right_color)
            draw.rectangle([x0, y0, x1, y1], outline=outline_color, fill=None)
        
        if change_type == "worse":
            for i in range(Config.HIGHLIGHT_WIDTH):
                draw.rectangle([x0 + i, y0 + i, x1 - i, y1 - i], outline=Config.WORSE_OUTLINE)
        elif change_type == "better":
            for i in range(Config.HIGHLIGHT_WIDTH):
                draw.rectangle([x0 + i, y0 + i, x1 - i, y1 - i], outline=Config.BETTER_OUTLINE)
    
    def _draw_data_cells(self, draw: ImageDraw.Draw, day_keys: list) -> None:
        table_x0 = Config.SPACING
        table_y0 = (Config.SPACING + Config.HEADER_H + 
                   Config.HOUR_ROW_H + Config.HEADER_SPACING)
        
        fact = self.data.get("fact", {})
        
        for r, day_key in enumerate(day_keys):
            y0 = table_y0 + r * Config.CELL_H
            day_map = fact["data"][day_key]
            gp_hours = day_map.get(self.group_name, {})
            
            prev_day_map = self.prev_data.get(day_key, {})
            prev_gp_hours = prev_day_map.get(self.group_name, {}) if isinstance(prev_day_map, dict) else {}
            
            if r == 0 and prev_gp_hours:
                log(f"🔍 День {day_key}, група {self.group_name}: знайдено {len(prev_gp_hours)} годин у попередніх даних")
            
            for h in range(24):
                h_key = str(h+1)
                state = gp_hours.get(h_key, "yes")
                
                prev_h_key = str(h) if h > 0 else None
                next_h_key = str(h + 2) if h < 23 else None
                prev_state = gp_hours.get(prev_h_key) if prev_h_key else None
                next_state = gp_hours.get(next_h_key) if next_h_key else None
                
                change_type = None
                if prev_gp_hours and h_key in prev_gp_hours:
                    old_state = prev_gp_hours[h_key]
                    comparison = compare_states(old_state, state)
                    
                    if comparison != "same" and self.changes_worse == 0 and self.changes_better == 0:
                        log(f"🔍 Перша зміна: день={day_key}, година={h_key}, старий={old_state}, новий={state}, тип={comparison}")
                    
                    if comparison == "worse":
                        change_type = "worse"
                        self.changes_worse += 1
                    elif comparison == "better":
                        change_type = "better"
                        self.changes_better += 1
                
                x0 = table_x0 + Config.LEFT_COL_W + h * Config.CELL_W
                x1 = x0 + Config.CELL_W
                
                self._draw_split_cell(draw, x0, y0, x1, y0 + Config.CELL_H, 
                                     state, prev_state, next_state, Config.GRID_COLOR,
                                     change_type)
    
    def _draw_grid(self, draw: ImageDraw.Draw, day_keys: list) -> None:
        n_rows = len(day_keys)
        table_x0 = Config.SPACING
        table_y0 = (Config.SPACING + Config.HEADER_H + 
                   Config.HOUR_ROW_H + Config.HEADER_SPACING)
        table_x1 = table_x0 + Config.LEFT_COL_W + 24 * Config.CELL_W
        table_y1 = table_y0 + n_rows * Config.CELL_H
        
        for i in range(25):
            x = table_x0 + Config.LEFT_COL_W + i * Config.CELL_W
            draw.line([(x, table_y0 - Config.HOUR_ROW_H), (x, table_y1)], 
                     fill=Config.GRID_COLOR)
        
        for r in range(n_rows + 1):
            y = table_y0 + r * Config.CELL_H
            draw.line([(table_x0, y), (table_x1, y)], 
                     fill=Config.GRID_COLOR)
    
    def _get_description_for_state(self, state: str) -> str:
        preset = self.data.get("preset", {})
        time_type = preset.get("time_type", {})
        descriptions = {
            "yes": "Електроенергія розподіляється",
            "no": "Електроенергія відсутня", 
            "maybe": "Можливе відключення",
            "first": "Світла не буде перші 30 хв.",
            "second": "Світла не буде другі 30 хв.",
            "mfirst": "Світла можливо не буде перші 30 хв.",
            "msecond": "Світла можливо не буде другі 30 хв."
        }
        return time_type.get(state, descriptions.get(state, "Невідомий стан"))
    
    def _draw_legend(self, draw: ImageDraw.Draw, day_keys: list) -> None:
        n_rows = len(day_keys)
        table_y1 = (Config.SPACING + Config.HEADER_H + 
                   Config.HOUR_ROW_H + Config.HEADER_SPACING + 
                   n_rows * Config.CELL_H)
        
        legend_states = ["yes", "no", "maybe"]
        legend_items = []
        for state in legend_states:
            color = self._get_color_for_state(state)
            description = self._get_description_for_state(state)
            legend_items.append((color, description, state))
        
        legend_y = table_y1 + 15
        box_size = 20
        gap = 15
        x_cursor = Config.SPACING
        
        font_legend = self.font_manager.get_font(Config.LEGEND_FONT_SIZE)
        
        for col, text, state in legend_items:
            text_bbox = draw.textbbox((0, 0), text, font=font_legend)
            w_text = text_bbox[2] - text_bbox[0]
            block_w = box_size + 6 + w_text
            
            draw.rectangle([x_cursor, legend_y, x_cursor + box_size, legend_y + box_size], 
                          fill=col, outline=Config.GRID_COLOR)
            
            draw.text((x_cursor + box_size + 4, legend_y + (box_size - (text_bbox[3]-text_bbox[1]))/2), 
                     text, fill=Config.TEXT_COLOR, font=font_legend)
            x_cursor += block_w + gap
        
        if self.changes_worse > 0 or self.changes_better > 0:
            x_cursor += gap * 2
            
            draw.rectangle([x_cursor, legend_y, x_cursor + box_size, legend_y + box_size], 
                          fill=Config.TABLE_BG, outline=Config.WORSE_OUTLINE, width=Config.HIGHLIGHT_WIDTH)
            worse_text = "Більше відключень"
            text_bbox = draw.textbbox((0, 0), worse_text, font=font_legend)
            draw.text((x_cursor + box_size + 4, legend_y + (box_size - (text_bbox[3]-text_bbox[1]))/2), 
                     worse_text, fill=Config.TEXT_COLOR, font=font_legend)
            x_cursor += box_size + 4 + (text_bbox[2] - text_bbox[0]) + gap
            
            draw.rectangle([x_cursor, legend_y, x_cursor + box_size, legend_y + box_size], 
                          fill=Config.TABLE_BG, outline=Config.BETTER_OUTLINE, width=Config.HIGHLIGHT_WIDTH)
            better_text = "Менше відключень"
            text_bbox = draw.textbbox((0, 0), better_text, font=font_legend)
            draw.text((x_cursor + box_size + 4, legend_y + (box_size - (text_bbox[3]-text_bbox[1]))/2), 
                     better_text, fill=Config.TEXT_COLOR, font=font_legend)
    
    def _get_color_for_state(self, state: str) -> tuple:
        color_map = {
            "yes": Config.AVAILABLE_COLOR,
            "no": Config.OUTAGE_COLOR,
            "maybe": Config.POSSIBLE_COLOR,
            "first": Config.OUTAGE_COLOR,
            "second": Config.OUTAGE_COLOR,
            "mfirst": Config.POSSIBLE_COLOR,
            "msecond": Config.POSSIBLE_COLOR
        }
        return color_map.get(state, Config.AVAILABLE_COLOR)
    
    def _draw_footer(self, draw: ImageDraw.Draw) -> None:
        fact = self.data.get("fact", {})
        pub_text = (fact.get("update") or 
                   self.data.get("lastUpdated") or 
                   datetime.now(ZoneInfo(Config.TIMEZONE)).strftime("%d.%m.%Y"))
        
        pub_label = f"Опубліковано {pub_text}"
        font_small = self.font_manager.get_font(Config.SMALL_FONT_SIZE)
        bbox_pub = draw.textbbox((0, 0), pub_label, font=font_small)
        w_pub = bbox_pub[2] - bbox_pub[0]
        
        width = Config.SPACING * 2 + Config.LEFT_COL_W + 24 * Config.CELL_W
        legend_bottom = (Config.SPACING + Config.HEADER_H + Config.HOUR_ROW_H + 
                        Config.HEADER_SPACING + len(self.processor.get_dates_for_display(self.data)) * Config.CELL_H + 
                        Config.LEGEND_H)
        
        draw.text((width - w_pub - Config.SPACING, legend_bottom - 20), 
                 pub_label, fill=Config.FOOTER_COLOR, font=font_small)
        
        x_text = Config.SPACING
        y_base = legend_bottom - 20
        line_gap = 6

        info_lines = [
            "Цей проєкт створено волонтерами для вас. Разом ми можемо зробити інформацію доступною для всіх.",
            "Помітили розбіжності між графіком та офіційним джерелом? Напишіть нам: https://t.me/OUTAGE_CHAT",
            "Офіційна спільнота проєкту: https://t.me/svitlobot_api"        
        ]


        for i, line in enumerate(info_lines):
            bbox_line = draw.textbbox((0, 0), line, font=font_small)
            draw.text((x_text, y_base + i * (bbox_line[3] - bbox_line[1] + line_gap)),
                      line, fill=Config.FOOTER_COLOR, font=font_small)
    
    def _save_image(self, img: Image.Image) -> None:
        safe_group_name = self.group_name.replace('GPV', '').replace('.', '-')
        out_name = OUT_DIR / f"gpv-{safe_group_name}-emergency.png"
        
        img_resized = img.resize((img.width * Config.OUTPUT_SCALE, 
                                img.height * Config.OUTPUT_SCALE), 
                               resample=Image.LANCZOS)
        img_resized.save(out_name, optimize=True)
        log(f"✅ Збережено {out_name}")

def generate_from_json(json_path: str, prev_state: dict = None):
    """
    Генерація зображень для всіх груп з JSON файлу
    
    Args:
        json_path: Шлях до JSON файлу
        prev_state: Попередній стан (необов'язковий). Якщо None - завантажується автоматично
    """
    # ВИПРАВЛЕННЯ: Якщо prev_state не передано - завантажуємо автоматично
    if prev_state is None:
        log("ℹ️ prev_state не передано, завантажую автоматично")
        prev_state = load_previous_state()
    
    processor = DataProcessor()
    data = processor.load_json_data(json_path)
    groups = processor.get_groups_from_data(data)
    
    for group in groups:
        log(f"▶ Генерую для {group}…")
        renderer = ImageRenderer(data, Path(json_path), group, prev_state)
        renderer.render()
    
    #Зберігаємо поточний стан після генерації всіх груп
    save_current_state(data)
    log("💾 Збережено поточний стан після генерації груп")

def load_latest_json(json_dir: Path):
    """Завантаження останнього JSON"""
    files = sorted(json_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("Не знайдено JSON файлів у " + str(json_dir))
    return files[0]

def main():
    """Основна функція"""
    try:
        path = load_latest_json(JSON_DIR)
    except Exception as e:
        log(f"❌ Помилка при завантаженні JSON: {e}")
        send_error(f"❌ Помилка при завантаженні JSON: {e}")
        sys.exit(1)
    
    log(f"Використовується JSON: {path}")
    
    # Завантажуємо попередній стан
    prev_state = load_previous_state()
    
    try:
        # Завантажуємо поточні дані
        processor = DataProcessor()
        current_data = processor.load_json_data(str(path))
        
        # Генеруємо з порівнянням
        generate_from_json(str(path), prev_state)
        
        # Зберігаємо поточний стан
        save_current_state(current_data)
        
        log("✅ Генерація завершена успішно")
    except Exception as e:
        log(f"❌ Помилка: {e}")
        send_error(f"❌ Помилка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()