import os
import sys
import time
import asyncio
import logging
import schedule
import json
from telegram.ext import Application
from datetime import datetime
import requests
import urllib3
import socks
import socket

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Config
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Proxy configuration
PROXY_HOST = "114.4.168.140"
PROXY_PORT_HTTP = 80

if not TOKEN or not CHAT_ID:
    logger.error("TOKEN atau CHAT_ID tidak ditemukan!")
    sys.exit(1)

# Setup SOCKS5 proxy
USE_SOCKS5 = True
try:
    if USE_SOCKS5:
        socks.set_default_proxy(
            socks.SOCKS5,
            PROXY_HOST,
            PROXY_PORT_SOCKS5,
            username=PROXY_USERNAME,
            password=PROXY_PASSWORD
        )
        socket.socket = socks.socksocket
        logger.info(f"✅ SOCKS5 proxy di-set: {PROXY_HOST}:{PROXY_PORT_SOCKS5}")
except Exception as e:
    logger.error(f"❌ Gagal setup SOCKS5: {e}")
    USE_SOCKS5 = False

# Setup proxies untuk requests
proxies = {
    'http': f'socks5://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT_SOCKS5}',
    'https': f'socks5://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT_SOCKS5}',
}

# HTTP proxy sebagai fallback
http_proxies = {
    'http': f'http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT_HTTP}',
    'https': f'http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT_HTTP}',
}

# Bot setup
try:
    application = Application.builder().token(TOKEN).build()
    logger.info("✅ Bot Telegram berhasil diinisialisasi")
except Exception as e:
    logger.error(f"❌ Gagal setup bot: {e}")
    sys.exit(1)

