#!/bin/bash
# ----------------- run_main.sh -----------------

BASE_DIR="/home/yaroslav/bots/TOE_PARSER"
VENV_DIR="$BASE_DIR/venv"
LOG_FILE="$BASE_DIR/logs/cron_main.log"
LOG_DIR="logs"
FULL_LOG_FILE="${LOG_DIR}/full_log.log"
LOG_RETENTION_DAYS=14  # зберігати логи тільки 14 днів

# --- Підготовка ---
mkdir -p out logs "$LOG_DIR"

# Активуємо venv
source "$VENV_DIR/bin/activate"

# Переходимо в папку проекту
cd "$BASE_DIR"

# --- Видалення старих логів ---
find "$LOG_DIR" -type f -name "*.log" -mtime +$LOG_RETENTION_DAYS -exec rm -f {} \;

## --- Перевірка часу ---
#CURRENT_MIN=$(date +%M)
#CURRENT_HOUR=$(date +%H)
#
#echo "$(date +'%Y-%m-%d %H:%M:%S') [cron] Текуще время: $CURRENT_HOUR:$CURRENT_MIN" | tee -a "$FULL_LOG_FILE"
#
## Якщо між 00:00 та 00:06 — запускаємо main.py без аргументів
#if [[ $CURRENT_HOUR == "00" && $CURRENT_MIN -ge 0 && $CURRENT_MIN -lt 6 ]]; then
#    echo "$(date +'%Y-%m-%d %H:%M:%S') [cron] Нічне форс-оновлення (00:00–00:06) → запуск main.py" | tee -a "$FULL_LOG_FILE"
#    python3 src/main.py
#else
#    echo "$(date +'%Y-%m-%d %H:%M:%S') [cron] Звичайний запуск → main.py --download" | tee -a "$FULL_LOG_FILE"
#    python3 src/main.py --download
#fi

echo "$(date +'%Y-%m-%d %H:%M:%S') [cron] Звичайний запуск → main.py без аргументів" | tee -a "$FULL_LOG_FILE"
python3 src/main.py

# --- Відступ у логах ---
echo | tee -a "$FULL_LOG_FILE"
