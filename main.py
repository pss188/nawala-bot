import os
import sys
import asyncio
import requests
import schedule
import time
import random
from telegram import Bot
from telegram.ext import Application
from urllib.parse import urlparse
import threading

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

# Bot setup
application = Application.builder().token(TOKEN).build()

# Pool proxy gratis (sumber publik)
FREE_PROXIES = [
    # Indonesia/Southeast Asia proxies (sering berubah, perlu update)
    "http://103.153.140.142:8080",
    "http://103.170.186.226:8080",
    "http://103.155.54.26:83",
    "http://103.147.77.66:3125",
    "http://202.158.49.140:56687",
    
    # Global proxies sebagai cadangan
    "http://185.199.229.156:7492",
    "http://185.199.228.220:7300",
    "http://185.199.231.45:8382",
    
    # SOCKS proxies
    "socks5://64.124.191.146:1080",
    "socks5://67.213.212.58:4145",
]

# Cache untuk proxy yang berhasil
working_proxies = []
proxy_lock = threading.Lock()

def test_proxy(proxy_url):
    """Test apakah proxy bekerja"""
    try:
        proxies = {
            'http': proxy_url,
            'https': proxy_url,
        }
        # Test dengan website yang tidak diblokir
        response = requests.get(
            'http://httpbin.org/ip',
            proxies=proxies,
            timeout=5
        )
        if response.status_code == 200:
            logger.info(f"Proxy berhasil: {proxy_url}")
            return True
    except:
        pass
    return False

def update_proxy_list():
    """Update proxy list dari sumber online"""
    global FREE_PROXIES
    try:
        # Sumber free proxy (pilih salah satu)
        sources = [
            "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=ID,TH,VN,SG,MY&ssl=yes&anonymity=elite",
            "https://www.proxy-list.download/api/v1/get?type=http&country=ID",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        ]
        
        for source in sources:
            try:
                response = requests.get(source, timeout=10)
                if response.status_code == 200:
                    new_proxies = response.text.strip().split('\n')
                    FREE_PROXIES.extend([f"http://{p.strip()}" for p in new_proxies if p.strip()])
                    logger.info(f"Ditambahkan {len(new_proxies)} proxy dari {source}")
                    break
            except:
                continue
    except Exception as e:
        logger.warning(f"Gagal update proxy list: {e}")

def get_working_proxy():
    """Dapatkan proxy yang berfungsi"""
    global working_proxies
    
    with proxy_lock:
        # Jika ada proxy yang sudah terbukti bekerja, gunakan
        if working_proxies:
            proxy = random.choice(working_proxies)
            return proxy
        
        # Test semua proxy
        logger.info("Mencari proxy yang berfungsi...")
        for proxy in FREE_PROXIES:
            if test_proxy(proxy):
                working_proxies.append(proxy)
                return proxy
        
        # Jika tidak ada yang berfungsi, update list
        update_proxy_list()
        for proxy in FREE_PROXIES[-20:]:  # Coba proxy terbaru
            if test_proxy(proxy):
                working_proxies.append(proxy)
                return proxy
    
    return None  # Tidak ada proxy yang berfungsi

async def kirim_status():
    try:
        waktu = time.strftime("%d-%m-%Y %H:%M:%S")
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=f"🤖 *Bot Aktif* berjalan normal!\nWaktu: {waktu}",
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
        logger.info("Tidak ada domain untuk dicek")
        return

    hasil = []
    max_retries = 3
    
    for domain in domains:
        success = False
        for attempt in range(max_retries):
            try:
                proxy = get_working_proxy()
                
                if proxy:
                    proxies = {'http': proxy, 'https': proxy}
                    logger.info(f"Mencoba dengan proxy: {proxy}")
                else:
                    proxies = None
                    logger.info("Mencoba tanpa proxy")
                
                # Headers untuk menghindari blokir
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'application/json',
                    'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
                }
                
                response = requests.get(
                    f'https://check.skiddle.id/?domains={domain}',
                    proxies=proxies,
                    headers=headers,
                    timeout=15
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if domain in data and data.get(domain, {}).get("blocked", False):
                        hasil.append(f"🚫 *{domain}* nawala!")
                    success = True
                    break
                else:
                    logger.warning(f"Attempt {attempt+1}: Status {response.status_code}")
                    
            except requests.exceptions.ProxyError:
                logger.warning(f"Proxy error, mencoba lagi...")
                with proxy_lock:
                    if proxy in working_proxies:
                        working_proxies.remove(proxy)
                continue
            except Exception as e:
                logger.error(f"Error cek {domain}: {e}")
                await asyncio.sleep(2)  # Tunggu sebelum retry
        
        if not success:
            logger.error(f"Gagal cek {domain} setelah {max_retries} percobaan")

    if hasil:
        try:
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text="\n".join(hasil),
                parse_mode="Markdown"
            )
            logger.info(f"Status domain terkirim: {len(hasil)} domain terblokir")
        except Exception as e:
            logger.error(f"Gagal kirim hasil: {e}")
    else:
        logger.info("Tidak ada domain yang terblokir.")

async def tugas_utama():
    # Update proxy list saat start
    update_proxy_list()
    
    # Jadwalkan update proxy setiap 6 jam
    schedule.every(6).hours.do(update_proxy_list)
    
    # Jadwalkan tugas utama
    schedule.every(1).minutes.do(lambda: asyncio.create_task(cek_domain()))
    schedule.every(1).hours.do(lambda: asyncio.create_task(kirim_status()))
    
    # Jalankan segera
    await cek_domain()
    await kirim_status()

    # Loop utama
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(tugas_utama())
    except KeyboardInterrupt:
        logger.info("Bot dihentikan oleh pengguna")
    except Exception as e:
        logger.error(f"Bot error: {e}")
