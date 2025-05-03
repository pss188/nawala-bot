import os
import sys
import asyncio
import aiohttp
import schedule
import time
from telegram import Bot
from telegram.ext import Application
from typing import List
from datetime import datetime

# Atur logging
import logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ambil variabel environment
TOKEN = os.getenv("TOKEN")
CHAT_ID_RAW = os.getenv("CHAT_ID")

if not TOKEN or not CHAT_ID_RAW:
    logger.error("TOKEN atau CHAT_ID tidak ditemukan di Railway Variables")
    sys.exit(1)

try:
    CHAT_ID = int(CHAT_ID_RAW)
except ValueError:
    logger.error("CHAT_ID harus berupa angka")
    sys.exit(1)

# Inisialisasi bot
application = Application.builder().token(TOKEN).build()

async def kirim_status():
    """Kirim laporan status bot setiap jam"""
    try:
        waktu_sekarang = time.strftime("%d-%m-%Y %H:%M:%S")
        pesan = f"✅ *Status Bot Aktif* (Pukul {waktu_sekarang})\nBot berjalan normal dan memantau domain!"
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=pesan,
            parse_mode="Markdown"
        )
        logger.info("Mengirim laporan status per jam")
    except Exception as e:
        logger.error(f"Gagal mengirim status: {e}")

async def baca_domain() -> List[str]:
    """Baca daftar domain dari file"""
    try:
        with open("domain.txt", "r") as f:
            domains = [line.strip() for line in f if line.strip()]
            logger.info(f"Berhasil membaca {len(domains)} domain dari domain.txt")
            return domains
    except Exception as e:
        logger.error(f"Gagal membaca domain.txt: {e}")
        return []

async def cek_blokir(session: aiohttp.ClientSession, domain: str) -> str:
    """Cek apakah domain diblokir"""
    url = f'https://check.skiddle.id/?domains={domain}'
    try:
        async with session.get(url, timeout=5) as response:
            data = await response.json()
            logger.debug(f"Hasil API untuk {domain}: {data}")
            
            if data.get(domain, {}).get("blocked", False):
                return f"🚫 *{domain}* terdeteksi diblokir nawala."
    except Exception as e:
        logger.warning(f"Gagal memeriksa {domain}: {e}")
        return f"⚠️ Gagal memeriksa {domain}: {e}"

async def periksa_blokir():
    """Periksa semua domain"""
    domains = await baca_domain()
    if not domains:
        logger.warning("Tidak ada domain yang perlu diperiksa")
        return

    daftar_pesan = []
    async with aiohttp.ClientSession() as session:
        tasks = [cek_blokir(session, domain) for domain in domains]
        daftar_pesan = await asyncio.gather(*tasks)

    if any(daftar_pesan):
        try:
            pesan_gabungan = "\n".join(pesan for pesan in daftar_pesan if pesan)
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=pesan_gabungan,
                parse_mode="Markdown"
            )
            logger.info("Pesan terkirim ke grup Telegram")
        except Exception as e:
            logger.error(f"Gagal mengirim pesan Telegram: {e}")
    else:
        logger.info("Tidak ada domain yang diblokir")

    logger.info(f"Pemeriksaan selesai pukul {time.strftime('%d-%m-%Y %H:%M:%S')}")

async def jalankan_bot():
    """Fungsi utama untuk menjalankan bot"""
    # Pemeriksaan awal
    await periksa_blokir()
    await kirim_status()  # Kirim status pertama kali
    
    # Jadwal otomatis
    schedule.every(1).minutes.do(lambda: asyncio.create_task(periksa_blokir()))
    schedule.every(1).hours.do(lambda: asyncio.create_task(kirim_status()))
    
    # Loop utama
    while True:
        schedule.run_pending()
        await asyncio.sleep(60)

if __name__ == "__main__":
    try:
        asyncio.run(jalankan_bot())
    except KeyboardInterrupt:
        logger.info("Bot dihentikan oleh pengguna")
    except Exception as e:
        logger.error(f"Error fatal: {e}")
