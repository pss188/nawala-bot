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
        self.base_url = "https://nawala.online"
        self.api_url = "https://nawala.online/api/check"  # Endpoint API yang mungkin
        
        # Headers untuk meniru browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Origin': self.base_url,
            'Referer': f'{self.base_url}/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        }
        
        # Track rate limit
        self.last_request_time = 0
        self.request_count = 0
        self.rate_limit_window = 300  # 5 menit
        self.max_requests_per_window = 10
    
    def _check_rate_limit(self):
        """Cek dan tunggu jika melewati rate limit"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        # Reset counter jika sudah melewati window
        if time_since_last > self.rate_limit_window:
            self.request_count = 0
            self.last_request_time = current_time
        
        # Jika sudah mencapai limit, tunggu
        if self.request_count >= self.max_requests_per_window:
            wait_time = self.rate_limit_window - time_since_last + 5
            logger.info(f"⏳ Rate limit tercapai, menunggu {wait_time:.0f} detik...")
            time.sleep(wait_time)
            self.request_count = 0
            self.last_request_time = time.time()
    
    def check_single_domain(self, domain):
        """Cek 1 domain secara individual"""
        try:
            logger.info(f"🔍 Checking domain: {domain}")
            
            # Cek rate limit
            self._check_rate_limit()
            
            # Coba berbagai pendekatan
            
            # Pendekatan 1: API JSON
            result = self._check_via_api(domain)
            if result is not None:
                self.request_count += 1
                self.last_request_time = time.time()
                return result
            
            # Pendekatan 2: Form submit
            result = self._check_via_form(domain)
            if result is not None:
                self.request_count += 1
                self.last_request_time = time.time()
                return result
            
            # Pendekatan 3: GET dengan query
            result = self._check_via_get(domain)
            if result is not None:
                self.request_count += 1
                self.last_request_time = time.time()
                return result
            
            logger.warning(f"⚠️ Semua pendekatan gagal untuk {domain}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error checking domain {domain}: {e}")
            return None
    
    def _check_via_api(self, domain):
        """Coba dengan API JSON"""
        try:
            # Payload yang mungkin
            payloads = [
                {'domain': domain},
                {'domains': [domain]},
                {'url': domain},
                {'q': domain},
                {'check': domain},
            ]
            
            for payload in payloads:
                try:
                    response = self.session.post(
                        self.api_url,
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
                        try:
                            data = response.json()
                            logger.debug(f"API Response: {json.dumps(data, indent=2)}")
                            return self._parse_api_response(data, domain)
                        except:
                            # Jika bukan JSON, coba parse HTML
                            return self._parse_html_response(response.text, domain)
                            
                except Exception as e:
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"❌ API error: {e}")
            return None
    
    def _check_via_form(self, domain):
        """Coba dengan form submit"""
        try:
            form_data = {
                'domain': domain,
                'domains': domain,
                'url': domain,
                'q': domain,
            }
            
            response = self.session.post(
                self.base_url,
                data=form_data,
                headers={
                    **self.headers,
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                timeout=15,
                verify=False
            )
            
            if response.status_code == 200:
                return self._parse_html_response(response.text, domain)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Form error: {e}")
            return None
    
    def _check_via_get(self, domain):
        """Coba dengan GET request"""
        try:
            params = {'domain': domain, 'q': domain}
            
            response = self.session.get(
                self.base_url,
                params=params,
                headers=self.headers,
                timeout=15,
                verify=False
            )
            
            if response.status_code == 200:
                return self._parse_html_response(response.text, domain)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ GET error: {e}")
            return None
    
    def _parse_api_response(self, data, domain):
        """Parse JSON response dari API"""
        try:
            domain_lower = domain.lower()
            
            if isinstance(data, dict):
                # Format 1: {'status': 'blocked' atau 'not blocked', 'domain': 'example.com'}
                if 'status' in data and 'domain' in data:
                    if data['domain'].lower() == domain_lower:
                        status = str(data['status']).lower()
                        if status in ['blocked', 'terblokir', 'true']:
                            logger.warning(f"🚫 {domain}: TERBLOKIR")
                            return True
                        elif status in ['not blocked', 'not_blocked', 'ok', 'aman', 'false']:
                            logger.info(f"✅ {domain}: AMAN")
                            return False
                
                # Format 2: {'result': {'domain': 'example.com', 'blocked': true/false}}
                if 'result' in data and isinstance(data['result'], dict):
                    result = data['result']
                    if result.get('domain', '').lower() == domain_lower:
                        blocked = result.get('blocked', False)
                        status = str(result.get('status', '')).lower()
                        
                        if blocked or status in ['blocked', 'terblokir']:
                            logger.warning(f"🚫 {domain}: TERBLOKIR")
                            return True
                        else:
                            logger.info(f"✅ {domain}: AMAN")
                            return False
                
                # Format 3: {'data': [{'domain': 'example.com', 'status': 'blocked'}]}
                if 'data' in data and isinstance(data['data'], list):
                    for item in data['data']:
                        if isinstance(item, dict):
                            if item.get('domain', '').lower() == domain_lower:
                                status = str(item.get('status', '')).lower()
                                blocked = item.get('blocked', False)
                                
                                if blocked or status in ['blocked', 'terblokir']:
                                    logger.warning(f"🚫 {domain}: TERBLOKIR")
                                    return True
                                else:
                                    logger.info(f"✅ {domain}: AMAN")
                                    return False
            
            # Cek di JSON string
            json_str = json.dumps(data).lower()
            if domain_lower in json_str:
                if 'blocked' in json_str or 'terblokir' in json_str:
                    # Cek konteks
                    domain_index = json_str.find(domain_lower)
                    context = json_str[domain_index:domain_index+200]
                    if 'blocked' in context or 'terblokir' in context:
                        logger.warning(f"🚫 {domain}: TERBLOKIR (dari JSON string)")
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ API parse error: {e}")
            return None
    
    def _parse_html_response(self, html, domain):
        """Parse HTML response"""
        try:
            html_lower = html.lower()
            domain_lower = domain.lower()
            
            # Cari domain di HTML
            if domain_lower not in html_lower:
                logger.info(f"✅ {domain}: Domain tidak ditemukan (asumsi aman)")
                return False
            
            # Cari status
            status_patterns = [
                # Pattern untuk "Not Blocked" atau "Blocked"
                r'status["\']?\s*[:=]\s*["\']?(not blocked|blocked|terblokir|aman)["\']?',
                r'<span[^>]*class=["\'][^"\']*(status|result)[^"\']*["\'][^>]*>(.*?)</span>',
                r'<div[^>]*class=["\'][^"\']*(status|result)[^"\']*["\'][^>]*>(.*?)</div>',
                r'<p[^>]*>(.*?blocked.*?)</p>',
                r'<p[^>]*>(.*?not blocked.*?)</p>',
                r'<p[^>]*>(.*?terblokir.*?)</p>',
                r'<p[^>]*>(.*?aman.*?)</p>',
            ]
            
            # Cari di konteks
            domain_index = html_lower.find(domain_lower)
            if domain_index != -1:
                start = max(0, domain_index - 300)
                end = min(len(html_lower), domain_index + 300)
                context = html_lower[start:end]
                
                # Cek indikasi blokir
                blocked_keywords = ['blocked', 'terblokir', 'diblokir']
                safe_keywords = ['not blocked', 'not_blocked', 'aman', 'ok', 'clean']
                
                for keyword in blocked_keywords:
                    if keyword in context:
                        logger.warning(f"🚫 {domain}: TERBLOKIR")
                        return True
                
                for keyword in safe_keywords:
                    if keyword in context:
                        logger.info(f"✅ {domain}: AMAN")
                        return False
            
            # Default: aman
            logger.info(f"✅ {domain}: Tidak terdeteksi blokir (asumsi aman)")
            return False
            
        except Exception as e:
            logger.error(f"❌ HTML parse error: {e}")
            return None
    
    def check_all_domains(self, domains):
        """Cek semua domain satu per satu dengan rate limit"""
        try:
            if not domains:
                return []
            
            # Batasi maksimal 10 domain per batch (sesuai rate limit)
            if len(domains) > 10:
                logger.warning(f"⚠️ Maksimal 10 domain per request, hanya 10 pertama yang dicek")
                domains = domains[:10]
            
            all_blocked = []
            total = len(domains)
            
            for i, domain in enumerate(domains, 1):
                logger.info(f"📌 [{i}/{total}] Memeriksa: {domain}")
                logger.info("-" * 40)
                
                # Cek domain
                is_blocked = self.check_single_domain(domain)
                
                if is_blocked is True:
                    all_blocked.append(domain)
                    logger.warning(f"🚫 {domain}: TERBLOKIR")
                elif is_blocked is False:
                    logger.info(f"✅ {domain}: AMAN")
                else:
                    logger.warning(f"⚠️ {domain}: TIDAK DIKETAHUI - coba lagi")
                    time.sleep(2)
                    is_blocked = self.check_single_domain(domain)
                    if is_blocked is True:
                        all_blocked.append(domain)
                        logger.warning(f"🚫 {domain}: TERBLOKIR (setelah retry)")
                    else:
                        logger.info(f"✅ {domain}: AMAN (setelah retry)")
                
                logger.info("-" * 40)
                
                # Delay antar domain (rate limit: 10 per 5 menit)
                if i < total:
                    delay = 30  # 30 detik antar domain untuk aman
                    logger.info(f"⏳ Menunggu {delay} detik (rate limit)...")
                    time.sleep(delay)
            
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
# FUNGSI TELEGRAM
# ============================================

async def kirim_status():
    """Kirim status bot"""
    try:
        waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        domains = baca_domain()
        domain_count = len(domains)
        
        # Batasi 10 domain
        if domain_count > 10:
            domain_count = 10
        
        message = (
            "🤖 *Nawala.online Monitoring Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Mode:** 1 domain/request\n"
            f"⏱️ **Rate Limit:** 10 domain/5 menit\n"
            f"🌐 **Sumber:** nawala.online\n\n"
            "_Bot akan mengecek domain satu per satu setiap 15 menit_"
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
            for i, domain in enumerate(blocked_domains, 1):
                domain_list += f"{i}. 🚫 `{domain}`\n"
            
            message = (
                "❌❌❌❌❌❌❌❌❌\n\n"
                f"**{blocked_count} DOMAIN TERBLOKIR**\n\n"
                f"{domain_list}\n"
                f"📊 **Statistik:** {blocked_count}/{total_domains} domain terblokir\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                "_Sumber: nawala.online_"
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
                    "_Sumber: nawala.online_"
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
    """Job untuk mengecek domain satu per satu"""
    try:
        logger.info("=" * 60)
        logger.info("🔄 MEMULAI PEMERIKSAAN NAWALA.ONLINE")
        logger.info("🔄 Mode: 1 domain per request")
        logger.info("🔄 Rate Limit: 10 domain/5 menit")
        logger.info("=" * 60)
        
        domains = baca_domain()
        if not domains:
            logger.warning("⚠️ Tidak ada domain untuk dicek")
            return
        
        # Batasi 10 domain
        if len(domains) > 10:
            logger.warning(f"⚠️ Maksimal 10 domain, hanya 10 pertama yang dicek")
            domains = domains[:10]
        
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
    print("🚀 NAWALA.ONLINE DOMAIN MONITORING BOT")
    print("📌 Mode: 1 domain per request")
    print("📌 Rate Limit: 10 domain/5 menit")
    print("=" * 60)
    
    logger.info("Bot starting...")
    logger.info("🌐 Source: nawala.online")
    logger.info("📌 Mode: 1 domain per request")
    logger.info("⏱️ Rate Limit: 10 domain/5 menit")
    
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
    logger.info("📍 Mode: 1 domain per request")
    logger.info("📍 Delay antar domain: 30 detik (rate limit)")
    logger.info("📍 Max domain per check: 10")
    logger.info("📍 Source: nawala.online")
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
        logger.info("💡 Install dengan: pip install requests schedule python-telegram-bot")
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"💥 Critical error: {e}")
        import traceback
        logger.error(traceback.format_exc())
