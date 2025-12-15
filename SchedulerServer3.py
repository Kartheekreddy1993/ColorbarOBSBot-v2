import obsws_python as obs
import schedule
import json
import time
import os
import subprocess
import threading
from datetime import datetime, timedelta

JSON_SCHEDULE_FILE = r".\schedule.json"
NOW_FILE = r".\Info\now.txt"
PENDING_FILE = r".\Info\pending_jobs.txt"

LAST_JSON_MTIME = 0
SCHEDULED_KEYS = set()   # prevent duplicates


# ================= SAFE JSON LOADER ================= #

def safe_json_load(path, retries=5, delay=0.2):
    for _ in range(retries):
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read().strip()
                if not text:
                    raise ValueError("Empty JSON")
                return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            time.sleep(delay)
    print("⚠ JSON read failed (file busy). Skipping update.")
    return None


# ================= NOW PLAY FUNCTION ================= #

def play_playlist(playlist_path, title, user):
    cl = obs.ReqClient(host='localhost', port=4455, password='secret', timeout=3)
    cl.set_current_program_scene("Schedule")

    inputname = "schedulesource"
    inputsettings = {
        'playlist': [
            {'hidden': False, 'selected': False, 'value': playlist_path}
        ]
    }
    cl.set_input_settings(inputname, inputsettings, overlay=True)

    with open(NOW_FILE, "w", encoding="utf-8") as f:
        f.write(f"{title} | {user}")

    print(f"Now Playing -> {title} | {user}")

    return schedule.CancelJob   # 🔥 run once, no tomorrow repeat


# ================= PENDING JOBS WRITER ================= #

def log_pending_jobs():
    now = datetime.now()
    today = now.date()
    buffer_time = now + timedelta(seconds=15)

    jobs = schedule.get_jobs()

    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        valid_jobs = []

        for job in jobs:
            if not job.next_run:
                continue

            # Only today’s jobs
            if job.next_run.date() != today:
                continue

            # Must be at least 15 seconds in the future
            if job.next_run <= buffer_time:
                continue

            valid_jobs.append(job)

        if not valid_jobs:
            f.write("All Time HITS\n")
            return

        for job in sorted(valid_jobs, key=lambda j: j.next_run):
            start = job.next_run.strftime("%I:%M %p")
            path, title, user = job.job_func.args
            f.write(f"{start} | {title} | {user}\n")


# ================= BACKGROUND THREAD ================= #

def pending_jobs_worker(interval=1):
    while True:
        try:
            log_pending_jobs()
        except Exception as e:
            print("Pending thread error:", e)
        time.sleep(interval)


def start_pending_thread():
    t = threading.Thread(target=pending_jobs_worker, daemon=True)
    t.start()


# ================= LOAD / UPDATE SCHEDULE ================= #

def load_schedule_if_changed():
    global LAST_JSON_MTIME

    if not os.path.exists(JSON_SCHEDULE_FILE):
        return

    mtime = os.path.getmtime(JSON_SCHEDULE_FILE)
    if mtime == LAST_JSON_MTIME:
        return

    LAST_JSON_MTIME = mtime
    print("\n--- schedule.json updated ---")

    data = safe_json_load(JSON_SCHEDULE_FILE)
    if not data:
        return

    today_str = datetime.now().strftime("%d %b %Y")
    now = datetime.now()

    for item in data:
        start = datetime.strptime(item["start"], "%d %b %Y %I:%M:%S %p")

        if start.strftime("%d %b %Y") != today_str:
            continue
        if start <= now:
            continue

        key = f"{item['start']}|{item['title']}|{item.get('user','Unknown')}"
        if key in SCHEDULED_KEYS:
            continue

        time_str = start.strftime("%H:%M:%S")

        schedule.every().day.at(time_str).do(
            play_playlist,
            item["path"],
            item["title"],
            item.get("user", "Unknown")
        )

        SCHEDULED_KEYS.add(key)
        print(f"Scheduled -> {time_str} | {item['title']} | {item.get('user','Unknown')}")


# ================= MAIN LOOP ================= #

def schedule_playlists():
    print("\n========== Scheduler Started ==========\n")

    start_pending_thread()
    load_schedule_if_changed()

    while True:
        schedule.run_pending()
        load_schedule_if_changed()
        time.sleep(1)


# ================= HTTP SERVER ================= #

def start_http_server():
    server_path = r"C:\Program Files\Colorbar Select v2\Info"
    command = ["python", "-m", "http.server", "8000"]
    subprocess.Popen(command, cwd=server_path)
    print("\n>>> HTTP Server running at http://localhost:8000/\n")


# ================= START ================= #

start_http_server()
schedule_playlists()
