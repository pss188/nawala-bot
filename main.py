# skiddle_checker_proxy.py
import os
import sys
import asyncio
import requests
import schedule
import time
import random
from datetime import datetime
from telegram import Bot
from telegram.ext import Application

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

# Cambodia Proxy Pool
CAMBODIA_PROXIES = [
    "http://202.178.125.136:8080",
    "http://203.171.252.7:8080", 
    "http://175.100.34.177:8080",
    "http://45.201.208.192:8080",
    "http://203.95.196.73:8080",
    "http://103.9.190.130:8080",
    "http://203.95.197.153:8080",
    "http://175.100.35.103:8080",
    "http://36.37.147.34:8080",
    "http://110.235.250.77:8080",
    "http://103.73.164.190:32650",
    "http://36.37.251.137:8080",
    "http://110.74.215.170:8080",
    "http://203.189.153.19:8083",
    "http://203.95.196.40:8080",
    "http://203.95.198.162:8080",
    "http://36.37.180.40:8080",
    "http://203.95.198.180:8080",
    "http://5.28.35.226:9812",
    "http://119.15.86.30:8080",
    "http://50.114.33.244:8080",
    "http://203.95.196.6:8080",
    "http://103.118.44.218:8080",
    "http://116.212.149.218:8080",
    "http://50.114.33.183:8080",
    "http://203.95.198.192:8080",
    "http://175.100.103.170:55443",
    "http://103.118.44.205:8080",
    "http://203.176.134.41:8080",
    "socks5://103.12.161.222:1080"
]

# Working proxies cache
working_proxies = []
proxy_last_update = 0

