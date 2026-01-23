#!/usr/bin/env python3
import os
import shutil
from datetime import datetime
from config import REGION, SOURCE_JSON, SOURCE_IMAGES, REPO_DIR, DATA_DIR, IMAGES_DIR, LOG_FILE, TIMEZONE

def log(message):
    timestamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    text = f"{timestamp} [upload_to_github] {message}"
    print(text)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except:
        pass


def run_upload():
    log(f"🚀 Початок оновлення даних для {REGION}...")

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(REPO_DIR, "images"), exist_ok=True)

    # ------------------- JSON -------------------
    target_json = os.path.join(DATA_DIR, f"{REGION}.json")

    if os.path.exists(SOURCE_JSON):
        shutil.copy2(SOURCE_JSON, target_json)
        log(f"✅ JSON оновлено → {target_json}")
    else:
        log("❗ JSON не знайдено — припиняю оновлення!")
        return

    # ------------------- ЗОБРАЖЕННЯ -------------------
    if os.path.exists(IMAGES_DIR):
        shutil.rmtree(IMAGES_DIR)
        log("🗑 Видалено старі зображення")

    if os.path.exists(SOURCE_IMAGES):
        shutil.copytree(SOURCE_IMAGES, IMAGES_DIR)
        log(f"🖼 Нові зображення скопійовано → {IMAGES_DIR}")
    else:
        log("⚠️ Папка з новими зображеннями не знайдена")

    current_time = datetime.now(TIMEZONE)
    
    # У своїй системі парсерів я перейшов на окремий поток для вивантаження на GitHub, 
    # так як іноді виникають проблеми з одночасним вивантаженням з декількох потоків.
    # Якщо ви використовуєте тільки один потік, можете розкоментувати код нижче
    # ------------------- GIT -------------------
    #try:
    #    log("▶️ git pull --rebase --autostash")
    #    subprocess.check_call(["git", "pull", "--rebase", "--autostash"], cwd=REPO_DIR)
    #
    #    log("▶️ git add .")
    #    subprocess.check_call(["git", "add", "."], cwd=REPO_DIR)
    #
    #    commit_msg = f"{REGION} update {current_time.strftime('%Y-%m-%d %H:%M:%S')}"
    #    log(f"▶️ git commit -m '{commit_msg}'")
    #
    #    if subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=REPO_DIR).returncode != 0:
    #        subprocess.check_call(["git", "commit", "-m", commit_msg], cwd=REPO_DIR)
    #        log(f"✔️ Коміт: {commit_msg}")
    #    else:
    #        log("ℹ️ Змін для коміту немає")
    #        return
    #
    #    log("▶️ git push")
    #    subprocess.check_call(["git", "push"], cwd=REPO_DIR)
    #
    #    log("🎉 Дані опубліковано в GitHub")
    #
    #except subprocess.CalledProcessError as e:
    #    log(f"❌ ПОМИЛКА Git: {e}")
    #    raise e


if __name__ == "__main__":
    try:
        run_upload()
    except Exception as e:
        log(f"❌ Завантаження на GitHub не вдалося: {e}")
