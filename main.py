import os
import sys
import asyncio
import requests
import schedule
import time
from telegram import Bot
from telegram.constants import ParseMode
import logging

# Logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Env Config
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not TOKEN or not CHAT_ID:
    logger.error("Token atau Chat ID tidak ditemukan!")
    sys.exit(1)

bot = Bot(token=TOKEN)

def baca_domain():
    try:
        with open("domain.txt", "r") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        logger.error(f"Error baca domain: {e}")
        return []

async def kirim_status():
    try:
        waktu = time.strftime("%d-%m-%Y %H:%M:%S")
        await bot.send_message(
            chat_id=CHAT_ID,
            text=f"🤖 *Bot Aktif* ({waktu})\nSistem berjalan normal!",
            parse_mode=ParseMode.MARKDOWN
        )
        logger.info("Status bot terkirim")
    except Exception as e:
        logger.error(f"Gagal kirim status: {e}")

async def cek_domain():
    domains = baca_domain()
    if not domains:
        return

    hasil = []
    for domain in domains:
        try:
            response = requests.get(f'https://check.skiddle.id/?domains={domain}', timeout=10)
            if response.json().get(domain, {}).get("blocked", False):
                hasil.append(f"🚫 *{domain}* terblokir!")
        except Exception as e:
            logger.error(f"Error cek {domain}: {e}")

    if hasil:
        try:
            await bot.send_message(
                chat_id=CHAT_ID,
                text="\n".join(hasil),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Gagal kirim pesan domain: {e}")

# Bungkus coroutine jadi task untuk schedule
def run_async_task(coro):
    asyncio.create_task(coro)

async def tugas_utama():
    # Jalankan awal
    await cek_domain()
    await kirim_status()

    # Jadwal
    schedule.every(1).minutes.do(run_async_task, cek_domain())
    schedule.every(1).hours.do(run_async_task, kirim_status())

    # Loop utama
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(tugas_utama())
    except Exception as e:
        logger.error(f"Bot error: {e}")