def test_proxy(proxy_url):
    """Test if a proxy is working"""
    try:
        proxies = {
            'http': proxy_url,
            'https': proxy_url.replace('http://', 'https://') if proxy_url.startswith('http://') else proxy_url
        }
        
        # Test with a simple request
        response = requests.get(
            'http://httpbin.org/ip',
            proxies=proxies,
            timeout=10,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ Proxy works: {proxy_url} -> IP: {data.get('origin')}")
            return True
    except Exception as e:
        logger.debug(f"Proxy {proxy_url} failed: {e}")
    
    return False

def get_working_proxies():
    """Get list of working proxies with caching"""
    global working_proxies, proxy_last_update
    
    # Return cached if recent (1 hour)
    current_time = time.time()
    if working_proxies and (current_time - proxy_last_update) < 3600:
        return working_proxies
    
    logger.info("Testing proxy pool...")
    working_proxies = []
    
    # Test all proxies
    for proxy in CAMBODIA_PROXIES:
        if test_proxy(proxy):
            working_proxies.append(proxy)
        
        # Small delay between tests
        time.sleep(0.5)
    
    proxy_last_update = current_time
    logger.info(f"Found {len(working_proxies)} working proxies")
    
    # If no proxies work, use all as fallback
    if not working_proxies:
        logger.warning("No proxies working, using all as fallback")
        working_proxies = CAMBODIA_PROXIES.copy()
    
    return working_proxies

def check_domain_with_proxy(domain, proxy_url=None):
    """Check domain using a proxy"""
    proxies = None
    
    if proxy_url:
        proxies = {
            'http': proxy_url,
            'https': proxy_url.replace('http://', 'https://') if proxy_url.startswith('http://') else proxy_url
        }
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://check.skiddle.id/',
            'Origin': 'https://check.skiddle.id'
        }
        
        response = requests.get(
            f'https://check.skiddle.id/?domains={domain}',
            proxies=proxies,
            headers=headers,
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            return {
                'blocked': data.get(domain, {}).get('blocked', False),
                'data': data,
                'success': True,
                'status': 'success'
            }
        elif response.status_code in [403, 429]:
            return {
                'blocked': None,
                'error': f'Access denied: {response.status_code}',
                'success': False,
                'status': 'blocked'
            }
        else:
            return {
                'blocked': None,
                'error': f'HTTP {response.status_code}',
                'success': False,
                'status': 'error'
            }
            
    except requests.exceptions.ProxyError as e:
        return {
            'blocked': None,
            'error': f'Proxy error: {str(e)}',
            'success': False,
            'status': 'proxy_error'
        }
    except requests.exceptions.Timeout:
        return {
            'blocked': None,
            'error': 'Request timeout',
            'success': False,
            'status': 'timeout'
        }
    except Exception as e:
        return {
            'blocked': None,
            'error': str(e),
            'success': False,
            'status': 'exception'
        }

async def kirim_status():
    try:
        waktu = time.strftime("%d-%m-%Y %H:%M:%S")
        proxy_count = len(get_working_proxies())
        
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=f"🤖 *Bot Aktif*\nWaktu: {waktu}\nProxy aktif: {proxy_count}/{len(CAMBODIA_PROXIES)}",
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
    
    # Get working proxies
    proxies = get_working_proxies()
    
    if not proxies:
        logger.error("Tidak ada proxy yang bekerja!")
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text="❌ *Tidak ada proxy yang bekerja!*",
            parse_mode="Markdown"
        )
        return
    
    hasil = []
    total_domain = len(domains)
    berhasil_dicek = 0
    
    logger.info(f"Memulai pengecekan {total_domain} domain dengan {len(proxies)} proxy...")
    
    for domain in domains:
        max_retries = 3
        checked = False
        
        for attempt in range(max_retries):
            # Pilih proxy acak
            proxy = random.choice(proxies)
            
            logger.info(f"Attempt {attempt+1}: Cek {domain} dengan proxy {proxy}")
            
            result = check_domain_with_proxy(domain, proxy)
            
            if result['success']:
                berhasil_dicek += 1
                checked = True
                
                if result['blocked']:
                    hasil.append(f"🚫 *{domain}* nawala!")
                    logger.info(f"{domain}: TERBLOKIR (via proxy {proxy})")
                else:
                    logger.info(f"{domain}: AMAN (via proxy {proxy})")
                
                break  # Success, keluar dari retry loop
                
            elif result['status'] == 'proxy_error':
                # Proxy mungkin mati, coba proxy lain
                logger.warning(f"Proxy {proxy} error, mencoba proxy lain...")
                if proxy in proxies:
                    proxies.remove(proxy)
                if not proxies:
                    logger.error("Semua proxy error!")
                    break
                continue
                
            else:
                logger.warning(f"Attempt {attempt+1} gagal: {result['error']}")
                await asyncio.sleep(2)  # Tunggu sebelum retry
        
        if not checked:
            logger.error(f"Gagal cek {domain} setelah {max_retries} percobaan")
    
    # Kirim hasil
    if hasil:
        message = "🔍 *Hasil Pengecekan Domain:*\n\n" + "\n".join(hasil)
        message += f"\n\n📊 Statistik:"
        message += f"\n• Total domain: {total_domain}"
        message += f"\n• Berhasil dicek: {berhasil_dicek}"
        message += f"\n• Terblokir: {len(hasil)}"
        message += f"\n• Proxy aktif: {len(get_working_proxies())}"
        
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="Markdown"
        )
        logger.info(f"Laporan terkirim: {len(hasil)} domain terblokir")
    
    elif berhasil_dicek > 0:
        # Semua aman
        message = f"✅ Semua *{berhasil_dicek}* domain aman!"
        message += f"\n\n📊 Statistik:"
        message += f"\n• Total domain: {total_domain}"
        message += f"\n• Proxy aktif: {len(get_working_proxies())}"
        
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="Markdown"
        )
        logger.info(f"Semua {berhasil_dicek} domain aman")
    
    else:
        logger.warning("Tidak ada domain yang berhasil dicek")
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text="⚠️ *Gagal memeriksa semua domain!*\nProxy mungkin tidak bekerja.",
            parse_mode="Markdown"
        )

async def tugas_utama():
    # Test proxies saat start
    proxies = get_working_proxies()
    
    if proxies:
        logger.info(f"✅ {len(proxies)} proxy aktif!")
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=f"✅ *Proxy aktif!*\n{len(proxies)} proxy Kamboja siap digunakan.",
            parse_mode="Markdown"
        )
    else:
        logger.error("❌ Tidak ada proxy yang bekerja!")
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text="❌ *Tidak ada proxy yang bekerja!*\nBot tidak dapat memantau domain.",
            parse_mode="Markdown"
        )
    
    # Jadwalkan tugas
    schedule.every(5).minutes.do(lambda: asyncio.create_task(cek_domain()))
    schedule.every(1).hours.do(lambda: asyncio.create_task(kirim_status()))
    schedule.every(2).hours.do(lambda: get_working_proxies())  # Update proxy list
    
    # Jalankan segera
    await cek_domain()
    await kirim_status()

    # Loop utama
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

if __name__ == "__main__":
    # Install package jika belum: pip install requests pysocks
    try:
        asyncio.run(tugas_utama())
    except KeyboardInterrupt:
        logger.info("Bot dihentikan oleh pengguna")
    except Exception as e:
        logger.error(f"Bot error: {e}")
