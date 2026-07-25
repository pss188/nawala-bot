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

class TrustPositifChecker:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://trustpositif.infonawala.com"
        
        # Headers untuk meniru browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Origin': self.base_url,
            'Referer': f'{self.base_url}/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        }
    
    def check_single_domain(self, domain):
        """Cek 1 domain secara individual"""
        try:
            logger.info(f"🔍 Checking domain: {domain}")
            
            # Coba berbagai pendekatan untuk 1 domain
            
            # Pendekatan 1: POST ke API Next.js dengan JSON
            result = self._check_via_nextjs_api(domain)
            if result is not None:
                return result
            
            # Pendekatan 2: POST dengan form data
            result = self._check_via_form(domain)
            if result is not None:
                return result
            
            # Pendekatan 3: GET dengan query parameter
            result = self._check_via_get(domain)
            if result is not None:
                return result
            
            logger.warning(f"⚠️ Semua pendekatan gagal untuk {domain}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error checking domain {domain}: {e}")
            return None
    
    def _check_via_nextjs_api(self, domain):
        """Coba dengan Next.js API routes"""
        try:
            # Next.js API routes yang umum
            endpoints = [
                f"{self.base_url}/api/check",
                f"{self.base_url}/api/domains",
                f"{self.base_url}/api/nawala",
                f"{self.base_url}/api/trustpositif",
                f"{self.base_url}/api/cek",
                f"{self.base_url}/api/scan",
            ]
            
            # Berbagai payload format
            payloads = [
                {'domain': domain},
                {'domains': [domain]},
                {'url': domain},
                {'q': domain},
                {'query': domain},
                {'data': {'domain': domain}},
                {'domains': domain},
            ]
            
            for endpoint in endpoints:
                for payload in payloads:
                    try:
                        # Coba dengan JSON
                        response = self.session.post(
                            endpoint,
                            json=payload,
                            headers={
                                **self.headers,
                                'Content-Type': 'application/json',
                                'Accept': 'application/json',
                            },
                            timeout=20,
                            verify=False
                        )
                        
                        if response.status_code == 200:
                            try:
                                data = response.json()
                                is_blocked = self._parse_json_response(data, domain)
                                if is_blocked is not None:
                                    logger.info(f"✅ API success: {endpoint}")
                                    return is_blocked
                            except:
                                # Jika bukan JSON, coba parse HTML
                                is_blocked = self._parse_html_response(response.text, domain)
                                if is_blocked is not None:
                                    logger.info(f"✅ API returned HTML: {endpoint}")
                                    return is_blocked
                                    
                    except Exception as e:
                        continue
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Next.js API error: {e}")
            return None
    
    def _check_via_form(self, domain):
        """Coba dengan form data (Next.js form action)"""
        try:
            # Next.js form action biasanya ke root atau /api/check
            endpoints = [
                self.base_url,
                f"{self.base_url}/check",
                f"{self.base_url}/cek",
            ]
            
            payloads = [
                {'domain': domain},
                {'domains': domain},
                {'url': domain},
                {'q': domain},
                {'check': domain},
                {'query': domain},
                {'action': 'check', 'domain': domain},
            ]
            
            for endpoint in endpoints:
                for payload in payloads:
                    try:
                        response = self.session.post(
                            endpoint,
                            data=payload,
                            headers={
                                **self.headers,
                                'Content-Type': 'application/x-www-form-urlencoded',
                            },
                            timeout=20,
                            verify=False
                        )
                        
                        if response.status_code == 200:
                            is_blocked = self._parse_html_response(response.text, domain)
                            if is_blocked is not None:
                                logger.info(f"✅ Form success: {endpoint}")
                                return is_blocked
                                
                    except Exception as e:
                        continue
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Form error: {e}")
            return None
    
    def _check_via_get(self, domain):
        """Coba dengan GET request"""
        try:
            params_list = [
                {'domain': domain},
                {'q': domain},
                {'url': domain},
                {'check': domain},
                {'cek': domain},
            ]
            
            for params in params_list:
                try:
                    response = self.session.get(
                        self.base_url,
                        params=params,
                        headers=self.headers,
                        timeout=20,
                        verify=False
                    )
                    
                    if response.status_code == 200:
                        is_blocked = self._parse_html_response(response.text, domain)
                        if is_blocked is not None:
                            logger.info(f"✅ GET success: {params}")
                            return is_blocked
                            
                except Exception as e:
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"❌ GET error: {e}")
            return None
    
    def _parse_json_response(self, data, domain):
        """Parse JSON response dari Next.js API - return True if blocked, False if safe, None if unknown"""
        try:
            domain_lower = domain.lower()
            
            if isinstance(data, dict):
                # Cari di berbagai field yang umum di Next.js API
                for key in ['data', 'result', 'results', 'domains', 'status', 'blocked', 'response']:
                    if key in data:
                        if isinstance(data[key], list):
                            for item in data[key]:
                                if isinstance(item, dict):
                                    item_domain = self._extract_domain(item)
                                    if item_domain == domain_lower:
                                        status = str(item.get('status', '')).lower()
                                        blocked = item.get('blocked', False) or item.get('is_blocked', False)
                                        
                                        if blocked or status in ['blocked', 'terblokir', 'true', '1']:
                                            return True
                                        elif status in ['clean', 'ok', 'allowed', 'aman', 'false', '0']:
                                            return False
                                        
                        elif isinstance(data[key], dict):
                            for d, value in data[key].items():
                                if d.lower() == domain_lower:
                                    if isinstance(value, dict):
                                        status = str(value.get('status', '')).lower()
                                        blocked = value.get('blocked', False)
                                        if blocked or status in ['blocked', 'terblokir']:
                                            return True
                                    elif str(value).lower() in ['blocked', 'terblokir', 'true', '1']:
                                        return True
                                    elif str(value).lower() in ['clean', 'ok', 'allowed', 'false', '0']:
                                        return False
                
                # Cek field langsung
                if 'status' in data and 'domain' in data:
                    if data['domain'].lower() == domain_lower:
                        status = str(data['status']).lower()
                        if status in ['blocked', 'terblokir']:
                            return True
                        elif status in ['clean', 'ok', 'allowed', 'aman']:
                            return False
            
            # Cek di seluruh JSON string
            json_str = json.dumps(data).lower()
            if domain_lower in json_str:
                if 'blocked' in json_str or 'terblokir' in json_str:
                    # Cek apakah ada indikasi aman juga
                    if 'allowed' in json_str or 'aman' in json_str:
                        # Jika ada keduanya, cek konteks
                        domain_index = json_str.find(domain_lower)
                        context = json_str[domain_index:domain_index+200]
                        if 'blocked' in context or 'terblokir' in context:
                            return True
                        return False
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ JSON parse error: {e}")
            return None
    
    def _parse_html_response(self, html, domain):
        """Parse HTML response - return True if blocked, False if safe, None if unknown"""
        try:
            html_lower = html.lower()
            domain_lower = domain.lower()
            domain_escaped = re.escape(domain_lower)
            
            # Cari domain dalam HTML
            domain_patterns = [
                rf'{domain_escaped}',
                rf'<td[^>]*>{domain_escaped}</td>',
                rf'<span[^>]*>{domain_escaped}</span>',
                rf'<div[^>]*>{domain_escaped}</div>',
                rf'"{domain_escaped}"',
                rf"'{domain_escaped}'",
                rf'>\\s*{domain_escaped}\\s*<',
            ]
            
            found = False
            for pattern in domain_patterns:
                if re.search(pattern, html_lower, re.IGNORECASE):
                    found = True
                    break
            
            if not found:
                logger.info(f"✅ {domain}: Tidak ditemukan di response (asumsi aman)")
                return False
            
            # Ambil konteks di sekitar domain
            match = re.search(rf'.{{0,400}}{domain_escaped}.{{0,400}}', html_lower, re.IGNORECASE)
            if not match:
                return False
            
            context = match.group(0)
            
            # Indikasi terblokir (Next.js biasanya menggunakan class atau data attributes)
            blocked_indicators = [
                r'terblokir',
                r'diblokir',
                r'blocked',
                r'nawala',
                r'positif',
                r'terindikasi',
                r'berbahaya',
                r'ilegal',
                r'pornografi',
                r'perjudian',
                r'data-status=["\'](blocked|terblokir)["\']',
                r'class=["\'][^"\']*(blocked|block|red|danger)[^"\']*["\']',
                r'bg-red',
                r'text-red',
                r'border-red',
                r'status["\']?\s*[:=]\s*["\']?(blocked|terblokir)',
                r'<span[^>]*class=["\'].*?blocked.*?["\'][^>]*>',
                r'<td[^>]*>.*?(blocked|terblokir).*?</td>',
            ]
            
            # Indikasi aman
            safe_indicators = [
                r'aman',
                r'safe',
                r'allowed',
                r'tidak ada',
                r'tidak ditemukan',
                r'data-status=["\'](clean|ok|allowed|aman)["\']',
                r'class=["\'][^"\']*(success|green|safe)[^"\']*["\']',
                r'bg-green',
                r'text-green',
                r'border-green',
                r'status["\']?\s*[:=]\s*["\']?(clean|ok|allowed|aman)',
            ]
            
            # Cek indikasi blokir di konteks
            for pattern in blocked_indicators:
                if re.search(pattern, context, re.IGNORECASE):
                    logger.warning(f"🚫 {domain}: Terdeteksi terblokir")
                    return True
            
            # Cek indikasi aman di konteks
            for pattern in safe_indicators:
                if re.search(pattern, context, re.IGNORECASE):
                    logger.info(f"✅ {domain}: Terdeteksi aman")
                    return False
            
            # Cek indikasi blokir di seluruh HTML (jika ada di dekat domain)
            domain_index = html_lower.find(domain_lower)
            if domain_index != -1:
                start = max(0, domain_index - 500)
                end = min(len(html_lower), domain_index + 500)
                context_large = html_lower[start:end]
                
                for pattern in blocked_indicators:
                    if re.search(pattern, context_large, re.IGNORECASE):
                        logger.warning(f"🚫 {domain}: Terdeteksi terblokir (dari konteks luas)")
                        return True
                
                for pattern in safe_indicators:
                    if re.search(pattern, context_large, re.IGNORECASE):
                        logger.info(f"✅ {domain}: Terdeteksi aman (dari konteks luas)")
                        return False
            
            # Default: aman
            logger.info(f"✅ {domain}: Tidak terdeteksi blokir (asumsi aman)")
            return False
            
        except Exception as e:
            logger.error(f"❌ HTML parse error: {e}")
            return None
    
    def _extract_domain(self, item):
        """Extract domain dari berbagai format"""
        for key in ['domain', 'name', 'url', 'host', 'target', 'item', 'id']:
            if key in item:
                return str(item[key]).strip().lower()
        return ''
    
    def check_all_domains(self, domains):
        """Cek semua domain satu per satu"""
        try:
            if not domains:
                return []
            
            all_blocked = []
            total = len(domains)
            
            for i, domain in enumerate(domains, 1):
                logger.info(f"📌 [{i}/{total}] Memeriksa: {domain}")
                
                # Cek domain
                is_blocked = self.check_single_domain(domain)
                
                if is_blocked is True:
                    all_blocked.append(domain)
                    logger.warning(f"🚫 {domain}: TERBLOKIR")
                elif is_blocked is False:
                    logger.info(f"✅ {domain}: AMAN")
                else:
                    # Unknown - coba sekali lagi dengan delay
                    logger.info(f"🔄 Retry {domain}...")
                    time.sleep(2)
                    is_blocked = self.check_single_domain(domain)
                    if is_blocked is True:
                        all_blocked.append(domain)
                        logger.warning(f"🚫 {domain}: TERBLOKIR (setelah retry)")
                    else:
                        logger.info(f"✅ {domain}: AMAN (setelah retry)")
                
                # Delay antar domain untuk menghindari rate limiting
                if i < total:
                    delay = 2
                    logger.info(f"⏳ Menunggu {delay} detik sebelum domain berikutnya...")
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
            "🤖 *TrustPositif Checker Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Mode:** 1 domain/request\n"
            f"🌐 **Sumber:** trustpositif.infonawala.com (Next.js)\n\n"
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
                "✅ *LAPORAN CEK TRUSTPOSITIF*\n\n"
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
                "_Sumber: trustpositif.infonawala.com (Next.js)_"
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
                    "_Sumber: trustpositif.infonawala.com_"
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
        logger.info("🔄 MEMULAI PEMERIKSAAN TRUSTPOSITIF.INFONAWALA.COM")
        logger.info("🔄 Mode: 1 domain per request")
        logger.info("🔄 Platform: Next.js")
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
    print("🚀 TRUSTPOSITIF.INFONAWALA.COM DOMAIN MONITORING BOT")
    print("📌 Mode: 1 domain per request")
    print("📌 Platform: Next.js")
    print("=" * 60)
    
    logger.info("Bot starting...")
    logger.info("🌐 Source: trustpositif.infonawala.com (Next.js)")
    logger.info("📌 Mode: 1 domain per request (lebih akurat)")
    
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
    logger.info("📍 Delay antar domain: 2 detik")
    logger.info("📍 Platform: Next.js")
    logger.info("📍 Source: trustpositif.infonawala.com")
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
