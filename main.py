import os
import sys
import time
import asyncio
import logging
import schedule
import json
import re
import socket
from telegram.ext import Application
from datetime import datetime
import requests
import urllib3

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
USE_PROXY = os.getenv("USE_PROXY", "true").lower() == "true"
PROXY_HOST = os.getenv("PROXY_HOST", "193.5.64.24")
PROXY_PORT = os.getenv("PROXY_PORT", "59101")
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "pulsaslot1888")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "b3Kft6IMwG")
PROXY_TYPE = os.getenv("PROXY_TYPE", "socks5")

if not TOKEN or not CHAT_ID:
    logger.error("TOKEN atau CHAT_ID tidak ditemukan!")
    sys.exit(1)

# Setup proxy untuk requests
proxies = None
if USE_PROXY and PROXY_HOST and PROXY_PORT:
    if PROXY_TYPE.lower() == "socks5":
        if PROXY_USERNAME and PROXY_PASSWORD:
            proxy_url = f"socks5://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT}"
        else:
            proxy_url = f"socks5://{PROXY_HOST}:{PROXY_PORT}"
        proxies = {'http': proxy_url, 'https': proxy_url}
        logger.info(f"🔑 Menggunakan SOCKS5 proxy: {PROXY_HOST}:{PROXY_PORT}")
    else:
        if PROXY_USERNAME and PROXY_PASSWORD:
            proxy_url = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT}"
        else:
            proxy_url = f"http://{PROXY_HOST}:{PROXY_PORT}"
        proxies = {'http': proxy_url, 'https': proxy_url}
        logger.info(f"🔑 Menggunakan HTTP proxy: {PROXY_HOST}:{PROXY_PORT}")
else:
    proxies = None
    logger.info("🔓 Koneksi langsung (tanpa proxy)")

# Setup SOCKS5 untuk socket
if USE_PROXY and PROXY_TYPE.lower() == "socks5":
    try:
        import socks
        socks.set_default_proxy(
            socks.SOCKS5,
            PROXY_HOST,
            int(PROXY_PORT),
            username=PROXY_USERNAME if PROXY_USERNAME else None,
            password=PROXY_PASSWORD if PROXY_PASSWORD else None
        )
        socket.socket = socks.socksocket
        logger.info("✅ SOCKS5 proxy di-set")
    except ImportError:
        logger.warning("⚠️ PySocks tidak terinstall")
    except Exception as e:
        logger.error(f"❌ Gagal setup SOCKS5: {e}")

# Bot setup
try:
    application = Application.builder().token(TOKEN).build()
    logger.info("✅ Bot Telegram berhasil diinisialisasi")
except Exception as e:
    logger.error(f"❌ Gagal setup bot: {e}")
    sys.exit(1)

def baca_domain():
    """Baca domain dari file domain.txt"""
    try:
        # Cek apakah file domain.txt ada
        if not os.path.exists("domain.txt"):
            logger.error("❌ File domain.txt tidak ditemukan!")
            logger.info("📝 Membuat file domain.txt contoh...")
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
                # Skip komentar dan baris kosong
                if line and not line.startswith('#'):
                    line = line.lower()
                    # Hapus protocol
                    for prefix in ['http://', 'https://', 'www.']:
                        if line.startswith(prefix):
                            line = line[len(prefix):]
                    line = line.rstrip('/')
                    # Validasi domain sederhana
                    if '.' in line and len(line) > 3:
                        domains.append(line)
        
        if domains:
            logger.info(f"📖 Membaca {len(domains)} domain dari domain.txt")
            for domain in domains:
                logger.info(f"   - {domain}")
        else:
            logger.warning("⚠️ Tidak ada domain ditemukan di domain.txt")
        
        return domains
        
    except Exception as e:
        logger.error(f"Error membaca domain: {e}")
        return []

