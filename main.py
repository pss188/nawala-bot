import os
import sys
import asyncio
import schedule
import time
from telegram import Bot
from telegram.ext import Application
import aiohttp
from aiohttp_socks import ProxyConnector

# Setup logging
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

# Proxy configuration
PROXY_HOST = "95.135.92.164"
PROXY_PORT_HTTP = 59100  # Port untuk HTTP(s)
PROXY_PORT_SOCKS5 = 59101  # Port untuk SOCKS5
PROXY_USERNAME = "pulsaslot1888"
PROXY_PASSWORD = "b3Kft6IMwG"

# URL Proxy untuk berbagai penggunaan
PROXY_URL_HTTP = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT_HTTP}"
PROXY_URL_SOCKS5 = f"socks5://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT_SOCKS5}"

# Bot setup dengan proxy SOCKS5
application = Application.builder()\
    .token(TOKEN)\
    .proxy_url(PROXY_URL_SOCKS5)\
    .build()

async def kirim_status():
    try:
        waktu = time.strftime("%d-%m-%Y %H:%M:%S")
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=f"🤖 *Bot Aktif* berjalan normal!\n⏰ {waktu}\n🌐 Menggunakan proxy: {PROXY_HOST}",
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

async def cek_domain_dengan_proxy(domain):
    """Cek domain menggunakan proxy HTTP"""
    try:
        # Buat connector dengan proxy HTTP untuk pengecekan domain
        connector = aiohttp.TCPConnector()
        
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=15)
        ) as session:
            # Gunakan proxy HTTP untuk request
            proxy = f"http://{PROXY_HOST}:{PROXY_PORT_HTTP}"
            proxy_auth = aiohttp.BasicAuth(PROXY_USERNAME, PROXY_PASSWORD)
            
            async with session.get(
                f'https://check.skiddle.id/?domains={domain}',
                proxy=proxy,
                proxy_auth=proxy_auth
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    blocked = data.get(domain, {}).get("blocked", False)
                    logger.info(f"Domain {domain}: {'Terblokir' if blocked else 'Aman'}")
                    return domain, blocked
                else:
                    logger.error(f"HTTP Error {response.status} untuk {domain}")
                    return domain, False
    except asyncio.TimeoutError:
        logger.error(f"Timeout untuk domain {domain}")
        return domain, False
    except Exception as e:
        logger.error(f"Error cek {domain}: {e}")
        return domain, False

async def cek_domain():
    domains = baca_domain()
    if not domains:
        logger.info("Tidak ada domain untuk dicek")
        return

    hasil = []
    
    # Cek domain satu per satu untuk menghindari rate limiting
    for domain in domains:
        logger.info(f"Memeriksa domain: {domain}")
        domain_result, blocked = await cek_domain_dengan_proxy(domain)
        
        if blocked:
            hasil.append(f"🚫 *{domain}* terblokir!")
            logger.warning(f"Domain terblokir ditemukan: {domain}")
    
    if hasil:
        try:
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text="🔔 *LAPORAN PEMERIKSAAN DOMAIN*\n\n" + "\n".join(hasil) + 
                     f"\n\n📊 Total: {len(hasil)} dari {len(domains)} domain terblokir",
                parse_mode="Markdown"
            )
            logger.info(f"Status domain terkirim: {len(hasil)} domain terblokir")
        except Exception as e:
            logger.error(f"Gagal mengirim laporan: {e}")
    else:
        logger.info("Semua domain aman, tidak ada yang terblokir")

def cek_domain_sync():
    """Wrapper untuk menjalankan cek_domain dari schedule"""
    asyncio.create_task(cek_domain())

def kirim_status_sync():
    """Wrapper untuk menjalankan kirim_status dari schedule"""
    asyncio.create_task(kirim_status())

async def tugas_utama():
    logger.info("🚀 Memulai bot monitoring domain...")
    logger.info(f"📍 Menggunakan proxy: {PROXY_HOST}")
    logger.info(f"📂 Membaca domain dari: domain.txt")
    
    # Jadwalkan tugas
    schedule.every(1).minutes.do(cek_domain_sync)
    schedule.every(1).hours.do(kirim_status_sync)
    
    # Jalankan segera setelah startup
    logger.info("🔄 Menjalankan pemeriksaan awal...")
    await cek_domain()
    await kirim_status()

    logger.info("✅ Bot berhasil dijalankan dan berjalan di background")
    
    # Loop utama
    while True:
        try:
            schedule.run_pending()
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 Bot dihentikan oleh pengguna")
            break
        except Exception as e:
            logger.error(f"Error dalam loop utama: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    # Install package yang diperlukan jika belum ada
    required_packages = ['aiohttp', 'aiohttp-socks', 'schedule', 'python-telegram-bot']
    
    for package in required_packages:
        try:
            if package == 'aiohttp-socks':
                import aiohttp_socks
            elif package == 'python-telegram-bot':
                from telegram import __version__
            else:
                __import__(package)
        except ImportError:
            logger.info(f"Menginstal {package}...")
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    
    try:
        asyncio.run(tugas_utama())
    except KeyboardInterrupt:
        logger.info("Bot dihentikan")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        # Coba kirim error ke Telegram jika koneksi masih ada
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                application.bot.send_message(
                    chat_id=CHAT_ID,
                    text=f"❌ *Bot Error*\n\nError: {str(e)[:100]}...",
                    parse_mode="Markdown"
                )
            )
        except:
            pass
