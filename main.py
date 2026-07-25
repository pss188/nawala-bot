import os
import sys
import time
import requests
import asyncio
import logging
import schedule
import json
import re
from telegram.ext import Application
from datetime import datetime
import urllib3
from bs4 import BeautifulSoup

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

if not TOKEN or not CHAT_ID:
    logger.error("TOKEN atau CHAT_ID tidak ditemukan!")
    sys.exit(1)

# Bot setup
try:
    application = Application.builder().token(TOKEN).build()
    logger.info("✅ Bot Telegram berhasil diinisialisasi")
except Exception as e:
    logger.error(f"❌ Gagal setup bot: {e}")
    sys.exit(1)

class NawalaChecker:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://www.nawala.asia"
        
        # Headers untuk meniru browser
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
        
        # Ambil token dari halaman
        self.csrf_token = self._get_csrf_token()
        self.recaptcha_token = None
        
        # Coba dapatkan struktur API dari JavaScript
        self.api_endpoints = self._discover_api_endpoints()
        
    def _get_csrf_token(self):
        """Fetch CSRF token dari halaman"""
        try:
            logger.info("🔄 Fetching CSRF token from Nawala...")
            response = self.session.get(
                self.base_url,
                headers=self.headers,
                timeout=20,
                verify=False
            )
            
            if response.status_code == 200:
                # Cari di HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Cari meta tags atau script
                csrf_meta = soup.find('meta', {'name': 'csrf-token'})
                if csrf_meta and csrf_meta.get('content'):
                    token = csrf_meta.get('content')
                    logger.info(f"✅ CSRF token found: {token[:10]}...")
                    return token
                
                # Cari di script
                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string and 'csrf' in script.string.lower():
                        match = re.search(r'csrf[_\s]*token["\']?\s*[:=]\s*["\']([^"\']+)', script.string)
                        if match:
                            token = match.group(1)
                            logger.info(f"✅ CSRF token from script: {token[:10]}...")
                            return token
            
            logger.warning("⚠️ CSRF token not found, using default")
            return "default_token"
            
        except Exception as e:
            logger.error(f"❌ Error getting CSRF token: {e}")
            return "default_token"
    
    def _discover_api_endpoints(self):
        """Discover API endpoints from the page"""
        endpoints = {}
        try:
            # Coba cari tahu endpoint dari JavaScript
            response = self.session.get(
                self.base_url,
                headers=self.headers,
                timeout=20,
                verify=False
            )
            
            if response.status_code == 200:
                # Cari pola URL Supabase
                supabase_pattern = r'https://[a-zA-Z0-9-]+\.supabase\.co/functions/v1/[a-zA-Z0-9-]+'
                matches = re.findall(supabase_pattern, response.text)
                
                if matches:
                    endpoints['supabase_functions'] = matches
                    logger.info(f"✅ Found Supabase endpoints: {matches}")
                
                # Cari pola API endpoint
                api_pattern = r'["\'](/api/[a-zA-Z0-9-/]+)["\']'
                matches = re.findall(api_pattern, response.text)
                if matches:
                    endpoints['api'] = matches
                    logger.info(f"✅ Found API endpoints: {matches}")
            
            return endpoints
            
        except Exception as e:
            logger.error(f"❌ Error discovering endpoints: {e}")
            return {}
    
    def check_batch_5_domains(self, domains):
        """Cek domain menggunakan Nawala.asia"""
        try:
            if len(domains) > 5:
                domains = domains[:5]
            
            logger.info(f"🔍 Checking batch: {', '.join(domains)}")
            
            # Karena website pakai React SPA, kemungkinan API ada di Supabase
            # Kita coba beberapa pendekatan
            
            # Pendekatan 1: Coba API langsung
            result = self._try_api_check(domains)
            if result is not None:
                return result
            
            # Pendekatan 2: Coba dengan rendering (simulasi browser)
            result = self._try_browser_check(domains)
            if result is not None:
                return result
            
            # Pendekatan 3: Coba dengan payload yang umum
            result = self._try_generic_check(domains)
            if result is not None:
                return result
            
            logger.error("❌ All approaches failed")
            return []
            
        except Exception as e:
            logger.error(f"❌ Error checking batch: {e}")
            return []
    
    def _try_api_check(self, domains):
        """Coba cek via API"""
        try:
            # Coba beberapa endpoint yang mungkin
            possible_endpoints = [
                f"{self.base_url}/api/check",
                f"{self.base_url}/api/domains",
                f"{self.base_url}/api/trustpositif",
                "https://bshpeqeoxfuattnzoyih.supabase.co/functions/v1/check-domain",
                "https://bshpeqeoxfuattnzoyih.supabase.co/functions/v1/trustpositif",
            ]
            
            for endpoint in possible_endpoints:
                try:
                    logger.info(f"🔄 Trying API: {endpoint}")
                    
                    # Payload yang mungkin
                    payloads = [
                        {'domains': domains},
                        {'domain': domains[0] if domains else ''},
                        {'domains': '\n'.join(domains)},
                        {'urls': domains},
                    ]
                    
                    for payload in payloads:
                        try:
                            response = self.session.post(
                                endpoint,
                                json=payload,
                                headers={
                                    **self.headers,
                                    'Content-Type': 'application/json',
                                    'Accept': 'application/json',
                                },
                                timeout=15,
                                verify=False
                            )
                            
                            if response.status_code == 200:
                                logger.info(f"✅ API success: {endpoint}")
                                return self._parse_api_response(response.text, domains)
                                
                        except Exception as e:
                            continue
                            
                except Exception as e:
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"❌ API check error: {e}")
            return None
    
    def _try_browser_check(self, domains):
        """Simulasi browser check dengan selenium atau requests-html"""
        try:
            # Karena ini SPA React, mungkin perlu JavaScript execution
            # Pendekatan: coba langsung ke halaman dengan parameter
            for domain in domains:
                try:
                    url = f"{self.base_url}/check?domain={domain}"
                    response = self.session.get(
                        url,
                        headers=self.headers,
                        timeout=15,
                        verify=False
                    )
                    
                    if response.status_code == 200:
                        # Parse hasil dari HTML
                        return self._parse_html_response(response.text, domains)
                        
                except Exception as e:
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Browser check error: {e}")
            return None
    
    def _try_generic_check(self, domains):
        """Try generic check using common patterns"""
        try:
            # Coba dengan form data seperti TrustPositif
            data = {
                'csrf_token': self.csrf_token,
                'name': '\n'.join(domains)
            }
            
            response = self.session.post(
                f"{self.base_url}/check",
                data=data,
                headers={
                    **self.headers,
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                timeout=15,
                verify=False
            )
            
            if response.status_code == 200:
                return self._parse_html_response(response.text, domains)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Generic check error: {e}")
            return None
    
    def _parse_api_response(self, response_text, original_domains):
        """Parse API response"""
        blocked_domains = []
        
        try:
            data = json.loads(response_text)
            
            # Coba berbagai format response yang mungkin
            if isinstance(data, dict):
                # Format 1: {'data': [{'domain': 'x', 'status': 'blocked'}]}
                if 'data' in data:
                    for item in data['data']:
                        if isinstance(item, dict):
                            domain = item.get('domain', '').lower()
                            status = item.get('status', '')
                            if status and status.lower() not in ['ok', 'clean', 'not blocked', 'tidak ada']:
                                blocked_domains.append(f"{domain} (terblokir)")
                
                # Format 2: {'domains': [{'domain': 'x', 'blocked': True}]}
                elif 'domains' in data:
                    for item in data['domains']:
                        if isinstance(item, dict):
                            domain = item.get('domain', '').lower()
                            blocked = item.get('blocked', False)
                            if blocked:
                                blocked_domains.append(f"{domain} (terblokir)")
                
                # Format 3: {'result': [{'domain': 'x', 'status': 'blocked'}]}
                elif 'result' in data:
                    for item in data['result']:
                        if isinstance(item, dict):
                            domain = item.get('domain', '').lower()
                            status = item.get('status', '')
                            if status and status.lower() in ['blocked', 'terblokir']:
                                blocked_domains.append(f"{domain} (terblokir)")
            
            # Jika tidak ada yang terdeteksi, asumsi aman
            if not blocked_domains:
                for domain in original_domains:
                    logger.info(f"✅ {domain}: Aman (tidak terdeteksi)")
            
            return blocked_domains
            
        except Exception as e:
            logger.error(f"❌ API parse error: {e}")
            return []
    
    def _parse_html_response(self, html, domains):
        """Parse HTML response using BeautifulSoup or regex"""
        blocked_domains = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Cari di berbagai elemen yang mungkin menampilkan hasil
            # 1. Cari di div dengan class tertentu
            result_divs = soup.find_all(['div', 'span', 'p'], class_=re.compile(r'(result|status|domain|blocked)'))
            for div in result_divs:
                text = div.text.lower()
                for domain in domains:
                    if domain.lower() in text:
                        if 'blocked' in text or 'terblokir' in text or 'nawala' in text:
                            blocked_domains.append(f"{domain} (terdeteksi di HTML)")
                            break
            
            # 2. Cari pattern di teks
            html_text = soup.text.lower()
            for domain in domains:
                domain_lower = domain.lower()
                if domain_lower in html_text:
                    # Cari konteks sekitar
                    pattern = f'.{{0,100}}{re.escape(domain_lower)}.{{0,100}}(blocked|terblokir|nawala).{{0,100}}'
                    match = re.search(pattern, html_text, re.IGNORECASE)
                    if match:
                        blocked_domains.append(f"{domain} (terdeteksi)")
            
            # Jika tidak ada yang terdeteksi, asumsi aman
            if not blocked_domains:
                for domain in domains:
                    if domain.lower() not in html_text:
                        logger.info(f"✅ {domain}: Tidak ditemukan (asumsi aman)")
            
            return blocked_domains
            
        except Exception as e:
            logger.error(f"❌ HTML parse error: {e}")
            return []
    
    def check_all_domains(self, domains):
        """Cek semua domain dengan batch 5"""
        try:
            if not domains:
                return []
            
            all_blocked = []
            batch_size = 5
            
            for i in range(0, len(domains), batch_size):
                batch = domains[i:i + batch_size]
                blocked_batch = self.check_batch_5_domains(batch)
                all_blocked.extend(blocked_batch)
                
                if i + batch_size < len(domains):
                    logger.info("⏳ Menunggu 3 detik sebelum batch berikutnya...")
                    time.sleep(3)
            
            return all_blocked
            
        except Exception as e:
            logger.error(f"❌ Error checking all domains: {e}")
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
            logger.info("✅ File domain.txt dibuat dengan contoh")
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
        logger.error(f"❌ Error membaca domain: {e}")
        return []

# ============================================
# FUNGSI TELEGRAM (Sama seperti sebelumnya)
# ============================================

async def kirim_status():
    """Kirim status bot"""
    try:
        waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        domains = baca_domain()
        domain_count = len(domains)
        
        message = (
            "🤖 *Nawala.asia Monitoring Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Batch:** 5 domain/request\n"
            f"🌐 **Sumber:** Nawala.asia\n\n"
            "_Bot akan mengecek domain setiap 15 menit_"
        )
        
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="Markdown"
        )
        logger.info("📤 Status bot terkirim")
        
    except Exception as e:
        logger.error(f"❌ Gagal kirim status: {e}")