class TrustPositifAPIChecker:
    def __init__(self):
        self.session = requests.Session()
        
        # Gunakan SOCKS5 proxy
        if USE_SOCKS5:
            self.session.proxies.update(proxies)
            logger.info("🔑 Menggunakan SOCKS5 proxy")
        else:
            # Fallback ke HTTP proxy
            self.session.proxies.update(http_proxies)
            logger.info("🔑 Menggunakan HTTP proxy (fallback)")
        
        # API Endpoints (multiple fallback)
        self.api_endpoints = [
            "https://trustpositif.komdigi.go.id/api/check",
            "https://trustpositif.komdigi.go.id/api/check",
            "https://api.trustpositif.komdigi.go.id/check",
        ]
        
        # Headers untuk API
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
        }
    
    def check_single_domain(self, domain):
        """Cek 1 domain via TrustPositif API dengan retry"""
        try:
            logger.info(f"🔍 Checking: {domain}")
            
            # Coba ke semua endpoints dengan retry
            for endpoint in self.api_endpoints:
                for attempt in range(3):  # 3 retry
                    try:
                        logger.debug(f"📡 Mencoba: {endpoint} (attempt {attempt+1})")
                        
                        response = self.session.get(
                            endpoint,
                            params={'domain': domain},
                            headers=self.headers,
                            timeout=30,  # Timeout lebih panjang
                            verify=False
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            logger.debug(f"✅ Response: {json.dumps(data, indent=2)[:200]}")
                            
                            # Parse response
                            is_blocked = self._parse_response(data)
                            
                            if is_blocked is not None:
                                return is_blocked
                            else:
                                logger.warning(f"⚠️ Response tidak jelas, coba endpoint lain...")
                                continue
                        else:
                            logger.warning(f"⚠️ HTTP {response.status_code} dari {endpoint}")
                            time.sleep(1)
                            continue
                            
                    except requests.exceptions.Timeout:
                        logger.warning(f"⏰ Timeout attempt {attempt+1} untuk {domain}")
                        time.sleep(2)
                        continue
                    except requests.exceptions.ProxyError as e:
                        logger.error(f"❌ Proxy error: {e}")
                        # Coba tanpa proxy
                        try:
                            logger.info("🔄 Mencoba tanpa proxy...")
                            fallback_session = requests.Session()
                            response = fallback_session.get(
                                endpoint,
                                params={'domain': domain},
                                headers=self.headers,
                                timeout=30,
                                verify=False
                            )
                            if response.status_code == 200:
                                data = response.json()
                                return self._parse_response(data)
                        except:
                            pass
                        time.sleep(2)
                        continue
                    except Exception as e:
                        logger.warning(f"⚠️ Error: {e}")
                        time.sleep(2)
                        continue
                
                # Jika semua retry gagal untuk endpoint ini, coba endpoint berikutnya
            
            # Jika semua gagal, return None
            logger.warning(f"⚠️ Semua endpoint gagal untuk {domain}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error checking {domain}: {e}")
            return None
    
    def _parse_response(self, data):
        """Parse response dari API"""
        try:
            # Format 1: {'status': 'blocked'} atau {'status': 'not blocked'}
            if 'status' in data:
                status = str(data['status']).lower()
                if status in ['blocked', 'blocked']:
                    return True
                elif status in ['not blocked', 'not_blocked', 'aman', 'notblocked']:
                    return False
            
            # Format 2: {'blocked': True/False}
            if 'blocked' in data:
                return bool(data['blocked'])
            
            # Format 3: {'result': {'status': 'blocked'}}
            if 'result' in data and isinstance(data['result'], dict):
                result = data['result']
                if 'status' in result:
                    if str(result['status']).lower() == 'blocked':
                        return True
                    return False
                if 'blocked' in result:
                    return bool(result['blocked'])
            
            # Format 4: {'data': {'status': 'blocked'}}
            if 'data' in data and isinstance(data['data'], dict):
                if 'status' in data['data']:
                    if str(data['data']['status']).lower() == 'blocked':
                        return True
                    return False
            
            # Format 5: {'Blocked': True/False}
            if 'Blocked' in data:
                return bool(data['Blocked'])
            
            # Jika tidak ada indikasi, asumsi aman
            logger.info(f"✅ Response tidak menunjukkan blokir, asumsi AMAN")
            return False
            
        except Exception as e:
            logger.error(f"Parse error: {e}")
            return None
    
    def check_all_domains(self, domains):
        """Cek semua domain satu per satu"""
        try:
            if not domains:
                return []
            
            all_blocked = []
            total = len(domains)
            
            logger.info(f"📋 Total domain: {total}")
            logger.info("=" * 50)
            
            for i, domain in enumerate(domains, 1):
                logger.info(f"[{i}/{total}] Memeriksa: {domain}")
                
                is_blocked = self.check_single_domain(domain)
                
                if is_blocked is True:
                    all_blocked.append(domain)
                    logger.warning(f"🚫 {domain}: TERBLOKIR")
                elif is_blocked is False:
                    logger.info(f"✅ {domain}: AMAN")
                else:
                    logger.warning(f"⚠️ {domain}: GAGAL (asumsi AMAN)")
                
                # Delay antar domain
                if i < total:
                    delay = 3
                    logger.info(f"⏳ Menunggu {delay} detik...")
                    time.sleep(delay)
            
            return all_blocked
            
        except Exception as e:
            logger.error(f"Error checking all domains: {e}")
            return []

def baca_domain():
    """Baca domain dari file domain.txt"""
    try:
        if not os.path.exists("domain.txt"):
            logger.error("❌ File domain.txt tidak ditemukan!")
            with open("domain.txt", "w") as f:
                f.write("# Daftar domain untuk dicek\n")
                f.write("# Satu domain per baris\n")
                f.write("google.com\n")
                f.write("facebook.com\n")
                f.write("twitter.com\n")
            return []
        
        domains = []
        with open("domain.txt", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    line = line.lower()
                    for prefix in ['http://', 'https://', 'www.']:
                        if line.startswith(prefix):
                            line = line[len(prefix):]
                    line = line.rstrip('/')
                    if '.' in line and len(line) > 3:
                        domains.append(line)
        
        logger.info(f"📖 Membaca {len(domains)} domain dari domain.txt")
        return domains
        
    except Exception as e:
        logger.error(f"Error membaca domain: {e}")
        return []

# ============================================
# FUNGSI TELEGRAM
# ============================================

async def kirim_status():
    try:
        waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        domains = baca_domain()
        domain_count = len(domains)
        
        message = (
            "🤖 *TrustPositif API Checker Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Mode:** TrustPositif API + Fallback\n"
            f"🔑 **Proxy:** SOCKS5/HTTP\n"
            f"🌐 **API:** trustpositif.komdigi.go.id\n\n"
            "_Bot akan mengecek domain setiap 15 menit_"
        )
        
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="Markdown"
        )
        logger.info("📤 Status bot terkirim")
        
    except Exception as e:
        logger.error(f"Gagal kirim status: {e}")

async def kirim_laporan(blocked_domains, total_domains):
    try:
        blocked_count = len(blocked_domains)
        
        if blocked_count == 0:
            message = (
                "✅ *LAPORAN CEK NAWALA*\n\n"
                "**SEMUA DOMAIN AMAN!** 🎉\n\n"
                f"📊 **Total Domain:** {total_domains}\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                "Tidak ada domain yang terblokir."
            )
            
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode="Markdown"
            )
            logger.info(f"📤 Laporan aman: {total_domains} domain")
            
        else:
            domain_list = ""
            for i, domain in enumerate(blocked_domains, 1):
                domain_list += f"{i}. 🚫 `{domain}`\n"
            
            message = (
                "❌❌❌❌❌❌❌❌❌\n\n"
                f"**{blocked_count} DOMAIN TERBLOKIR**\n\n"
                f"{domain_list}\n"
                f"📊 **Statistik:** {blocked_count}/{total_domains} domain terblokir\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                "_Sumber: TrustPositif API_"
            )
            
            if len(message) > 4096:
                await kirim_pesan_terbagi(blocked_domains, total_domains)
            else:
                await application.bot.send_message(
                    chat_id=CHAT_ID,
                    text=message,
                    parse_mode="Markdown"
                )
                logger.info(f"📤 Laporan terblokir: {blocked_count} domain")
            
    except Exception as e:
        logger.error(f"Gagal kirim laporan: {e}")

