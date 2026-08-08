#!/usr/bin/env python3
"""
AMAROK Nawala Checker Bot
Cek domain terblokir TrustPositif/Nawala dengan proxy DataImpulse
"""

import os
import sys
import time
import asyncio
import logging
import json
import re
from datetime import datetime
from typing import List, Tuple, Optional
from urllib.parse import urlparse

import requests
import schedule
from telegram.ext import Application
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

# ============ KONFIGURASI PROXY DATAIMPULSE ============
# Data dari dashboard DataImpulse
PROXY_USERNAME = "986a4990d6e126d77bf9"
PROXY_PASSWORD = "767adc34dc218955"
PROXY_HOST = "gw.dataimpulse.com"
PROXY_PORT = "823"

# Format proxy DataImpulse dengan country code ID (Indonesia)
# Format: http://<username>__cr.id:<password>@<gateway>:<port>
PROXY_URL = f"http://{PROXY_USERNAME}__cr.id:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT}"

# ============ KONFIGURASI TELEGRAM ============
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not TOKEN or not CHAT_ID:
    print("❌ ERROR: TOKEN atau CHAT_ID tidak ditemukan!")
    print("   Set di .env file:")
    print("   TOKEN=your_telegram_token")
    print("   CHAT_ID=your_chat_id")
    sys.exit(1)

# ============ KONFIGURASI PROXY ============
proxies = {
    'http': PROXY_URL,
    'https': PROXY_URL,
}

# ============ LOGGING ============
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

# ============ TELEGRAM BOT ============
try:
    application = Application.builder().token(TOKEN).build()
    logger.info("✅ Bot Telegram berhasil diinisialisasi")
except Exception as e:
    logger.error(f"❌ Gagal setup bot: {e}")
    sys.exit(1)

