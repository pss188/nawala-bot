#!/usr/bin/env python3
"""
AMAROK Nawala Checker Bot
Cek domain terblokir TrustPositif/Nawala dengan multiple methods
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

import requests
import schedule
from telegram.ext import Application
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============ KONFIGURASI ============
# Dibaca dari environment variables
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
PROXY_HOST = os.getenv("PROXY_HOST", "95.135.92.164")
PROXY_PORT_HTTP = os.getenv("PROXY_PORT_HTTP", "59100")
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "pulsaslot1888")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")

# Validasi
if not TOKEN:
    print("❌ ERROR: TOKEN tidak ditemukan! Set environment variable TOKEN")
    sys.exit(1)

if not CHAT_ID:
    print("❌ ERROR: CHAT_ID tidak ditemukan! Set environment variable CHAT_ID")
    sys.exit(1)

if not PROXY_PASSWORD:
    print("⚠️  WARNING: PROXY_PASSWORD tidak ditemukan, proxy mungkin tidak berfungsi")

# ============ PROXY SETUP ============
if PROXY_PASSWORD:
    PROXY_HTTP = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT_HTTP}"
else:
    PROXY_HTTP = f"http://{PROXY_HOST}:{PROXY_PORT_HTTP}"

proxies = {
    'http': PROXY_HTTP,
    'https': PROXY_HTTP,
}

# ============ LOGGING SETUP ============
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
class NawalaChecker:
    """Multi-method checker untuk TrustPositif/Nawala"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.proxies.update(proxies)
        self.session.timeout = 15
        
        # Headers
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        
        # DNS resolver untuk metode DNS
        self.dns_servers = ['202.134.0.155', '202.134.2.155', '202.134.7.7']
        
    def check_via_dns(self, domain: str) -> Optional[bool]:
        """Cek domain via DNS Nawala"""
        try:
            import dns.resolver
            
            for dns_server in self.dns_servers:
                try:
                    resolver = dns.resolver.Resolver()
                    resolver.nameservers = [dns_server]
                    resolver.timeout = 3
                    resolver.lifetime = 5
                    
                    try:
                        resolver.resolve(domain, 'A')
                        return True  # Domain bisa di-resolve = AMAN
                    except dns.resolver.NXDOMAIN:
                        return False  # Domain tidak ditemukan = BLOKIR
                    except Exception:
                        continue
                        
                except Exception:
                    continue
                    
            return None  # Semua DNS gagal
            
        except ImportError:
            logger.warning("⚠️ dnspython tidak terinstall, skip DNS check")
            return None
        except Exception as e:
            logger.error(f"DNS error untuk {domain}: {e}")
            return None
    
    def check_via_scraping(self, domain: str) -> Optional[bool]:
        """Cek domain via scraping TrustPositif"""
        try:
            # Step 1: Dapatkan CSRF token
            response = self.session.get(
                "https://trustpositif.komdigi.go.id/",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code != 200:
                return None
                
            # Extract CSRF token
            csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text)
            if csrf_match:
                csrf_token = csrf_match.group(1)
            else:
                # Fallback token
                csrf_token = "3835f8d38d9c0a271d2d782a70113bc2"
            
            # Step 2: Kirim request cek domain
            api_url = "https://trustpositif.komdigi.go.id/Rest_server/getrecordsname_home"
            
            data = {
                'csrf_token': csrf_token,
                'name': domain
            }
            
            api_headers = self.headers.copy()
            api_headers.update({
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Referer': 'https://trustpositif.komdigi.go.id/',
                'Origin': 'https://trustpositif.komdigi.go.id'
            })
            
            response = self.session.post(
                api_url,
                data=data,
                headers=api_headers,
                timeout=15
            )
            
            if response.status_code != 200:
                return None
                
            # Parse response
            if 'tidak ada' in response.text.lower():
                return True  # AMAN
            else:
                return False  # BLOKIR
                
        except Exception as e:
            logger.error(f"Scraping error untuk {domain}: {e}")
            return None
    
    def check_via_trustpositif_api(self, domain: str) -> Optional[bool]:
        """Cek via TrustPositif API (jika ada)"""
        try:
            # Endpoint API yang mungkin
            api_urls = [
                f"https://trustpositif.komdigi.go.id/api/check/{domain}",
                f"https://trustpositif.komdigi.go.id/Rest_server/getrecordsname_home?name={domain}"
            ]
            
            for url in api_urls:
                try:
                    response = self.session.get(url, headers=self.headers, timeout=10)
                    if response.status_code == 200:
                        data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                        
                        # Coba berbagai format response
                        if isinstance(data, dict):
                            if data.get('status') == 'blocked' or data.get('blocked') is True:
                                return False
                            elif data.get('status') == 'allowed' or data.get('blocked') is False:
                                return True
                                
                except:
                    continue
                    
            return None
            
        except Exception as e:
            logger.error(f"API error untuk {domain}: {e}")
            return None
    
    def check_domain(self, domain: str) -> Tuple[bool, str]:
        """
        Cek domain dengan multiple methods
        Returns: (is_blocked, method_used)
        """
        domain = domain.strip().lower()
        
        # Bersihkan domain
        for prefix in ['http://', 'https://', 'www.']:
            if domain.startswith(prefix):
                domain = domain[len(prefix):]
        domain = domain.rstrip('/')
        
        logger.info(f"🔍 Checking: {domain}")
        
        # Method 1: DNS Check (tercepat)
        dns_result = self.check_via_dns(domain)
        if dns_result is not None:
            if dns_result:
                logger.info(f"✅ {domain}: ALLOWED (DNS)")
                return False, "DNS Check"
            else:
                logger.warning(f"🚫 {domain}: BLOCKED (DNS)")
                return True, "DNS Check"
        
        # Method 2: Scraping (fallback)
        scrap_result = self.check_via_scraping(domain)
        if scrap_result is not None:
            if scrap_result:
                logger.info(f"✅ {domain}: ALLOWED (Scraping)")
                return False, "Scraping TrustPositif"
            else:
                logger.warning(f"🚫 {domain}: BLOCKED (Scraping)")
                return True, "Scraping TrustPositif"
        
        # Method 3: API (last resort)
        api_result = self.check_via_trustpositif_api(domain)
        if api_result is not None:
            if api_result:
                logger.info(f"✅ {domain}: ALLOWED (API)")
                return False, "TrustPositif API"
            else:
                logger.warning(f"🚫 {domain}: BLOCKED (API)")
                return True, "TrustPositif API"
        
        # Semua method gagal
        logger.warning(f"⚠️ {domain}: UNKNOWN (all methods failed)")
        return False, "UNKNOWN (no method available)"
    
    def check_domains_batch(self, domains: List[str]) -> List[Tuple[str, bool, str]]:
        """Cek multiple domains sekaligus"""
        results = []
        for domain in domains:
            is_blocked, method = self.check_domain(domain)
            results.append((domain, is_blocked, method))
            
            # Delay antar request untuk hindari rate limit
            time.sleep(1)
            
        return results

