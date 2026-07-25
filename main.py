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

class TrustPositifIDChecker:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://trustpositif.id"
        self.checker_url = f"{self.base_url}/checker"
        
        # Headers untuk meniru browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Origin': self.base_url,
            'Referer': f'{self.checker_url}/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        }
    
    def check_domains_batch(self, domains):
        """Cek multiple domain dalam satu request (max 100)"""
        try:
            if not domains:
                return []
            
            # Batasi maksimal 100 domain
            if len(domains) > 100:
                logger.warning(f"⚠️ Maksimal 100 domain, hanya 100 pertama yang dicek")
                domains = domains[:100]
            
            logger.info(f"🔍 Checking {len(domains)} domains in batch...")
            
            # Format domains: satu per baris atau dipisahkan koma
            domains_text = "\n".join(domains)
            domains_comma = ", ".join(domains)
            
            # Coba berbagai pendekatan
            
            # Pendekatan 1: POST dengan JSON
            result = self._check_via_json(domains, domains_text)
            if result is not None:
                return result
            
            # Pendekatan 2: POST dengan form data
            result = self._check_via_form(domains, domains_text)
            if result is not None:
                return result
            
            # Pendekatan 3: GET dengan query parameter
            result = self._check_via_get(domains)
            if result is not None:
                return result
            
            logger.error("❌ Semua pendekatan gagal")
            return []
            
        except Exception as e:
            logger.error(f"❌ Error checking batch: {e}")
            return []
    
    def _check_via_json(self, domains, domains_text):
        """Coba dengan JSON payload"""
        try:
            # Endpoint yang mungkin
            endpoints = [
                f"{self.checker_url}/api/check",
                f"{self.checker_url}/api/domains",
                f"{self.base_url}/api/check",
                f"{self.base_url}/api/nawala",
                f"{self.checker_url}/check",
            ]
            
            # Berbagai format payload
            payloads = [
                {'domains': domains},
                {'domains': domains_text},
                {'domain': domains},
                {'domains': domains, 'format': 'json'},
                {'data': domains},
                {'list': domains},
                {'urls': domains},
            ]
            
            for endpoint in endpoints:
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
                            timeout=30,
                            verify=False
                        )
                        
                        if response.status_code == 200:
                            try:
                                data = response.json()
                                logger.debug(f"API Response: {json.dumps(data, indent=2)[:500]}")
                                return self._parse_api_response(data, domains)
                            except:
                                # Jika bukan JSON, coba parse HTML
                                return self._parse_html_response(response.text, domains)
                                
                    except Exception as e:
                        continue
            
            return None
            
        except Exception as e:
            logger.error(f"❌ JSON error: {e}")
            return None
    
    def _check_via_form(self, domains, domains_text):
        """Coba dengan form data"""
        try:
            form_data = {
                'domains': domains_text,
                'domain': domains_text,
                'urls': domains_text,
                'q': domains_text,
                'action': 'check',
                'submit': 'Cek',
            }
            
            response = self.session.post(
                self.checker_url,
                data=form_data,
                headers={
                    **self.headers,
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                timeout=30,
                verify=False,
                allow_redirects=True
            )
            
            if response.status_code == 200:
                return self._parse_html_response(response.text, domains)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Form error: {e}")
            return None
    
    def _check_via_get(self, domains):
        """Coba dengan GET request"""
        try:
            domains_param = ",".join(domains)
            params = {
                'domains': domains_param,
                'q': domains_param,
            }
            
            response = self.session.get(
                self.checker_url,
                params=params,
                headers=self.headers,
                timeout=30,
                verify=False
            )
            
            if response.status_code == 200:
                return self._parse_html_response(response.text, domains)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ GET error: {e}")
            return None
    
    def _parse_api_response(self, data, domains):
        """Parse JSON response dari API"""
        blocked_domains = []
        
        try:
            if isinstance(data, dict):
                # Cari data di berbagai field
                data_fields = ['data', 'result', 'results', 'domains', 'list', 'items']
                
                for field in data_fields:
                    if field in data:
                        items = data[field]
                        
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict):
                                    domain = self._extract_domain(item)
                                    status = self._extract_status(item)
                                    blocked = item.get('blocked', False) or item.get('is_blocked', False)
                                    
                                    if domain:
                                        if blocked or status.lower() in ['blocked', 'terblokir', 'nawala']:
                                            blocked_domains.append(domain)
                                            logger.warning(f"🚫 {domain}: TERBLOKIR")
                                        elif status.lower() in ['not blocked', 'not_blocked', 'aman', 'ok', 'clean']:
                                            logger.info(f"✅ {domain}: AMAN")
                                        
                        elif isinstance(items, dict):
                            for domain, status in items.items():
                                if isinstance(status, dict):
                                    blocked = status.get('blocked', False) or status.get('is_blocked', False)
                                    status_text = status.get('status', '')
                                    if blocked or str(status_text).lower() in ['blocked', 'terblokir']:
                                        blocked_domains.append(domain)
                                        logger.warning(f"🚫 {domain}: TERBLOKIR")
                                elif str(status).lower() in ['blocked', 'terblokir', 'true', '1']:
                                    blocked_domains.append(domain)
                                    logger.warning(f"🚫 {domain}: TERBLOKIR")
            
            # Jika tidak ada yang terdeteksi sebagai blokir, semua aman
            if not blocked_domains:
                for domain in domains:
                    if domain not in blocked_domains:
                        logger.info(f"✅ {domain}: AMAN")
            
            return blocked_domains
            
        except Exception as e:
            logger.error(f"❌ API parse error: {e}")
            return []
    
    def _parse_html_response(self, html, domains):
        """Parse HTML response"""
        blocked_domains = []
        
        try:
            html_lower = html.lower()
            
            # Cari status untuk setiap domain
            for domain in domains:
                domain_lower = domain.lower()
                
                if domain_lower not in html_lower:
                    logger.info(f"✅ {domain}: Domain tidak ditemukan (asumsi aman)")
                    continue
                
                # Cari konteks
                domain_index = html_lower.find(domain_lower)
                start = max(0, domain_index - 300)
                end = min(len(html_lower), domain_index + 300)
                context = html_lower[start:end]
                
                # Indikasi terblokir
                blocked_patterns = [
                    r'terblokir',
                    r'diblokir',
                    r'blocked',
                    r'nawala',
                    r'status["\']?\s*[:=]\s*["\']?blocked',
                    r'class=["\'][^"\']*(blocked|red|danger)[^"\']*["\']',
                    r'bg-red',
                    r'text-red',
                    r'border-red',
                ]
                
                # Indikasi aman
                safe_patterns = [
                    r'aman',
                    r'safe',
                    r'not blocked',
                    r'not_blocked',
                    r'clean',
                    r'ok',
                    r'status["\']?\s*[:=]\s*["\']?(ok|clean|aman|not blocked)',
                    r'class=["\'][^"\']*(success|green|safe)[^"\']*["\']',
                    r'bg-green',
                    r'text-green',
                    r'border-green',
                ]
                
                is_blocked = False
                is_safe = False
                
                # Cek blokir
                for pattern in blocked_patterns:
                    if re.search(pattern, context, re.IGNORECASE):
                        is_blocked = True
                        break
                
                # Cek aman
                for pattern in safe_patterns:
                    if re.search(pattern, context, re.IGNORECASE):
                        is_safe = True
                        break
                
                if is_blocked and not is_safe:
                    blocked_domains.append(domain)
                    logger.warning(f"🚫 {domain}: TERBLOKIR")
                elif is_safe:
                    logger.info(f"✅ {domain}: AMAN")
                else:
                    # Default: aman
                    logger.info(f"✅ {domain}: Tidak terdeteksi blokir (asumsi aman)")
            
            return blocked_domains
            
        except Exception as e:
            logger.error(f"❌ HTML parse error: {e}")
            return []
    
    def _extract_domain(self, item):
        """Extract domain dari berbagai format"""
        for key in ['domain', 'name', 'url', 'host', 'target', 'item', 'id']:
            if key in item:
                return str(item[key]).strip().lower()
        return ''
    
    def _extract_status(self, item):
        """Extract status dari berbagai format"""
        for key in ['status', 'result', 'state', 'blocked_status']:
            if key in item:
                return str(item[key]).strip().lower()
        return ''
    
    def check_all_domains(self, domains):
        """Cek semua domain dengan batch (max 100 per request)"""
        try:
            if not domains:
                return []
            
            all_blocked = []
            total = len(domains)
            
            # Proses dalam batch maksimal 100
            batch_size = 100
            
            for i in range(0, total, batch_size):
                batch = domains[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (total + batch_size - 1) // batch_size
                
                logger.info(f"📦 Batch {batch_num}/{total_batches}: {len(batch)} domains")
                logger.info("-" * 40)
                
                # Cek batch
                blocked_batch = self.check_domains_batch(batch)
                all_blocked.extend(blocked_batch)
                
                # Delay antar batch (rate limit: 1000 domain / 10 menit)
                if i + batch_size < total:
                    delay = 10  # 10 detik antar batch untuk aman
                    logger.info(f"⏳ Menunggu {delay} detik sebelum batch berikutnya...")
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
        
        message = (
            "🤖 *TrustPositif.id Monitoring Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Mode:** Batch (max 100 domain/request)\n"
            f"⏱️ **Rate Limit:** 1000 domain/10 menit\n"
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
        logger.error(f"❌ Gagal kirim pesan terbagi: {e}")

async def cek_domain_job():
    """Job untuk mengecek domain dengan batch"""
    try:
        logger.info("=" * 60)
        logger.info("🔄 MEMULAI PEMERIKSAAN TRUSTPOSITIF.ID/CHECKER")
        logger.info("🔄 Mode: Batch (max 100 domain/request)")
        logger.info("🔄 Rate Limit: 1000 domain/10 menit")
        logger.info("=" * 60)
        
        domains = baca_domain()
        if not domains:
            logger.warning("⚠️ Tidak ada domain untuk dicek")
            return
        
        logger.info(f"📋 Jumlah domain: {len(domains)}")
        
        checker = TrustPositifIDChecker()
        
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
    print("🚀 TRUSTPOSITIF.ID/CHECKER DOMAIN MONITORING BOT")
    print("📌 Mode: Batch (max 100 domain/request)")
    print("📌 Rate Limit: 1000 domain/10 menit")
    print("=" * 60)
    
    logger.info("Bot starting...")
    logger.info("🌐 Source: trustpositif.id/checker")
    logger.info("📌 Mode: Batch (max 100 domain per request)")
    logger.info("⏱️ Rate Limit: 1000 domain/10 menit")
    
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
    logger.info("📍 Delay antar batch: 10 detik")
    logger.info("📍 Source: trustpositif.id/checker")
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