# ============ CHECKER CLASS ============
class TrustPositifChecker:
    """Checker untuk TrustPositif menggunakan proxy DataImpulse"""
    
    def __init__(self):
        self.session = requests.Session()
        
        # Setup retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        self.session.proxies.update(proxies)
        self.session.timeout = 30
        self.session.verify = False
        self.session.trust_env = False
        
        # Headers untuk meniru browser Indonesia
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        self.base_url = "https://trustpositif.komdigi.go.id"
        self.api_url = f"{self.base_url}/Rest_server/getrecordsname_home"
        self.csrf_token = None
        
    def get_csrf_token(self) -> Optional[str]:
        """Dapatkan CSRF token dari halaman utama"""
        try:
            logger.info("🔑 Mengambil CSRF token...")
            
            response = self.session.get(
                self.base_url,
                headers=self.headers,
                timeout=15
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Gagal load halaman: {response.status_code}")
                return None
                
            # Cari CSRF token
            csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text)
            if csrf_match:
                self.csrf_token = csrf_match.group(1)
                logger.info(f"✅ CSRF token ditemukan: {self.csrf_token[:10]}...")
                return self.csrf_token
                
            # Fallback
            logger.warning("⚠️ CSRF token tidak ditemukan, menggunakan default")
            self.csrf_token = "3835f8d38d9c0a271d2d782a70113bc2"
            return self.csrf_token
            
        except Exception as e:
            logger.error(f"❌ Error get CSRF: {e}")
            return None
    
    def check_domain(self, domain: str) -> Tuple[bool, str]:
        """
        Cek satu domain di TrustPositif
        Returns: (is_blocked, message)
        """
        domain = domain.strip().lower()
        
        # Bersihkan domain
        for prefix in ['http://', 'https://', 'www.']:
            if domain.startswith(prefix):
                domain = domain[len(prefix):]
        domain = domain.rstrip('/')
        
        logger.info(f"🔍 Checking: {domain}")
        
        try:
            # Ambil CSRF token jika belum ada
            if not self.csrf_token:
                if not self.get_csrf_token():
                    return False, "Gagal mendapatkan CSRF token"
            
            # Data untuk request
            data = {
                'csrf_token': self.csrf_token,
                'name': domain
            }
            
            # Headers untuk AJAX request
            api_headers = {
                'User-Agent': self.headers['User-Agent'],
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': f'{self.base_url}/',
                'Origin': self.base_url,
                'Connection': 'keep-alive',
            }
            
            # Kirim request
            response = self.session.post(
                self.api_url,
                data=data,
                headers=api_headers,
                timeout=15
            )
            
            logger.info(f"📡 Response status: {response.status_code}")
            
            if response.status_code == 200:
                return self.parse_response(response.text, domain)
            else:
                logger.error(f"❌ HTTP Error {response.status_code}")
                return False, f"HTTP {response.status_code}"
                
        except requests.exceptions.Timeout:
            logger.error(f"❌ Timeout untuk {domain}")
            return False, "Timeout"
        except requests.exceptions.ConnectionError:
            logger.error(f"❌ Connection error untuk {domain}")
            return False, "Connection Error"
        except Exception as e:
            logger.error(f"❌ Error checking {domain}: {e}")
            return False, str(e)
    
    def parse_response(self, response_text: str, domain: str) -> Tuple[bool, str]:
        """Parse response dari TrustPositif"""
        try:
            # Coba parse sebagai JSON
            try:
                data = json.loads(response_text)
                
                if 'values' in data:
                    for item in data['values']:
                        if isinstance(item, dict):
                            item_domain = item.get('Domain', '').strip().lower()
                            status = item.get('Status', '').strip()
                            
                            if item_domain == domain.lower():
                                if status == 'Tidak Ada':
                                    logger.info(f"✅ {domain}: ALLOWED (aman)")
                                    return False, "ALLOWED - Tidak diblokir"
                                else:
                                    logger.warning(f"🚫 {domain}: BLOCKED ({status})")
                                    return True, f"BLOCKED - {status}"
                
                return False, "ALLOWED - Tidak ditemukan dalam database"
                
            except json.JSONDecodeError:
                # Bukan JSON, parse HTML
                if 'tidak ada' in response_text.lower():
                    return False, "ALLOWED - Tidak diblokir"
                elif domain.lower() in response_text.lower():
                    return True, "BLOCKED - Terdeteksi dalam sistem"
                else:
                    return False, "ALLOWED - Tidak ditemukan"
                    
        except Exception as e:
            logger.error(f"❌ Parse error: {e}")
            return False, f"Parse error: {e}"
    
    def check_domains_batch(self, domains: List[str]) -> List[Tuple[str, bool, str]]:
        """Cek multiple domains"""
        results = []
        
        # Ambil CSRF token sekali untuk semua domain
        if not self.csrf_token:
            if not self.get_csrf_token():
                logger.error("❌ Gagal mendapatkan CSRF token")
                return [(d, False, "CSRF token failed") for d in domains]
        
        for i, domain in enumerate(domains):
            is_blocked, message = self.check_domain(domain)
            results.append((domain, is_blocked, message))
            
            # Delay antar request
            if i < len(domains) - 1:
                time.sleep(1.5)
        
        return results

# ============ FUNGSI UTAMA ============
def baca_domain() -> List[str]:
    """Baca domain dari file domain.txt"""
    try:
        if not os.path.exists("domain.txt"):
            with open("domain.txt", "w") as f:
                f.write("# Daftar domain untuk dicek\n")
                f.write("# Satu domain per baris\n\n")
                f.write("google.com\n")
                f.write("facebook.com\n")
                f.write("youtube.com\n")
            logger.info("✅ File domain.txt dibuat dengan contoh")
            return []
        
        domains = []
        with open("domain.txt", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    domain = line.lower()
                    for prefix in ['http://', 'https://', 'www.']:
                        if domain.startswith(prefix):
                            domain = domain[len(prefix):]
                    domain = domain.rstrip('/')
                    if '.' in domain and len(domain) > 3:
                        domains.append(domain)
        
        logger.info(f"📖 Membaca {len(domains)} domain dari domain.txt")
        return domains
        
    except Exception as e:
        logger.error(f"❌ Error membaca domain: {e}")
        return []

async def kirim_status() -> None:
    """Kirim status bot"""
    try:
        domains = baca_domain()
        domain_count = len(domains)
        waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        
        message = (
            "🤖 *AMAROK Nawala Checker Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🌐 **Proxy:** DataImpulse Indonesia (Residential)\n"
            f"📡 **Status:** ✅ Connected\n\n"
            "_Bot mengecek domain setiap 15 menit_\n"
            "_Source: TrustPositif Kominfo_"
        )
        
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="Markdown"
        )
        logger.info("📤 Status bot terkirim")
        
    except Exception as e:
        logger.error(f"❌ Gagal kirim status: {e}")

