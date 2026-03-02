import os
import asyncio
import pandas as pd
import matplotlib.pyplot as plt
import gspread

from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google.oauth2.service_account import Credentials

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =============================
# CONFIG
# =============================
TOKEN = "8618925046:AAEwxmSh3X-gNXBzcv2LLWKYu20q53aM9sg"
CHAT_ID = 104256754

SPREADSHEET_ID = "1DAKEtO0g4DahPhxuKBVQ2xEz2uy_NSIacdq32uMPb1Y"

TARGET_HARIAN = 4
SEKTOR_LIST = ["UBR 1", "UBR 2", "B2B"]

LABOR, SEKTOR, SC = range(3)

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["/input", "/lapor"],
        ["/batal"]
    ],
    resize_keyboard=True
)

# =============================
# GOOGLE SHEET
# =============================
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

import os

SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
if os.path.exists("/etc/secrets/service_account.json"):
    SERVICE_ACCOUNT_FILE = "/etc/secrets/service_account.json"

creds = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=scope,
)

client = gspread.authorize(creds)
spreadsheet = client.open_by_key(SPREADSHEET_ID)

sheet_input = spreadsheet.worksheet("DATA INPUTAN")
sheet_teknisi = spreadsheet.worksheet("data_teknisi")

# =============================
# DASHBOARD ENGINE
# =============================
def generate_dashboard(sektor):

    df_input = pd.DataFrame(sheet_input.get_all_records())
    df_teknisi = pd.DataFrame(sheet_teknisi.get_all_records())

    df_input.columns = df_input.columns.str.lower().str.strip()
    df_teknisi.columns = df_teknisi.columns.str.lower().str.strip()

    teknisi = df_teknisi[df_teknisi["sektor"] == sektor]

    if not df_input.empty:
        count = (
            df_input[df_input["sektor"] == sektor]
            .groupby("nama_teknisi")
            .size()
            .reset_index(name="input")
        )
    else:
        count = pd.DataFrame(columns=["nama_teknisi","input"])

    df = teknisi.merge(count,on="nama_teknisi",how="left")

    df["input"] = df["input"].fillna(0)
    df["ach"] = (df["input"]/TARGET_HARIAN)*100

    df = df.sort_values("input",ascending=False)
    df.reset_index(drop=True,inplace=True)
    df.index += 1

    total_input = int(df["input"].sum())
    total_ach = (total_input/(len(df)*TARGET_HARIAN))*100

    filename=f"dashboard_{sektor}.png"
    if os.path.exists(filename):
        os.remove(filename)

    # =====================
    # CREATE FIGURE
    # =====================
    fig, ax = plt.subplots(figsize=(9,11))
    ax.axis("off")

    table_data=[
        [i,
         str(r["nama_teknisi"]),
         int(r["input"]),
         f'{r["ach"]:.1f}%']
        for i,r in df.iterrows()
    ]

    table=ax.table(
        cellText=table_data,
        colLabels=["Rank","Teknisi","Input","Ach"],
        cellLoc="center",
        loc="center"
    )

    # =====================
    # FIX COLUMN WIDTH
    # =====================
    col_widths=[0.08,0.55,0.15,0.15]

    for i,width in enumerate(col_widths):
        for key,cell in table.get_celld().items():
            if key[1]==i:
                cell.set_width(width)

    # =====================
    # STYLE
    # =====================
    table.auto_set_font_size(False)
    table.set_fontsize(9)

    for (row,col),cell in table.get_celld().items():

        cell.set_height(0.035)

        if row==0:
            cell.set_facecolor("#40466e")
            cell.set_text_props(color="white",weight="bold")

        else:
            val=df.iloc[row-1]["input"]

            if val>=TARGET_HARIAN:
                cell.set_facecolor("#c8f7c5")
            else:
                cell.set_facecolor("#f7c5c5")

    plt.title(
        f"DASHBOARD {sektor}\n"
        f"TOTAL INPUT : {total_input} | ACH : {total_ach:.1f}%",
        fontsize=14,
        weight="bold"
    )

    plt.savefig(filename,bbox_inches="tight",dpi=200)
    plt.close()

    return filename

# =============================
# SEND DASHBOARD
# =============================
async def kirim_dashboard(app):

    for sektor in SEKTOR_LIST:

        file=generate_dashboard(sektor)

        await app.bot.send_photo(
            chat_id=CHAT_ID,
            photo=open(file,"rb"),
            caption=f"📊 REPORT {sektor}"
        )

# =============================
# COMMAND
# =============================
async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "✅ BOT SOBI READY",
        reply_markup=MAIN_MENU
    )

async def input_cmd(update:Update,context):
    await update.message.reply_text(
        "Masukkan Labor Teknisi:",
        reply_markup=ReplyKeyboardRemove()
    )
    return LABOR

async def labor(update:Update,context):
    context.user_data["labor"]=update.message.text
    await update.message.reply_text("Pilih sektor: UBR 1 / UBR 2 / B2B")
    return SEKTOR

async def sektor(update:Update,context):
    context.user_data["sektor"]=update.message.text
    await update.message.reply_text("Masukkan SC AOxxxx tanpa DGPS")
    return SC

async def sc(update:Update,context):

    sc=update.message.text.upper()

    if not sc.startswith("AO"):
        await update.message.reply_text("Format SC salah")
        return SC

    data=context.user_data

    sheet_input.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        data["labor"],
        "",
        data["sektor"],
        sc,
        "PSB",
        ""
    ])

    await update.message.reply_text(
        "✅ DATA TERSIMPAN",
        reply_markup=MAIN_MENU
    )

    return ConversationHandler.END

async def batal(update:Update,context):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Dibatalkan",
        reply_markup=MAIN_MENU
    )
    return ConversationHandler.END

async def lapor(update:Update,context):
    await update.message.reply_text("⏳ Membuat dashboard...")
    await kirim_dashboard(context.application)
    await update.message.reply_text(
        "✅ Dashboard terkirim",
        reply_markup=MAIN_MENU
    )

# =============================
# MAIN
# =============================
def main():

    loop=asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app=Application.builder().token(TOKEN).build()

    conv=ConversationHandler(
        entry_points=[CommandHandler("input",input_cmd)],
        states={
            LABOR:[MessageHandler(filters.TEXT & ~filters.COMMAND,labor)],
            SEKTOR:[MessageHandler(filters.TEXT & ~filters.COMMAND,sektor)],
            SC:[MessageHandler(filters.TEXT & ~filters.COMMAND,sc)],
        },
        fallbacks=[CommandHandler("batal",batal)]
    )

    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("lapor",lapor))
    app.add_handler(CommandHandler("batal",batal))
    app.add_handler(conv)

    async def start_scheduler(application):

        scheduler=AsyncIOScheduler()

        scheduler.add_job(
            lambda:asyncio.create_task(
                kirim_dashboard(application)
            ),
            "cron",
            hour="8,12,17",
            minute=0
        )

        scheduler.start()

    app.post_init=start_scheduler

    print("✅ BOT RUNNING...")
    app.run_polling()

if __name__=="__main__":
    main()