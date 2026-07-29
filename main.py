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
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "986a4990d6e126d77bf9")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "767adc34dc218955")

# Multiple gateway options (coba satu per satu)
GATEWAYS = [
    ("gw.dataimpulse.com", "823"),
    ("74.81.81.81", "823"),
    ("gw.dataimpulse.com", "824"),
    ("74.81.81.81", "824"),
]

# ============ KONFIGURASI TELEGRAM ============
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not TOKEN or not CHAT_ID:
    print("❌ ERROR: TOKEN atau CHAT_ID tidak ditemukan!")
    print("   Set di .env file:")
    print("   TOKEN=your_telegram_token")
    print("   CHAT_ID=your_chat_id")
    sys.exit(1)

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

# ============ PROXY MANAGER ============
class ProxyManager:
    """Manajemen proxy dengan multiple gateway dan retry"""
    
    def __init__(self):
        self.current_gateway_index = 0
        self.gateways = GATEWAYS
        self.proxy_url = None
        self.session = None
        self.is_connected = False
        
    def get_proxy_url(self, gateway_index: int = None) -> str:
        """Dapatkan URL proxy untuk gateway tertentu"""
        if gateway_index is None:
            gateway_index = self.current_gateway_index
            
        host, port = self.gateways[gateway_index]
        
        # Format: username__cr.id:password@host:port
        proxy_url = f"http://{PROXY_USERNAME}__cr.id:{PROXY_PASSWORD}@{host}:{port}"
        return proxy_url
    
    def create_session(self, gateway_index: int = None) -> requests.Session:
        """Buat session dengan retry mechanism"""
        session = requests.Session()
        
        # Retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Proxy
        proxy_url = self.get_proxy_url(gateway_index)
        session.proxies = {
            'http': proxy_url,
            'https': proxy_url,
        }
        
        # Settings
        session.timeout = 30
        session.verify = False
        session.trust_env = False
        
        return session, proxy_url
    
    def test_connection(self) -> bool:
        """Test koneksi proxy dengan multiple gateway"""
        logger.info("🔗 Testing proxy DataImpulse...")
        
        for i in range(len(self.gateways)):
            try:
                logger.info(f"   Testing gateway {i+1}/{len(self.gateways)}: {self.gateways[i][0]}:{self.gateways[i][1]}")
                
                session, proxy_url = self.create_session(i)
                
                # Test ke api.ipify.org
                response = session.get(
                    'https://api.ipify.org/',
                    timeout=10
                )
                
                if response.status_code == 200:
                    ip = response.text.strip()
                    logger.info(f"✅ Proxy connected! IP: {ip}")
                    logger.info(f"   Gateway: {self.gateways[i][0]}:{self.gateways[i][1]}")
                    
                    # Simpan session yang berhasil
                    self.session = session
                    self.proxy_url = proxy_url
                    self.current_gateway_index = i
                    self.is_connected = True
                    return True
                    
            except Exception as e:
                logger.warning(f"   ❌ Gateway {i+1} failed: {str(e)[:50]}")
                continue
        
        logger.error("❌ All gateways failed!")
        return False
    
    def get_session(self) -> Optional[requests.Session]:
        """Dapatkan session yang sudah terhubung"""
        if not self.is_connected or not self.session:
            if not self.test_connection():
                return None
        return self.session
    
    def get_proxy_info(self) -> str:
        """Dapatkan informasi proxy yang sedang digunakan"""
        if self.is_connected and self.current_gateway_index < len(self.gateways):
            host, port = self.gateways[self.current_gateway_index]
            return f"{host}:{port}"
        return "Not connected"