async def kirim_laporan(results: List[Tuple[str, bool, str]], total_domains: int) -> None:
    """Kirim laporan hasil pengecekan"""
    try:
        blocked = [(d, m) for d, is_blocked, m in results if is_blocked]
        blocked_count = len(blocked)
        
        if blocked_count == 0:
            message = (
                "✅ *LAPORAN CEK NAWALA*\n\n"
                "**SEMUA DOMAIN AMAN!** 🎉\n\n"
                f"📊 **Total Domain:** {total_domains}\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                "Tidak ada domain yang terblokir TrustPositif."
            )
            
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode="Markdown"
            )
            logger.info(f"📤 Laporan aman: {total_domains} domain")
            
        else:
            domain_list = ""
            for i, (domain, method) in enumerate(blocked, 1):
                domain_list += f"{i}. 🚫 `{domain}`\n"
            
            message = (
                "❌❌❌❌❌❌❌❌❌*\n\n"
                f"**{blocked_count} DOMAIN TERBLOKIR**\n\n"
                f"{domain_list}\n"
                f"📊 **Statistik:** {blocked_count}/{total_domains} domain terblokir\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                "_Sumber: TrustPositif Kominfo via DataImpulse_"
            )
            
            if len(message) > 4096:
                chunks = [blocked[i:i+15] for i in range(0, len(blocked), 15)]
                for i, chunk in enumerate(chunks, 1):
                    chunk_msg = f"🚨 *LAPORAN (Bagian {i}/{len(chunks)})*\n\n"
                    for j, (domain, method) in enumerate(chunk, 1):
                        chunk_msg += f"{j}. 🚫 `{domain}`\n"
                    
                    if i == len(chunks):
                        chunk_msg += f"\n📊 **Total:** {blocked_count}/{total_domains} domain terblokir"
                    
                    await application.bot.send_message(
                        chat_id=CHAT_ID,
                        text=chunk_msg,
                        parse_mode="Markdown"
                    )
                    await asyncio.sleep(1)
            else:
                await application.bot.send_message(
                    chat_id=CHAT_ID,
                    text=message,
                    parse_mode="Markdown"
                )
                logger.info(f"📤 Laporan terblokir: {blocked_count} domain")
            
    except Exception as e:
        logger.error(f"❌ Gagal kirim laporan: {e}")

async def cek_domain_job() -> None:
    """Job utama untuk mengecek domain"""
    try:
        logger.info("=" * 60)
        logger.info("🔄 MEMULAI PEMERIKSAAN TRUSTPOSITIF")
        logger.info(f"🌐 Proxy: DataImpulse Indonesia (Residential)")
        logger.info("=" * 60)
        
        # Baca domain
        domains = baca_domain()
        if not domains:
            logger.warning("⚠️ Tidak ada domain untuk dicek")
            return
        
        logger.info(f"📋 Jumlah domain: {len(domains)}")
        
        # Buat checker
        checker = TrustPositifChecker()
        
        # Cek semua domain
        start_time = time.time()
        results = checker.check_domains_batch(domains)
        elapsed_time = time.time() - start_time
        
        # Hitung statistik
        total = len(results)
        blocked = sum(1 for _, is_blocked, _ in results if is_blocked)
        
        logger.info(f"⏱️ Waktu: {elapsed_time:.2f} detik")
        logger.info(f"📊 Hasil: {blocked}/{total} domain terblokir")
        
        # Kirim laporan
        await kirim_laporan(results, total)
        
        logger.info("✅ Pemeriksaan selesai")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Error dalam cek_domain_job: {e}")
        import traceback
        logger.error(traceback.format_exc())