class TrustPositifChecker:
    def __init__(self):
        self.base_url = "https://trustpositif.id"
        self.checker_url = f"{self.base_url}/checker"
        self.session = requests.Session()
        if proxies:
            self.session.proxies.update(proxies)
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Origin': self.base_url,
            'Referer': f'{self.checker_url}/',
            'Content-Type': 'application/json',
        }
    
    def check_batch(self, domains):
        """Cek batch domain"""
        try:
            if not domains:
                return []
            
            if len(domains) > 100:
                domains = domains[:100]
            
            logger.info(f"🔍 Checking {len(domains)} domains...")
            
            response = self.session.post(
                f"{self.checker_url}/check",
                json={'domains': domains},
                headers=self.headers,
                timeout=30,
                verify=False
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return self._parse_results(data.get('results', []))
                else:
                    logger.error(f"API error: {data.get('message', 'Unknown')}")
                    return []
            else:
                logger.error(f"HTTP {response.status_code}")
                # Jika 403 dan pakai proxy, coba tanpa proxy
                if response.status_code == 403 and proxies:
                    logger.warning("⚠️ Proxy ditolak, mencoba tanpa proxy...")
                    fallback_session = requests.Session()
                    fallback_response = fallback_session.post(
                        f"{self.checker_url}/check",
                        json={'domains': domains},
                        headers=self.headers,
                        timeout=30,
                        verify=False
                    )
                    if fallback_response.status_code == 200:
                        data = fallback_response.json()
                        if data.get('success'):
                            return self._parse_results(data.get('results', []))
                return []
                
        except requests.exceptions.ProxyError as e:
            logger.error(f"Proxy error: {e}")
            try:
                logger.warning("🔄 Mencoba tanpa proxy...")
                fallback_session = requests.Session()
                response = fallback_session.post(
                    f"{self.checker_url}/check",
                    json={'domains': domains},
                    headers=self.headers,
                    timeout=30,
                    verify=False
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success'):
                        return self._parse_results(data.get('results', []))
            except:
                pass
            return []
        except Exception as e:
            logger.error(f"Error: {e}")
            return []
    
    def _parse_results(self, results):
        """Parse hasil dari API"""
        blocked = []
        for result in results:
            domain = result.get('Domain', '') or result.get('domain', '')
            is_blocked = result.get('Blocked', False) or result.get('blocked', False)
            
            if domain and is_blocked:
                blocked.append(domain)
                logger.warning(f"🚫 {domain}: DIBLOKIR")
            elif domain:
                logger.info(f"✅ {domain}: AMAN")
        
        return blocked
    
    def check_all_domains(self, domains):
        """Cek semua domain dengan batch"""
        try:
            if not domains:
                return []
            
            all_blocked = []
            batch_size = 100
            
            for i in range(0, len(domains), batch_size):
                batch = domains[i:i + batch_size]
                batch_num = i // batch_size + 1
                total = (len(domains) + batch_size - 1) // batch_size
                
                logger.info(f"📦 Batch {batch_num}/{total}: {len(batch)} domains")
                
                blocked_batch = self.check_batch(batch)
                all_blocked.extend(blocked_batch)
                
                if i + batch_size < len(domains):
                    delay = 5
                    logger.info(f"⏳ Menunggu {delay} detik...")
                    time.sleep(delay)
            
            return all_blocked
            
        except Exception as e:
            logger.error(f"Error: {e}")
            return []

# ============================================
# FUNGSI TELEGRAM
# ============================================

async def kirim_status():
    try:
        waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        domains = baca_domain()
        domain_count = len(domains)
        
        proxy_status = "✅" if USE_PROXY else "❌"
        
        message = (
            "🤖 *TrustPositif Checker Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Mode:** Batch (max 100 domain/request)\n"
            f"🔑 **Proxy:** {proxy_status}\n"
            f"🌐 **Sumber:** trustpositif.id/checker\n\n"
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
                "_Sumber: trustpositif.id/checker_"
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
                    "_Sumber: trustpositif.id/checker_"
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
        logger.info("🔄 MEMULAI PEMERIKSAAN TRUSTPOSITIF.ID")
        logger.info(f"🔄 Proxy: {'AKTIF' if USE_PROXY else 'NONAKTIF'}")
        logger.info("=" * 60)
        
        domains = baca_domain()
        if not domains:
            logger.warning("⚠️ Tidak ada domain untuk dicek")
            return
        
        logger.info(f"📋 Jumlah domain: {len(domains)}")
        
        checker = TrustPositifChecker()
        
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
    print("🚀 TRUSTPOSITIF.ID CHECKER BOT")
    print(f"📌 Proxy: {'AKTIF' if USE_PROXY else 'NONAKTIF'}")
    if USE_PROXY:
        print(f"📌 Proxy: {PROXY_HOST}:{PROXY_PORT} ({PROXY_TYPE.upper()})")
    print("=" * 60)
    
    logger.info("Bot starting...")
    logger.info("🌐 Source: trustpositif.id/checker")
    
    # Cek domain.txt
    domains = baca_domain()
    logger.info(f"📊 Total domain terdaftar: {len(domains)}")
    
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
    logger.info("📍 Mode: Batch (max 100 domain per request)")
    logger.info(f"📍 Proxy: {'AKTIF' if USE_PROXY else 'NONAKTIF'}")
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
        logger.info("💡 Install dengan: pip install requests schedule python-telegram-bot")
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        import traceback
        logger.error(traceback.format_exc())