# ============ CHECKER CLASS ============
class TrustPositifChecker:
    """Checker untuk TrustPositif menggunakan proxy manager"""
    
    def __init__(self, proxy_manager: ProxyManager):
        self.proxy_manager = proxy_manager
        self.session = None
        self.base_url = "https://trustpositif.komdigi.go.id"
        self.api_url = f"{self.base_url}/Rest_server/getrecordsname_home"
        self.csrf_token = None
        
        # Headers untuk meniru browser Indonesia
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
        
    def get_csrf_token(self) -> Optional[str]:
        """Dapatkan CSRF token dari halaman utama"""
        try:
            logger.info("🔑 Mengambil CSRF token...")
            
            # Dapatkan session dari proxy manager
            self.session = self.proxy_manager.get_session()
            if not self.session:
                logger.error("❌ No active proxy session")
                return None
            
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
    
    def check_domain(self, domain: str, retry_count: int = 0) -> Tuple[bool, str]:
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
            # Dapatkan session dari proxy manager
            self.session = self.proxy_manager.get_session()
            if not self.session:
                return False, "No proxy connection"
            
            # Ambil CSRF token jika belum ada
            if not self.csrf_token:
                if not self.get_csrf_token():
                    return False, "Failed to get CSRF token"
            
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
            elif response.status_code == 403 and retry_count < 2:
                # Coba refresh CSRF token
                logger.warning("⚠️ 403 error, refreshing CSRF token...")
                self.csrf_token = None
                return self.check_domain(domain, retry_count + 1)
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
                                    logger.info(f"✅ {domain}: ALLOWED")
                                    return False, "ALLOWED"
                                else:
                                    logger.warning(f"🚫 {domain}: BLOCKED ({status})")
                                    return True, f"BLOCKED - {status}"
                
                return False, "ALLOWED - Not found"
                
            except json.JSONDecodeError:
                # Bukan JSON, parse HTML
                if 'tidak ada' in response_text.lower():
                    return False, "ALLOWED"
                elif domain.lower() in response_text.lower():
                    return True, "BLOCKED - Detected"
                else:
                    return False, "ALLOWED - Not found"
                    
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

async def kirim_status(proxy_manager: ProxyManager) -> None:
    """Kirim status bot"""
    try:
        domains = baca_domain()
        domain_count = len(domains)
        waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        proxy_info = proxy_manager.get_proxy_info()
        
        message = (
            "🤖 *AMAROK Nawala Checker Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🌐 **Proxy:** DataImpulse ({proxy_info})\n"
            f"📡 **Status:** {'✅ Connected' if proxy_manager.is_connected else '❌ Disconnected'}\n\n"
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
                "🚨 *LAPORAN DOMAIN TERBLOKIR*\n\n"
                f"**{blocked_count} DOMAIN TERBLOKIR**\n\n"
                f"{domain_list}\n"
                f"📊 **Statistik:** {blocked_count}/{total_domains} domain terblokir\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                "_Sumber: TrustPositif Kominfo_"
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

async def cek_domain_job(proxy_manager: ProxyManager) -> None:
    """Job utama untuk mengecek domain"""
    try:
        logger.info("=" * 60)
        logger.info("🔄 MEMULAI PEMERIKSAAN TRUSTPOSITIF")
        logger.info(f"🌐 Proxy: {proxy_manager.get_proxy_info()}")
        logger.info("=" * 60)
        
        # Baca domain
        domains = baca_domain()
        if not domains:
            logger.warning("⚠️ Tidak ada domain untuk dicek")
            return
        
        logger.info(f"📋 Jumlah domain: {len(domains)}")
        
        # Buat checker
        checker = TrustPositifChecker(proxy_manager)
        
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

def run_async_job(job_func, *args):
    """Wrapper untuk menjalankan async job dari schedule"""
    asyncio.create_task(job_func(*args))

async def schedule_runner(proxy_manager: ProxyManager):
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

async def main():
    """Main function"""
    print("\n" + "=" * 60)
    print("🚀 AMAROK NAWALA CHECKER BOT")
    print("=" * 60)
    print(f"📱 Bot Token: {TOKEN[:10]}...{TOKEN[-5:]}")
    print(f"📱 Chat ID: {CHAT_ID}")
    print("=" * 60 + "\n")
    
    logger.info("Bot starting...")
    
    # Setup proxy manager
    proxy_manager = ProxyManager()
    
    # Test proxy
    if not proxy_manager.test_connection():
        logger.error("❌ Proxy test failed! Bot will continue but may not work.")
        print("❌ Proxy test failed! Periksa kredensial DataImpulse Anda.")
    else:
        logger.info("✅ Proxy connected successfully!")
        print(f"✅ Proxy connected: {proxy_manager.get_proxy_info()}")
    
    # Kirim status awal
    await kirim_status(proxy_manager)
    
    # Setup schedule
    logger.info("Setting up schedule...")
    schedule.every(15).minutes.do(lambda: run_async_job(cek_domain_job, proxy_manager))
    schedule.every(3).hours.do(lambda: run_async_job(kirim_status, proxy_manager))
    
    logger.info("✅ Schedule: Check domains every 15 minutes")
    logger.info("✅ Schedule: Status report every 3 hours")
    
    # Jalankan pengecekan pertama
    logger.info("Running first check in 3 seconds...")
    await asyncio.sleep(3)
    await cek_domain_job(proxy_manager)
    
    logger.info("✅ Bot successfully started!")
    logger.info("📍 Domain checks: Every 15 minutes")
    logger.info("📍 Status reports: Every 3 hours")
    logger.info("📍 Press Ctrl+C to stop\n")
    
    # Jalankan schedule runner
    await schedule_runner(proxy_manager)

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
