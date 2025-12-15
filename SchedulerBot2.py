import os
import json
import time
import logging
import subprocess
from datetime import datetime, timedelta
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

#================= CONFIG =================
with open("config.json", "r") as f:
    config = json.load(f)

BOT_TOKEN = config["BOT_TOKEN"]
VIDEO_FOLDERS = config["VIDEO_FOLDER"]
SCHEDULE_JSON = config["SCHEDULE_JSON"]
FILES_PER_PAGE = 50
RATE_LIMIT_SECONDS = config["TIME_LIMIT"]

USER_RATE_LIMITS = {}

#================= LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("bot_actions.log"), logging.StreamHandler()]
)

#================ UTILITIES ================
def get_video_files(exts=('.mp4','.mkv','.ts','.mov','.avi','.mp3','.wav','.xml','.txt')):
    files=[]
    for folder in VIDEO_FOLDERS:
        for f in os.listdir(folder):
            if f.lower().endswith(exts):
                files.append(f"{folder}||{f}")
    return files

def get_files_from_folder(folder, sort_new_first=True):
    files=[f"{folder}||{f}" for f in os.listdir(folder)]
    files.sort(key=lambda x: os.path.getmtime(os.path.join(*x.split("||"))), reverse=sort_new_first)
    return files

def get_duration(path):
    try:
        output=subprocess.check_output(
            ['ffprobe','-v','error','-show_entries','format=duration',
             '-of','default=nokey=1:noprint_wrappers=1',path]
        ).decode().strip()
        return timedelta(seconds=int(float(output)))
    except:
        return timedelta(minutes=5)

def read_schedule():
    return json.load(open(SCHEDULE_JSON,"r",encoding="utf-8")) if os.path.exists(SCHEDULE_JSON) else []

def write_schedule(data):
    json.dump(data,open(SCHEDULE_JSON,"w",encoding="utf-8"),indent=4)


#================ RATE LIMIT ================
def rate_limit_start(func):
    @wraps(func)
    async def wrapper(update: Update, context):
        user_id = update.effective_user.id
        now = time.time()
        last = USER_RATE_LIMITS.get(user_id,0)
        left = RATE_LIMIT_SECONDS - (now-last)

        if left>0:
            mins=int(left//60); sec=int(left%60)
            txt="⏳ Try again after "
            if mins>0: txt+=f"{mins} min "
            txt+=f"{sec} sec"

            if update.callback_query:
                await update.callback_query.answer(txt, show_alert=True)
            else:
                await update.message.reply_text(txt)
            return

        USER_RATE_LIMITS[user_id]=now
        return await func(update,context)
    return wrapper


#================ START (FOLDER LIST) ================
@rate_limit_start
async def start(update:Update,context):
    buttons=[[InlineKeyboardButton(f"📁 {os.path.basename(f)}",callback_data=f"folder_{f}")]
             for f in VIDEO_FOLDERS]
    markup = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await update.callback_query.edit_message_text("📂 Select Folder:",reply_markup=markup)
    else:
        await update.message.reply_text("📂 Select Folder:",reply_markup=markup)


#================ PAGINATION =================
async def send_page(update_or_q, context, page):
    files=context.user_data.get("files",[])
    total=len(files)
    pages = max(1,(total-1)//FILES_PER_PAGE+1)

    page=max(0,min(page,pages-1))
    start=page*FILES_PER_PAGE
    end=min(start+FILES_PER_PAGE,total)

    keyboard=[]

    for i in range(start,end):
        folder,fname=files[i].split("||")
        keyboard.append([InlineKeyboardButton(fname,callback_data=f"file_{i}")])

    # Pagination Controls
    nav=[]
    if page>0:
        nav.append(InlineKeyboardButton("⬅ Prev", callback_data=f"page_{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{pages}", callback_data="noop"))
    if page<pages-1:
        nav.append(InlineKeyboardButton("Next ➡", callback_data=f"page_{page+1}"))

    keyboard.append(nav)

    keyboard.append([
        InlineKeyboardButton("⬅ Back to Folder", callback_data="back_to_folder"),
        InlineKeyboardButton("🔄 New", callback_data="sort_new"),
        InlineKeyboardButton("⏳ Old", callback_data="sort_old")
    ])

    markup=InlineKeyboardMarkup(keyboard)

    if isinstance(update_or_q,Update):
        await update_or_q.message.reply_text("📂 Select File",reply_markup=markup)
    else:
        await update_or_q.edit_message_text("📂 Select File",reply_markup=markup)

    context.user_data["page"]=page



#================ SEARCH =================
async def search(update:Update,context):
    if not context.args:
        return await update.message.reply_text("Use:  `/search name`",parse_mode="Markdown")

    key=" ".join(context.args).lower()
    files=[f for f in get_video_files() if key in f.lower()]

    if not files:
        return await update.message.reply_text("❌ No matching files")

    context.user_data["files"]=files
    await send_page(update,context,0)



#================ CALLBACK HANDLER =================
async def callback(update:Update,context):
    q=update.callback_query; data=q.data
    await q.answer()

    # Pagination
    if data.startswith("page_"):
        return await send_page(q,context,int(data.split("_")[1]))

    if data=="noop":
        return

    # Folder selection
    if data.startswith("folder_"):
        folder=data.split("_",1)[1]
        context.user_data["folder"]=folder
        context.user_data["files"]=get_files_from_folder(folder)
        return await send_page(q,context,0)

    if data=="back_to_folder":
        buttons = [[InlineKeyboardButton(f"📁 {os.path.basename(f)}", callback_data=f"folder_{f}")]
               for f in VIDEO_FOLDERS]
        markup = InlineKeyboardMarkup(buttons)
        return await q.edit_message_text("📂 Select Folder:", reply_markup=markup)        

    # Sorting
    if data=="sort_new":
        context.user_data["files"]=get_files_from_folder(context.user_data["folder"],True)
        return await send_page(q,context,0)

    if data=="sort_old":
        context.user_data["files"]=get_files_from_folder(context.user_data["folder"],False)
        return await send_page(q,context,0)

    # File Selected → Add schedule
    if data.startswith("file_"):
        idx=int(data.split("_")[1])
        folder,filename=context.user_data["files"][idx].split("||")
        full=os.path.join(folder,filename)

        sched=read_schedule()
        last_id=max([i["id"] for i in sched],default=0)+1
        now=datetime.now()

        if sched:
            last_end=datetime.strptime(sched[-1]["end"],"%d %b %Y %I:%M:%S %p")
            start_time = last_end if last_end>now else now+timedelta(seconds=30)
        else:
            start_time=now+timedelta(seconds=30)

        dur=get_duration(full)
        end=start_time+dur

        entry={
            "id":last_id,
            "title":os.path.splitext(filename)[0],
            "path":full,
            "start":start_time.strftime("%d %b %Y %I:%M:%S %p"),
            "duration":str(dur),
            "end":end.strftime("%d %b %Y %I:%M:%S %p"),
            "user":update.effective_user.full_name
        }

        sched.append(entry)
        write_schedule(sched)

        await q.edit_message_text(
            f"✅ Scheduled\n🎬 *{entry['title']}*\n⏳Start Time {entry['start']} → {entry['end']}",
            parse_mode="Markdown"
        )


#================ RUN BOT =================
if __name__=="__main__":
    app=ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("search",search))
    app.add_handler(CallbackQueryHandler(callback))
    print("BOT RUNNING ✔")
    app.run_polling()
