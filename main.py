import os
import sys
import asyncio
import requests
import schedule
import time
import random
import logging
from datetime import datetime
from telegram import Bot
from telegram.ext import Application

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

# Bot setup
application = Application.builder().token(TOKEN).build()

# PROXY PREMIUM SAJA
PROXY_LIST = [
    # Premium Proxy HTTP dengan auth
    {
        'http': 'http://pulsaslot1888:b3Kft6IMwG@95.135.92.164:59100',
        'https': 'http://pulsaslot1888:b3Kft6IMwG@95.135.92.164:59100',
        'name': 'premium_http',
        'type': 'premium'
    },
    # Premium Proxy SOCKS5 dengan auth
    {
        'socks5': 'socks5://pulsaslot1888:b3Kft6IMwG@95.135.92.164:59101',
        'name': 'premium_socks5',
        'type': 'premium'
    }
]

# Cache untuk proxy yang bekerja
working_proxies = []
proxy_last_update = 0

def create_request_session(proxy_info):
    """Create requests session dengan proxy configuration"""
    session = requests.Session()
    
    # Headers tetap untuk semua request
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    })
    
    # Setup proxy
    if 'http' in proxy_info or 'https' in proxy_info:
        # HTTP/HTTPS proxy
        proxy_config = {}
        if 'http' in proxy_info:
            proxy_config['http'] = proxy_info['http']
        if 'https' in proxy_info:
            proxy_config['https'] = proxy_info['https']
        
        session.proxies.update(proxy_config)
        session.trust_env = False  # Ignore system proxy
    
    return session

def test_proxy(proxy_info):
    """Test jika proxy bekerja"""
    try:
        session = create_request_session(proxy_info)
        
        # Test dengan simple request
        response = session.get(
            'http://httpbin.org/ip',
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ Proxy {proxy_info['name']} bekerja. IP: {data.get('origin', 'Unknown')}")
            return True
            
    except Exception as e:
        logger.warning(f"❌ Proxy {proxy_info['name']} gagal: {str(e)[:100]}")
    
    return False

def get_working_proxies():
    """Dapatkan list proxy yang bekerja"""
    global working_proxies, proxy_last_update
    
    # Cache selama 30 menit
    current_time = time.time()
    if working_proxies and (current_time - proxy_last_update) < 1800:
        return working_proxies
    
    logger.info("🔍 Testing proxy premium...")
    working_proxies = []
    
    for proxy in PROXY_LIST:
        if test_proxy(proxy):
            working_proxies.append(proxy)
    
    proxy_last_update = current_time
    
    if working_proxies:
        logger.info(f"✅ Found {len(working_proxies)} working proxies")
    else:
        logger.error("❌ Tidak ada proxy yang bekerja!")
    
    return working_proxies

def check_domain_skiddle(domain, proxy_info):
    """Cek domain di skiddle.id menggunakan proxy"""
    try:
        session = create_request_session(proxy_info)
        
        # Tambahkan headers khusus untuk skiddle.id
        skiddle_headers = {
            'Referer': 'https://check.skiddle.id/',
            'Origin': 'https://check.skiddle.id',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin'
        }
        session.headers.update(skiddle_headers)
        
        response = session.get(
            f'https://check.skiddle.id/?domains={domain}',
            timeout=20
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
                return {
                    'success': True,
                    'blocked': data.get(domain, {}).get('blocked', False),
                    'data': data.get(domain, {}),
                    'raw_data': data,
                    'status_code': response.status_code,
                    'proxy_used': proxy_info['name']
                }
            except ValueError:
                # Response bukan JSON
                return {
                    'success': False,
                    'error': 'Invalid JSON response',
                    'status_code': response.status_code,
                    'proxy_used': proxy_info['name']
                }
        else:
            return {
                'success': False,
                'error': f'HTTP {response.status_code}',
                'status_code': response.status_code,
                'proxy_used': proxy_info['name']
            }
            
    except requests.exceptions.Timeout:
        return {
            'success': False,
            'error': 'Request timeout',
            'proxy_used': proxy_info['name']
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'proxy_used': proxy_info['name']
        }

async def kirim_status():
    """Kirim status bot ke Telegram"""
    try:
        waktu = time.strftime("%d-%m-%Y %H:%M:%S")
        proxies = get_working_proxies()
        
        status_text = f"🤖 *Bot Aktif*\n"
        status_text += f"Waktu: {waktu}\n"
        status_text += f"Proxy aktif: {len(proxies)}/{len(PROXY_LIST)}\n"
        
        for proxy in proxies:
            status_text += f"• {proxy['name']}\n"
        
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=status_text,
            parse_mode="Markdown"
        )
        logger.info("✅ Status bot terkirim")
        
    except Exception as e:
        logger.error(f"❌ Gagal kirim status: {e}")

def baca_domain():
    """Baca domain dari file"""
    try:
        with open("domain.txt", "r") as f:
            domains = [line.strip() for line in f if line.strip()]
            logger.info(f"📖 Membaca {len(domains)} domain dari file")
            return domains
    except Exception as e:
        logger.error(f"❌ Error baca domain: {e}")
        return []

async def cek_domain():
    """Cek semua domain"""
    domains = baca_domain()
    if not domains:
        logger.info("ℹ️ Tidak ada domain untuk dicek")
        return
    
    proxies = get_working_proxies()
    if not proxies:
        logger.error("❌ Tidak ada proxy yang bekerja!")
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text="❌ *Tidak ada proxy yang bekerja!*",
            parse_mode="Markdown"
        )
        return
    
    hasil_blokir = []
    total_domain = len(domains)
    berhasil_dicek = 0
    
    logger.info(f"🔍 Memulai pengecekan {total_domain} domain...")
    
    for domain in domains:
        logger.info(f"🔍 Checking: {domain}")
        max_retries = 2
        checked = False
        
        for attempt in range(max_retries):
            # Pilih proxy secara bergantian
            proxy = proxies[attempt % len(proxies)]
            
            logger.info(f"   Attempt {attempt+1} dengan {proxy['name']}")
            result = check_domain_skiddle(domain, proxy)
            
            if result['success']:
                berhasil_dicek += 1
                checked = True
                
                if result['blocked']:
                    hasil_blokir.append(f"🚫 *{domain}* nawala!")
                    logger.info(f"   ✅ {domain}: TERBLOKIR (via {proxy['name']})")
                else:
                    logger.info(f"   ✅ {domain}: AMAN (via {proxy['name']})")
                
                break  # Berhasil, keluar dari retry
            else:
                logger.warning(f"   ❌ Attempt {attempt+1} gagal: {result['error']}")
                await asyncio.sleep(1)  # Delay sebelum retry
        
        if not checked:
            logger.error(f"   ❌ Gagal cek {domain} setelah {max_retries} percobaan")
    
    # Kirim laporan ke Telegram
    if hasil_blokir:
        message = "🚨 *DOMAIN TERBLOKIR* 🚨\n\n"
        message += "\n".join(hasil_blokir)
        message += f"\n\n📊 *Statistik:*\n"
        message += f"• Total domain: {total_domain}\n"
        message += f"• Berhasil dicek: {berhasil_dicek}\n"
        message += f"• Terblokir: {len(hasil_blokir)}"
    elif berhasil_dicek > 0:
        message = "✅ *SEMUA DOMAIN AMAN* ✅\n\n"
        message += f"📊 *Statistik:*\n"
        message += f"• Total domain: {total_domain}\n"
        message += f"• Berhasil dicek: {berhasil_dicek}\n"
        message += f"• Terblokir: 0"
    else:
        message = "⚠️ *GAGAL MENGECEK DOMAIN* ⚠️\n\n"
        message += f"Tidak ada domain yang berhasil dicek.\n"
        message += f"Total domain: {total_domain}"
    
    try:
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="Markdown"
        )
        logger.info(f"📤 Laporan terkirim: {len(hasil_blokir)} domain terblokir")
    except Exception as e:
        logger.error(f"❌ Gagal kirim laporan: {e}")