def run_async_job(job_func):
    """Wrapper untuk menjalankan async job dari schedule"""
    asyncio.create_task(job_func())

async def schedule_runner():
    """Menjalankan schedule dalam loop asyncio"""
    while True:
        try:
            schedule.run_pending()
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 Schedule runner dihentikan")
            break
        except Exception as e:
            logger.error(f"❌ Error dalam schedule runner: {e}")
            await asyncio.sleep(5)

async def test_koneksi() -> bool:
    """Test koneksi ke TrustPositif via proxy"""
    try:
        logger.info("🔗 Testing koneksi ke TrustPositif via DataImpulse...")
        
        response = requests.get(
            "https://trustpositif.komdigi.go.id/",
            timeout=15,
            proxies=proxies,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            },
            verify=False
        )
        
        if response.status_code == 200:
            if 'TrustPositif' in response.text or 'Kominfo' in response.text:
                logger.info("✅ Koneksi BERHASIL ke TrustPositif")
                return True
            else:
                logger.warning("⚠️ Response OK tapi halaman tidak sesuai")
                return False
        else:
            logger.warning(f"⚠️ HTTP Status: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test koneksi GAGAL: {e}")
        return False

async def main():
    """Main function"""
    print("\n" + "=" * 60)
    print("🚀 AMAROK NAWALA CHECKER BOT")
    print("=" * 60)
    print(f"📱 Bot Token: {TOKEN[:10]}...{TOKEN[-5:]}")
    print(f"📱 Chat ID: {CHAT_ID}")
    print(f"🌐 Proxy: DataImpulse Indonesia (Residential)")
    print(f"   Host: {PROXY_HOST}:{PROXY_PORT}")
    print(f"   Username: {PROXY_USERNAME}")
    print("=" * 60 + "\n")
    
    logger.info("Bot starting...")
    
    # Test proxy
    logger.info("Testing proxy DataImpulse...")
    try:
        test_response = requests.get(
            'https://api.ipify.org/',
            proxies=proxies,
            timeout=10,
            verify=False
        )
        proxy_ip = test_response.text.strip()
        logger.info(f"✅ Proxy IP: {proxy_ip}")
        print(f"🌐 Proxy IP: {proxy_ip}")
    except Exception as e:
        logger.error(f"❌ Proxy test gagal: {e}")
        print(f"❌ Proxy test gagal: {e}")
        print("   Periksa kredensial proxy DataImpulse Anda!")
        print(f"   Error: {e}")
    
    # Test koneksi ke TrustPositif
    if not await test_koneksi():
        logger.warning("⚠️ Koneksi ke TrustPositif bermasalah, bot tetap berjalan...")
    
    # Kirim status awal
    await kirim_status()
    
    # Setup schedule
    logger.info("Setting up schedule...")
    schedule.every(15).minutes.do(lambda: run_async_job(cek_domain_job))
    schedule.every(3).hours.do(lambda: run_async_job(kirim_status))
    
    logger.info("✅ Schedule: Check domains every 15 minutes")
    logger.info("✅ Schedule: Status report every 3 hours")
    
    # Jalankan pengecekan pertama
    logger.info("Running first check in 3 seconds...")
    await asyncio.sleep(3)
    await cek_domain_job()
    
    logger.info("✅ Bot successfully started!")
    logger.info("📍 Domain checks: Every 15 minutes")
    logger.info("📍 Status reports: Every 3 hours")
    logger.info("📍 Proxy: DataImpulse Indonesia (Residential)")
    logger.info("📍 Press Ctrl+C to stop\n")
    
    # Jalankan schedule runner
    await schedule_runner()

if __name__ == "__main__":
    # Cek dependencies
    try:
        import schedule
        import requests
        from telegram import __version__
        logger.info(f"✅ Dependencies OK (telegram-bot v{__version__})")
    except ImportError as e:
        logger.error(f"❌ Missing dependency: {e}")
        logger.info("💡 Install dengan: pip install -r requirements.txt")
        sys.exit(1)
    
    # Jalankan bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"💥 Critical error: {e}")
        import traceback
        logger.error(traceback.format_exc())
