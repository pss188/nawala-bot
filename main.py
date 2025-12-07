import os
import sys
import time
import schedule
import requests
from telegram import Bot
from telegram.ext import Application
import logging

# Setup logging
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

# Proxy configuration
PROXY_HOST = "95.135.92.164"
PROXY_PORT_HTTP = 59100
PROXY_PORT_SOCKS5 = 59101
PROXY_USERNAME = "pulsaslot1888"
PROXY_PASSWORD = "b3Kft6IMwG"

# Proxy URLs
PROXY_HTTP = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT_HTTP}"
PROXY_SOCKS5 = f"socks5://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT_SOCKS5}"

# Konfigurasi proxy untuk requests
proxies = {
    'http': PROXY_HTTP,
    'https': PROXY_HTTP,
}

# Bot setup dengan proxy SOCKS5
try:
    # Coba buat application dengan proxy
    REQUEST_KWARGS = {
        'proxy_url': PROXY_SOCKS5,
    }
    application = Application.builder()\
        .token(TOKEN)\
        .get_updates_proxy_url(PROXY_SOCKS5)\
        .build()
    logger.info("Bot berhasil diinisialisasi dengan proxy SOCKS5")
except Exception as e:
    logger.warning(f"Gagal setup proxy SOCKS5: {e}. Menggunakan tanpa proxy...")
    application = Application.builder().token(TOKEN).build()

async def kirim_status():
    try:
        waktu = time.strftime("%d-%m-%Y %H:%M:%S")
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=f"🤖 *Bot Aktif* berjalan normal!\n⏰ {waktu}",
            parse_mode="Markdown"
        )
        logger.info("Status bot terkirim")
    except Exception as e:
        logger.error(f"Gagal kirim status: {e}")

def baca_domain():
    try:
        with open("domain.txt", "r") as f:
            domains = []
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    domains.append(line)
            return domains
    except Exception as e:
        logger.error(f"Error baca domain: {e}")
        return []

def cek_domain_sync():
    """Fungsi synchronous untuk cek domain"""
    try:
        domains = baca_domain()
        if not domains:
            logger.info("Tidak ada domain untuk dicek")
            return
        
        hasil = []
        
        for domain in domains:
            try:
                logger.info(f"Memeriksa domain: {domain}")
                
                # Gunakan proxy untuk request
                response = requests.get(
                    f'https://check.skiddle.id/?domains={domain}',
                    proxies=proxies,
                    timeout=15
                )
                
                if response.status_code == 200:
                    data = response.json()
                    blocked = data.get(domain, {}).get("blocked", False)
                    
                    if blocked:
                        hasil.append(f"🚫 *{domain}* terblokir!")
                        logger.warning(f"Domain terblokir: {domain}")
                    else:
                        logger.info(f"Domain aman: {domain}")
                else:
                    logger.error(f"HTTP Error {response.status_code} untuk {domain}")
                    
            except requests.exceptions.Timeout:
                logger.error(f"Timeout untuk domain {domain}")
            except requests.exceptions.ProxyError as e:
                logger.error(f"Proxy error untuk {domain}: {e}")
            except Exception as e:
                logger.error(f"Error cek {domain}: {e}")
        
        if hasil:
            # Kirim hasil via Telegram (async)
            asyncio.create_task(kirim_hasil_domain(hasil, len(domains)))
        else:
            logger.info("Semua domain aman")
            
    except Exception as e:
        logger.error(f"Error dalam cek_domain_sync: {e}")

async def kirim_hasil_domain(hasil_list, total_domain):
    """Kirim hasil pemeriksaan domain"""
    try:
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=f"🔔 *LAPORAN DOMAIN*\n\n" + 
                 "\n".join(hasil_list) + 
                 f"\n\n📊 Total: {len(hasil_list)} dari {total_domain} domain terblokir",
            parse_mode="Markdown"
        )
        logger.info(f"Laporan terkirim: {len(hasil_list)} domain terblokir")
    except Exception as e:
        logger.error(f"Gagal kirim laporan: {e}")

async def tugas_utama():
    logger.info("🚀 Memulai bot monitoring domain...")
    logger.info(f"📍 Proxy: {PROXY_HOST}:{PROXY_PORT_HTTP} (HTTP)")
    
    # Jadwalkan tugas
    schedule.every(1).minutes.do(cek_domain_sync)
    schedule.every(1).hours.do(lambda: asyncio.create_task(kirim_status()))
    
    # Jalankan segera
    await kirim_status()
    cek_domain_sync()
    
    logger.info("✅ Bot berjalan. Tekan Ctrl+C untuk berhenti.")
    
    # Loop utama
    while True:
        try:
            schedule.run_pending()
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 Bot dihentikan")
            break
        except Exception as e:
            logger.error(f"Error loop: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    # Cek dan install dependencies jika diperlukan
    required_packages = ['requests', 'schedule', 'python-telegram-bot']
    
    for package in required_packages:
        try:
            if package == 'python-telegram-bot':
                from telegram import __version__
                logger.info(f"python-telegram-bot v{__version__} terinstal")
            else:
                __import__(package)
                logger.info(f"{package} terinstal")
        except ImportError:
            logger.warning(f"{package} tidak ditemukan. Menginstal...")
            try:
                import subprocess
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                logger.info(f"{package} berhasil diinstal")
            except Exception as e:
                logger.error(f"Gagal install {package}: {e}")
    
    try:
        import asyncio
        asyncio.run(tugas_utama())
    except KeyboardInterrupt:
        logger.info("Bot berhenti")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