# ============ FUNGSI UTAMA ============
def baca_domain() -> List[str]:
    """Baca domain dari file domain.txt"""
    try:
        if not os.path.exists("domain.txt"):
            # Buat file contoh
            with open("domain.txt", "w") as f:
                f.write("# Daftar domain untuk dicek\n")
                f.write("# Satu domain per baris\n\n")
                f.write("# Contoh:\n")
                f.write("google.com\n")
                f.write("facebook.com\n")
                f.write("youtube.com\n")
                f.write("twitter.com\n")
                f.write("instagram.com\n")
            logger.info("✅ File domain.txt dibuat dengan contoh")
            return []
        
        domains = []
        with open("domain.txt", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Bersihkan domain
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
            f"🔧 **Methods:** DNS, Scraping, API\n\n"
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
                "Tidak ada domain yang terblokir."
            )
            
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode="Markdown"
            )
            logger.info(f"📤 Laporan aman: {total_domains} domain")
            
        else:
            # Format daftar domain terblokir
            domain_list = ""
            for i, (domain, method) in enumerate(blocked, 1):
                domain_list += f"{i}. 🚫 `{domain}` ({method})\n"
            
            message = (
                "🚨 *LAPORAN DOMAIN TERBLOKIR*\n\n"
                f"**{blocked_count} DOMAIN TERBLOKIR**\n\n"
                f"{domain_list}\n"
                f"📊 **Statistik:** {blocked_count}/{total_domains} domain terblokir\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                "_Sumber: TrustPositif Kominfo_"
            )
            
            # Kirim pesan (potong jika terlalu panjang)
            if len(message) > 4096:
                # Kirim per 20 domain
                chunks = [blocked[i:i+20] for i in range(0, len(blocked), 20)]
                for i, chunk in enumerate(chunks, 1):
                    chunk_msg = f"🚨 *LAPORAN (Bagian {i}/{len(chunks)})*\n\n"
                    for j, (domain, method) in enumerate(chunk, 1):
                        chunk_msg += f"{j}. 🚫 `{domain}` ({method})\n"
                    
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
        logger.info("🔄 MEMULAI PEMERIKSAAN")
        logger.info("=" * 60)
        
        # Baca domain
        domains = baca_domain()
        if not domains:
            logger.warning("⚠️ Tidak ada domain untuk dicek")
            return
        
        logger.info(f"📋 Jumlah domain: {len(domains)}")
        
        # Buat checker
        checker = NawalaChecker()
        
        # Cek semua domain
        start_time = time.time()
        results = checker.check_domains_batch(domains)
        elapsed_time = time.time() - start_time
        
        # Hitung statistik
        total = len(results)
        blocked = sum(1 for _, is_blocked, _ in results if is_blocked)
        unknown = sum(1 for _, is_blocked, _ in results if not is_blocked and 'UNKNOWN' in _[2])
        
        logger.info(f"⏱️ Waktu: {elapsed_time:.2f} detik")
        logger.info(f"📊 Hasil: {blocked}/{total} terblokir, {unknown} unknown")
        
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
    """Test koneksi ke TrustPositif"""
    try:
        logger.info("🔗 Testing koneksi ke trustpositif.komdigi.go.id...")
        
        response = requests.get(
            "https://trustpositif.komdigi.go.id/",
            timeout=10,
            proxies=proxies
        )
        
        if response.status_code == 200:
            logger.info("✅ Koneksi BERHASIL")
            return True
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
    print(f"🌐 Proxy: {PROXY_HOST}:{PROXY_PORT_HTTP}")
    print("=" * 60 + "\n")
    
    logger.info("Bot starting...")
    
    # Test koneksi
    if not await test_koneksi():
        logger.warning("⚠️ Koneksi bermasalah, bot tetap berjalan...")
    
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
    logger.info("📍 Press Ctrl+C to stop\n")
    
    # Jalankan schedule runner
    await schedule_runner()

if __name__ == "__main__":
    # Cek dependencies
    try:
        import schedule
        import requests
        import dns.resolver
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