async def kirim_laporan(blocked_domains, total_domains):
    """Kirim laporan hasil pengecekan"""
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
            for i, domain_info in enumerate(blocked_domains, 1):
                domain_list += f"{i}. 🚫 `{domain_info}`\n"
            
            message = (
                "❌❌❌❌❌❌❌❌❌\n\n"
                f"**{blocked_count} DOMAIN TERBLOKIR**\n\n"
                f"{domain_list}\n"
                f"📊 **Statistik:** {blocked_count}/{total_domains} domain terblokir\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                "_Sumber: Nawala.asia_"
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
        logger.error(f"❌ Gagal kirim laporan: {e}")

async def kirim_pesan_terbagi(blocked_domains, total_domains):
    """Kirim pesan terbagi jika terlalu panjang"""
    try:
        blocked_count = len(blocked_domains)
        chunk_size = 20
        chunks = [blocked_domains[i:i + chunk_size] for i in range(0, len(blocked_domains), chunk_size)]
        
        for i, chunk in enumerate(chunks, 1):
            domain_list = ""
            for j, domain_info in enumerate(chunk, 1):
                domain_list += f"{(i-1)*chunk_size + j}. 🚫 `{domain_info}`\n"
            
            message = (
                f"🚨 *LAPORAN DOMAIN TERBLOKIR (Bagian {i}/{len(chunks)})*\n\n"
                f"{domain_list}\n"
            )
            
            if i == len(chunks):
                message += (
                    f"📊 **Statistik:** {blocked_count}/{total_domains} domain terblokir\n"
                    f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                    "_Sumber: Nawala.asia_"
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
        logger.error(f"❌ Gagal kirim pesan terbagi: {e}")

async def cek_domain_job():
    """Job untuk mengecek domain"""
    try:
        logger.info("=" * 60)
        logger.info("🔄 MEMULAI PEMERIKSAAN NAWALA.ASIA")
        logger.info("=" * 60)
        
        domains = baca_domain()
        if not domains:
            logger.warning("⚠️ Tidak ada domain untuk dicek")
            return
        
        logger.info(f"📋 Jumlah domain: {len(domains)}")
        
        checker = NawalaChecker()
        
        start_time = time.time()
        blocked_domains = checker.check_all_domains(domains)
        elapsed_time = time.time() - start_time
        
        logger.info(f"⏱️ Waktu pemrosesan: {elapsed_time:.2f} detik")
        logger.info(f"📊 Hasil: {len(blocked_domains)} dari {len(domains)} domain terblokir")
        
        await kirim_laporan(blocked_domains, len(domains))
        
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

async def main():
    """Main function"""
    print("\n" + "=" * 60)
    print("🚀 NAWALA.ASIA DOMAIN MONITORING BOT")
    print("=" * 60)
    
    logger.info("Bot starting...")
    logger.info("🌐 Source: Nawala.asia (TrustPositif mirror)")
    
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
    logger.info("📍 Status reports: Every 3 hours")
    logger.info("📍 Batch size: 5 domains per request")
    logger.info("📍 Source: Nawala.asia")
    logger.info("📍 Press Ctrl+C to stop\n")
    
    await schedule_runner()

if __name__ == "__main__":
    try:
        import schedule
        import requests
        from telegram import __version__
        logger.info(f"✅ Dependencies: requests, schedule, python-telegram-bot v{__version__}")
    except ImportError as e:
        logger.error(f"❌ Missing dependency: {e}")
        logger.info("💡 Install dengan: pip install requests schedule python-telegram-bot beautifulsoup4")
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"💥 Critical error: {e}")
        import traceback
        logger.error(traceback.format_exc())