async def tugas_utama():
    """Main bot task"""
    # Test proxy saat start
    proxies = get_working_proxies()
    
    if proxies:
        logger.info(f"✅ Bot siap dengan {len(proxies)} proxy premium!")
        
        startup_msg = "🚀 *Bot Skiddle Checker Aktif!*\n\n"
        startup_msg += f"✅ {len(proxies)} proxy premium siap digunakan:\n"
        for proxy in proxies:
            startup_msg += f"• {proxy['name']}\n"
        startup_msg += f"\nBot akan mengecek domain setiap 5 menit."
        
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=startup_msg,
            parse_mode="Markdown"
        )
    else:
        logger.error("❌ Tidak ada proxy yang bekerja!")
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text="❌ *Bot Gagal Start!*\nTidak ada proxy premium yang bekerja.",
            parse_mode="Markdown"
        )
        return
    
    # Jadwalkan tugas
    schedule.every(5).minutes.do(lambda: asyncio.create_task(cek_domain()))
    schedule.every(1).hours.do(lambda: asyncio.create_task(kirim_status()))
    schedule.every(30).minutes.do(get_working_proxies)  # Update proxy list
    
    # Jalankan segera
    await cek_domain()
    await kirim_status()
    
    # Main loop
    logger.info("🔄 Bot berjalan...")
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

if __name__ == "__main__":
    # Check for PySocks jika butuh SOCKS5
    try:
        import socks
        logger.info("✅ PySocks terinstall, SOCKS5 proxy siap digunakan")
    except ImportError:
        logger.warning("⚠️ PySocks tidak terinstall. SOCKS5 proxy tidak akan bekerja.")
        logger.info("   Install dengan: pip install pysocks")
    
    try:
        asyncio.run(tugas_utama())
    except KeyboardInterrupt:
        logger.info("👋 Bot dihentikan oleh pengguna")
    except Exception as e:
        logger.error(f"💥 Bot error: {e}")
        sys.exit(1)