async def kirim_pesan_terbagi(blocked_domains, total_domains):
    try:
        blocked_count = len(blocked_domains)
        chunk_size = 20
        chunks = [blocked_domains[i:i + chunk_size] for i in range(0, len(blocked_domains), chunk_size)]
        
        for i, chunk in enumerate(chunks, 1):
            domain_list = ""
            for j, domain in enumerate(chunk, 1):
                domain_list += f"{(i-1)*chunk_size + j}. 🚫 `{domain}`\n"
            
            message = (
                f"🚨 *LAPORAN DOMAIN TERBLOKIR (Bagian {i}/{len(chunks)})*\n\n"
                f"{domain_list}\n"
            )
            
            if i == len(chunks):
                message += (
                    f"📊 **Statistik:** {blocked_count}/{total_domains} domain terblokir\n"
                    f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                    "_Sumber: TrustPositif API_"
                )
            
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode="Markdown"
            )
            
            if i < len(chunks):
                await asyncio.sleep(1)
        
        logger.info(f"📤 Laporan terbagi: {blocked_count} domain dalam {len(chunks)} pesan")
        
    except Exception as e:
        logger.error(f"Gagal kirim pesan terbagi: {e}")

async def cek_domain_job():
    try:
        logger.info("=" * 60)
        logger.info("🔄 MEMULAI PEMERIKSAAN TRUSTPOSITIF API")
        logger.info("=" * 60)
        
        domains = baca_domain()
        if not domains:
            logger.warning("⚠️ Tidak ada domain untuk dicek")
            return
        
        logger.info(f"📋 Jumlah domain: {len(domains)}")
        
        checker = TrustPositifAPIChecker()
        
        start_time = time.time()
        blocked_domains = checker.check_all_domains(domains)
        elapsed_time = time.time() - start_time
        
        logger.info(f"⏱️ Waktu pemrosesan: {elapsed_time:.2f} detik")
        logger.info(f"📊 Hasil: {len(blocked_domains)} dari {len(domains)} domain terblokir")
        
        await kirim_laporan(blocked_domains, len(domains))
        
        logger.info("✅ Pemeriksaan selesai")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Error dalam cek_domain_job: {e}")
        import traceback
        logger.error(traceback.format_exc())

def run_async_job(job_func):
    asyncio.create_task(job_func())

async def schedule_runner():
    while True:
        try:
            schedule.run_pending()
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 Schedule runner dihentikan")
            break
        except Exception as e:
            logger.error(f"Error dalam schedule runner: {e}")
            await asyncio.sleep(5)

async def main():
    print("\n" + "=" * 60)
    print("🚀 TRUSTPOSITIF API CHECKER BOT")
    print("📌 Mode: TrustPositif API + Fallback")
    print("=" * 60)
    
    logger.info("Bot starting...")
    logger.info("🌐 API: trustpositif.komdigi.go.id")
    
    await kirim_status()
    
    logger.info("Setting up schedule...")
    schedule.every(15).minutes.do(lambda: run_async_job(cek_domain_job))
    logger.info("✅ Schedule: Check domains every 15 minutes")
    
    schedule.every(3).hours.do(lambda: run_async_job(kirim_status))
    logger.info("✅ Schedule: Status report every 3 hours")
    
    logger.info("Running first check in 5 seconds...")
    await asyncio.sleep(5)
    await cek_domain_job()
    
    logger.info("✅ Bot successfully started!")
    logger.info("📍 Domain checks: Every 15 minutes")
    logger.info("📍 Mode: TrustPositif API + Fallback")
    logger.info("📍 Press Ctrl+C to stop\n")
    
    await schedule_runner()

if __name__ == "__main__":
    try:
        import schedule
        import requests
        from telegram import __version__
        logger.info(f"✅ Dependencies: requests, schedule, python-telegram-bot v{__version__}")
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        logger.info("💡 Install dengan: pip install requests schedule python-telegram-bot PySocks")
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        import traceback
        logger.error(traceback.format_exc())
