import os
import sys
import asyncio
import requests
import aioschedule as schedule
import time
from telegram import Bot
from telegram.ext import Application

# Logging
import logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Config
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not TOKEN or not CHAT_ID:
    logger.error("Token atau Chat ID tidak ditemukan!")
    sys.exit(1)

# Setup bot
application = Application.builder().token(TOKEN).build()

async def kirim_status():
    try:
        waktu = time.strftime("%d-%m-%Y %H:%M:%S")
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=f"🤖 *Status Bot On* ({waktu})\nSistem berjalan normal!",
            parse_mode="Markdown"
        )
        logger.info("Status bot terkirim")
    except Exception as e:
        logger.error(f"Gagal kirim status: {e}")

def baca_domain():
    try:
        with open("domain.txt", "r") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        logger.error(f"Error baca domain: {e}")
        return []

async def cek_domain():
    domains = baca_domain()
    if not domains:
        return

    hasil = []
    for domain in domains:
        try:
            response = requests.get(f'https://check.skiddle.id/?domains={domain}', timeout=10)
            if response.json().get(domain, {}).get("blocked", False):
                hasil.append(f"🚫 *{domain}* terkena nawala!")
        except Exception as e:
            logger.error(f"Error cek {domain}: {e}")

    if hasil:
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text="\n".join(hasil),
            parse_mode="Markdown"
        )

async def scheduler():
    schedule.every(1).minutes.do(cek_domain)
    schedule.every(1).hours.do(kirim_status)

    await cek_domain()
    await kirim_status()

    while True:
        await schedule.run_pending()
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(scheduler())
    except Exception as e:
        logger.error(f"Bot error: {e}")
